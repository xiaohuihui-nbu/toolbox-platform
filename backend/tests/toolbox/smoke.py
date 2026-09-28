"""Run inside the API container against real MySQL/Redis/Celery/S3.

Creates two isolated test accounts and removes only their rows/objects in finally.
No mocks for the primary execution, TTS, audio extraction or ownership checks.
"""

import asyncio
import json
import secrets
import time
from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.toolbox.config import settings
from app.toolbox.jobs.outbox import dispatch_once
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, Outbox, User, now
from app.toolbox.runtime.egress import connect_public
from app.toolbox.storage.s3 import client
from workers.tasks import execute

BASE = "http://api:8000/api"
passed = []
owners = []


def check(condition, label):
    assert condition, label
    passed.append(label)
    print("PASS " + label, flush=True)


def wait_job(c, job_id):
    for _ in range(100):
        job = c.get(f"{BASE}/jobs/{job_id}").json()
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(1)
    raise AssertionError("Task did not finish within 100 seconds")


def submit(c, tool, params, key=None):
    r = c.post(f"{BASE}/jobs", json={"tool_id": tool, "params": params}, headers={"Idempotency-Key": key or str(uuid4())})
    assert r.status_code == 202, r.text
    return r.json()


def main():
    admin = httpx.Client(timeout=45)
    check(admin.get(f"{BASE}/health").status_code == 200, "MySQL Redis S3 health")
    check(admin.post(f"{BASE}/auth/login", json={"username": "admin", "password": settings().admin_password}).status_code == 200, "Administrator login")
    a, b = httpx.Client(timeout=45), httpx.Client(timeout=45)
    for session in [a, b]:
        name = "qa_" + secrets.token_hex(5)
        password = secrets.token_urlsafe(24)
        r = admin.post(f"{BASE}/admin/users", json={"username": name, "password": password, "name": "自动验证账号"})
        assert r.status_code == 201, r.text
        owners.append(r.json()["id"])
        assert session.post(f"{BASE}/auth/login", json={"username": name, "password": password}).status_code == 200
    check(b.post(f"{BASE}/admin/users", json={"username": "denied", "name": "x", "password": "not-a-real-secret"}).status_code == 403, "Member cannot create users")
    prefs = {"mode": "dark", "accent": "violet", "favorites": ["tts.basic"]}
    check(a.put(f"{BASE}/me/preferences", json=prefs).status_code == 200 and a.get(f"{BASE}/me").json()["preferences"] == prefs, "Account appearance persists")
    check(
        a.post(f"{BASE}/jobs", headers={"Origin": "https://unrelated.invalid", "Idempotency-Key": str(uuid4())}, json={"tool_id": "text.export", "params": {"text": "x"}}).status_code == 403,
        "Cross-origin writes denied",
    )
    key = str(uuid4())
    job = submit(a, "text.export", {"text": "真实队列与对象存储验证。"}, key)
    again = submit(a, "text.export", {"text": "真实队列与对象存储验证。"}, key)
    check(job["id"] == again["id"], "Idempotency returns same task")
    conflict = a.post(f"{BASE}/jobs", json={"tool_id": "text.export", "params": {"text": "different"}}, headers={"Idempotency-Key": key})
    check(conflict.status_code == 409, "Idempotency payload mismatch rejected")
    done = wait_job(a, job["id"])
    check(done["state"] == "succeeded", "Outbox Celery MySQL task completed")
    asset_id = done["result"]["asset_id"]
    content = a.get(f"{BASE}/assets/{asset_id}/download")
    check(content.status_code == 200 and content.content.decode("utf-8") == "真实队列与对象存储验证。", "Private S3 download exact content")
    check(a.get(f"{BASE}/assets/{asset_id}/preview").status_code == 415, "Non-media cannot be rendered inline")
    check(b.get(f"{BASE}/jobs/{job['id']}").status_code == 404 and b.post(f"{BASE}/jobs/{job['id']}/cancel").status_code == 404, "Cross-owner task read and cancel denied")
    check(b.get(f"{BASE}/assets/{asset_id}/download").status_code == 404, "Cross-owner file download denied")
    execute.apply_async(args=[job["id"]])
    time.sleep(2)
    check(len(a.get(f"{BASE}/assets").json()) == 1, "Duplicate delivery creates no second output")
    speech = wait_job(a, submit(a, "tts.basic", {"text": "你好，欢迎来到拾光工具箱。", "language": "cmn", "speed": 160})["id"])
    check(speech["state"] == "succeeded", "CPU Chinese TTS completed")
    audio = a.get(f"{BASE}/assets/{speech['result']['asset_id']}/download").content
    check(audio[:4] == b"RIFF" and len(audio) > 1000, "TTS produces real WAV audio")
    media_id = speech["result"]["asset_id"]
    preview = f"{BASE}/assets/{media_id}/preview"
    ranged = a.get(preview, headers={"Range": "bytes=0-31"})
    check(ranged.status_code == 206 and ranged.content == audio[:32] and ranged.headers["content-range"] == f"bytes 0-31/{len(audio)}", "Audio range returns exact bytes")
    suffix = a.get(preview, headers={"Range": "bytes=-16"})
    check(suffix.status_code == 206 and suffix.content == audio[-16:], "Suffix range returns file tail")
    check(a.head(preview).headers["content-length"] == str(len(audio)) and a.get(preview, headers={"Range": "bytes=999999999-"}).status_code == 416, "Media HEAD and unsatisfiable range")
    check(b.get(preview).status_code == 404 and b.head(preview).status_code == 404 and httpx.get(preview).status_code == 401, "Media GET HEAD enforce ownership and login")
    upload = a.post(f"{BASE}/assets", files={"file": ("验证音频.wav", audio, "audio/wav")})
    check(upload.status_code == 201, "Upload to private S3")
    extract = wait_job(a, submit(a, "audio.extract", {"asset_id": upload.json()["id"]})["id"])
    check(extract["state"] == "succeeded", "FFmpeg extraction completed")
    mp3 = a.get(f"{BASE}/assets/{extract['result']['asset_id']}/download").content
    check(len(mp3) > 1000 and (mp3[:3] == b"ID3" or mp3[:1] == b"\xff"), "Extraction produces MP3")
    check(b.post(f"{BASE}/jobs", json={"tool_id": "audio.extract", "params": {"asset_id": asset_id}}, headers={"Idempotency-Key": str(uuid4())}).status_code == 404, "Foreign input asset denied")
    admin.put(f"{BASE}/admin/tools/text.export", json={"enabled": False}).raise_for_status()
    check(a.post(f"{BASE}/jobs", json={"tool_id": "text.export", "params": {"text": "x"}}, headers={"Idempotency-Key": str(uuid4())}).status_code == 409, "Disabled tool rejects submission")
    admin.put(f"{BASE}/admin/tools/text.export", json={"enabled": True}).raise_for_status()
    # Explicit fixture without outbox makes queued cancellation deterministic.
    with transaction() as db:
        queued = Job(owner_id=owners[0], tool_id="text.export", title="queued fixture", params={"text": "cancel"}, idempotency_key=str(uuid4()), request_hash="fixture")
        db.add(queued)
        db.flush()
        queued_id = queued.id
    check(a.post(f"{BASE}/jobs/{queued_id}/cancel").json()["state"] == "cancelled", "Queued cancellation is terminal")
    retry = a.post(f"{BASE}/jobs/{queued_id}/retry", headers={"Idempotency-Key": str(uuid4())})
    check(retry.status_code == 202 and wait_job(a, retry.json()["id"])["state"] == "succeeded", "Manual retry creates successful new task")
    with transaction() as db:
        crashed = Job(
            owner_id=owners[0],
            tool_id="text.export",
            title="lost worker fixture",
            params={"text": "x"},
            idempotency_key=str(uuid4()),
            request_hash="fixture",
            state="running",
            attempt=str(uuid4()),
            heartbeat_at=now() - timedelta(seconds=120),
        )
        db.add(crashed)
        db.flush()
        crashed_id = crashed.id
    dispatch_once()
    check(a.get(f"{BASE}/jobs/{crashed_id}").json()["state"] == "failed", "Expired worker lease fails safely")
    for host in ["127.0.0.1", "169.254.169.254", "::1", "mysql"]:
        try:
            asyncio.run(connect_public(host, 80))
            raise AssertionError("Private address accepted")
        except ValueError:
            pass
    check(True, "Egress blocks loopback metadata IPv6 and internal DNS")
    video = wait_job(a, submit(a, "video.download", {"url": "https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4"})["id"])
    check(video["state"] == "succeeded", "Public sample video downloaded through restricted proxy")
    video_preview = a.get(f"{BASE}/assets/{video['result']['asset_id']}/preview", headers={"Range": "bytes=0-1023"})
    check(
        video_preview.status_code == 206 and video_preview.headers["content-type"].startswith("video/mp4") and len(video_preview.content) == 1024, "Downloaded video supports browser range streaming"
    )
    check(a.post(f"{BASE}/auth/logout").status_code == 200 and a.get(f"{BASE}/me").status_code == 401, "Logout revokes session")
    print(json.dumps({"passed": len(passed), "checks": passed}, ensure_ascii=False), flush=True)


try:
    main()
finally:
    with transaction() as db:
        for owner in owners:
            for asset in db.scalars(select(Asset).where(Asset.owner_id == owner)).all():
                client().delete_object(Bucket=settings().s3_bucket, Key=asset.object_key)
            ids = list(db.scalars(select(Job.id).where(Job.owner_id == owner)))
            if ids:
                db.execute(delete(Outbox).where(Outbox.job_id.in_(ids)))
            db.execute(delete(Asset).where(Asset.owner_id == owner))
            db.execute(delete(Job).where(Job.owner_id == owner))
            db.execute(delete(User).where(User.id == owner))
