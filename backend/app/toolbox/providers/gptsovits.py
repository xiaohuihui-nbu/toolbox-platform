import re
import time

import httpx
from sqlalchemy import select

from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Job, JobAttempt
from app.toolbox.jobs.capabilities import db_now

GATEWAY = "http://tts-gateway:8898"


def provider_get(path):
    with httpx.Client(timeout=8, trust_env=False) as client:
        response = client.get(GATEWAY + path)
        response.raise_for_status()
        return response


def synthesize(params, directory, check, job_id, attempt):
    def update_result(value, progress=None, message=None):
        with transaction() as db:
            job = db.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            att = db.get(JobAttempt, attempt)
            if not att or not att.lease_until or att.lease_until < db_now(db) or job.attempt != attempt or job.state not in {"running", "cancel_requested"}:
                raise ValueError("任务执行权已失效")
            job.result = value
            if value.get("provider_job_id"):
                att.provider_job_id = value["provider_job_id"]
            if progress is not None:
                job.progress, job.message = progress, message

    remote_id = None
    completed = False
    with httpx.Client(base_url=GATEWAY, timeout=35, trust_env=False) as client:
        health = client.get("/health")
        if health.status_code != 200 or health.json().get("status") != "ready":
            raise ValueError("GPT-SoVITS 尚未就绪，请等待模型加载或启动配音服务")
        check()
        update_result({"provider": "gptsovits", "submission_state": "submitting"})
        try:
            try:
                response = client.post("/api/jobs", json={key: params[key] for key in ("text", "voice_id", "speed", "pause")})
            except httpx.HTTPError:
                update_result({"provider": "gptsovits", "submission_state": "unknown"})
                raise ValueError("引擎提交结果未知，请先到配音服务核对；系统不会自动重复提交")
            if response.status_code != 202:
                unknown = response.status_code >= 500
                update_result({"provider": "gptsovits", "submission_state": "unknown" if unknown else "rejected"})
                raise ValueError("引擎未确认任务，请检查配音服务状态后再处理")
            remote_id = response.json()["id"]
            result = {"provider": "gptsovits", "provider_job_id": remote_id, "submission_state": "accepted"}
            update_result(result)
            deadline = time.monotonic() + 740
            while time.monotonic() < deadline:
                check()
                response = client.get(f"/api/jobs/{remote_id}")
                response.raise_for_status()
                job = response.json()
                if job["status"] == "done":
                    filename = job[params["format"]]
                    if not re.fullmatch(r"[a-f0-9]{32}-full-[a-f0-9]{8}\.(wav|mp3)", filename):
                        raise ValueError("引擎返回的文件名无效")
                    output = directory / ("自然配音." + params["format"])
                    with client.stream("GET", "/audio/" + filename) as audio:
                        audio.raise_for_status()
                        size = 0
                        with output.open("wb") as target:
                            for chunk in audio.iter_bytes(256 * 1024):
                                check()
                                size += len(chunk)
                                if size > 100 * 1024 * 1024:
                                    raise ValueError("引擎输出超过 100 MB")
                                target.write(chunk)
                    completed = True
                    return output
                if job["status"] in {"failed", "cancelled", "interrupted"}:
                    raise ValueError("配音引擎任务未完成，请检查引擎运行状态")
                segments = job.get("segments", [])
                count = sum(segment.get("status") == "done" for segment in segments)
                update_result(result, 15 + int(70 * count / max(1, len(segments))), f"自然配音：已完成 {count}/{len(segments)} 段" if job["status"] == "running" else "正在等待配音引擎")
                time.sleep(2)
            raise ValueError("CPU 配音等待超时，请缩短文本；已请求引擎停止")
        finally:
            if remote_id and not completed:
                try:
                    client.post(f"/api/jobs/{remote_id}/cancel")
                except httpx.HTTPError:
                    pass  # The persisted provider_job_id remains available for reconciliation.
