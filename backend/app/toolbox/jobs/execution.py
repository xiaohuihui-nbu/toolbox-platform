import logging
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Job, JobAttempt, JobEvent
from app.toolbox.jobs.capabilities import db_now
from app.toolbox.registry.catalog import REGISTRY
from app.toolbox.runtime.process import Cancelled
from app.toolbox.runtime.runner import run
from app.toolbox.storage.s3 import prepare_output, check_storage_quota, client
from app.toolbox.config import settings


def run_job(job_id, attempt_id=None):
    if not attempt_id: return  # Old unversioned messages cannot claim new attempts.
    token = str(uuid4())
    with transaction() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        attempt = db.get(JobAttempt, attempt_id)
        if not job or not attempt or job.state != "queued" or job.attempt != attempt_id or attempt.state != "queued": return
        tool = REGISTRY.get(job.tool_id)
        current = db_now(db)
        if not tool or any(getattr(job, key) != tool[key] for key in ("plugin_id", "plugin_version", "schema_hash")) or job.tool_version != tool['version'] or job.config_snapshot.get('implementation_hash') != tool['implementation_hash']:
            job.state = job.stage = attempt.state = "failed"
            job.message = "插件部署版本与任务快照不一致，请重新提交"
            attempt.error_code = "VERSION_MISMATCH"; job.finished_at = attempt.finished_at = current
            db.add(JobEvent(job_id=job.id, attempt_id=attempt_id, event_type="failed", payload={"error_code": "VERSION_MISMATCH"}))
            return
        job.state = job.stage = attempt.state = "running"
        job.started_at = job.heartbeat_at = attempt.started_at = attempt.heartbeat_at = current
        attempt.lease_token, attempt.lease_until = token, current + timedelta(seconds=60)
        job.progress, job.message = 15, "正在处理"
        owner_id, tool_id, params = job.owner_id, job.tool_id, job.params
        max_output_bytes = job.config_snapshot['max_output_bytes']
        deadline = time.monotonic() + job.config_snapshot['timeout_seconds']
        db.add(JobEvent(job_id=job.id, attempt_id=attempt_id, event_type="running", payload={}))
    stopped, cancelled = threading.Event(), threading.Event()

    def heartbeat():
        while not stopped.wait(5):
            try:
                with transaction() as db:
                    row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                    att = db.get(JobAttempt, attempt_id)
                    current = db_now(db)
                    if not row or not att or row.attempt != attempt_id or row.state != "running" or att.lease_token != token or att.lease_until < current:
                        cancelled.set()
                    else:
                        row.heartbeat_at = att.heartbeat_at = current
                        att.lease_until = current + timedelta(seconds=60)
            except Exception:
                logging.exception("heartbeat failed: %s", job_id); cancelled.set()

    def check():
        if cancelled.is_set(): raise Cancelled()
        if time.monotonic() > deadline: raise TimeoutError('Task execution budget exhausted')

    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    prepared, committed = None, False
    try:
        with tempfile.TemporaryDirectory(prefix=f"toolbox-{attempt_id}-") as temp:
            output = run(REGISTRY[tool_id]["handler"], params, owner_id, Path(temp), check, job_id, attempt_id)
            if output.stat().st_size > max_output_bytes: raise ValueError("产物超过工具输出额度")
            check()
            prepared = prepare_output(output, owner_id, output.name, job_id, attempt_id)
            with transaction() as db:
                # Match submission's owner -> job lock order; S3 I/O holds no DB lock.
                check_storage_quota(db, owner_id, prepared.size)
                row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                att = db.get(JobAttempt, attempt_id)
                if not row or not att or row.attempt != attempt_id or att.lease_token != token or att.lease_until < db_now(db) or row.state not in {"running", "cancel_requested"}: return
                if row.state == "cancel_requested": raise Cancelled()
                asset = prepared
                db.add(asset)
                if att.lease_until < db_now(db): raise Cancelled()
                row.state = row.stage = att.state = "succeeded"
                row.progress, row.message = 100, "处理完成"
                row.result = {**row.result, "asset_id": asset.id}
                row.finished_at = att.finished_at = db_now(db)
                db.add(JobEvent(job_id=job_id, attempt_id=attempt_id, event_type="succeeded", payload={"asset_id": asset.id}))
            committed = True
    except Exception as exc:
        logging.exception("job ended: %s", job_id)
        with transaction() as db:
            row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            att = db.get(JobAttempt, attempt_id)
            if row and att and row.attempt == attempt_id and att.lease_token == token and att.lease_until >= db_now(db) and row.state in {"running", "cancel_requested"}:
                is_cancel = isinstance(exc, Cancelled) or row.state == "cancel_requested"
                uncertain = row.result.get("submission_state") in {"submitting", "unknown", "accepted"}
                state = "reconciling" if uncertain else ("cancelled" if is_cancel else "failed")
                row.state = row.stage = att.state = state
                row.message = "外部执行结果待核对，请先检查配音服务记录" if uncertain else ("任务已取消" if is_cancel else (str(exc) if isinstance(exc, ValueError) else "执行异常，请查看服务日志"))
                code = "SUBMISSION_UNCERTAIN" if uncertain else ("CANCELED" if is_cancel else getattr(exc, 'code', 'EXECUTION_ERROR'))
                row.result = {**row.result, "error_code": code}
                att.error_code = code; att.provider_job_id = row.result.get('provider_job_id')
                row.finished_at = att.finished_at = None if state == "reconciling" else db_now(db)
                db.add(JobEvent(job_id=job_id, attempt_id=attempt_id, event_type=state, payload={"error_code": code}))
    finally:
        stopped.set(); thread.join(timeout=6)
        if prepared is not None and not committed:
            try:
                client().delete_object(Bucket=settings().s3_bucket, Key=prepared.object_key)
            except Exception:
                logging.exception("orphan output requires cleanup: %s", prepared.object_key)
