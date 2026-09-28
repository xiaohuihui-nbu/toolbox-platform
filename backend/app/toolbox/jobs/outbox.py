import logging
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Job, JobAttempt, JobEvent, Outbox
from app.toolbox.jobs.capabilities import db_now
from workers.tasks import execute


def dispatch_once():
    deliveries = []
    with transaction() as db:
        current = db_now(db)
        stale = db.scalars(select(JobAttempt.id).where(JobAttempt.state == "running", JobAttempt.lease_until < current).limit(100)).all()
        for attempt_id in stale:
            candidate = db.get(JobAttempt, attempt_id)
            job = db.scalar(select(Job).where(Job.id == candidate.job_id).with_for_update(skip_locked=True))
            if not job:
                continue
            attempt = db.scalar(select(JobAttempt).where(JobAttempt.id == attempt_id).with_for_update().execution_options(populate_existing=True))
            if job.attempt != attempt.id or job.state not in {"running", "cancel_requested"} or attempt.state != "running" or attempt.lease_until >= db_now(db):
                continue
            uncertain = job.result.get("submission_state") in {"submitting", "unknown", "accepted"}
            state = "reconciling" if uncertain else ("cancelled" if job.state == "cancel_requested" else "failed")
            job.state = job.stage = attempt.state = state
            job.message = "执行租约失效；外部结果需核对" if uncertain else "执行器失联，请重试"
            job.finished_at = attempt.finished_at = None if uncertain else current
            attempt.error_code = "SUBMISSION_UNCERTAIN" if uncertain else "WORKER_LOST"
            db.add(JobEvent(job_id=job.id, attempt_id=attempt.id, event_type=state, payload={"error_code": attempt.error_code}))
        rows = db.scalars(select(Outbox).where(Outbox.not_before <= current,
            or_(Outbox.lease_until.is_(None), Outbox.lease_until < current)).with_for_update(skip_locked=True).limit(30)).all()
        for item in rows:
            job = db.get(Job, item.job_id)
            if not job or job.state != "queued" or item.attempt_id != job.attempt:
                db.delete(item); continue
            if item.deliveries >= 8:
                job.state = job.stage = "failed"; job.finished_at = current
                job.message = "投递超过恢复次数，请检查执行器后手动重试"
                attempt = db.get(JobAttempt, job.attempt)
                attempt.state, attempt.error_code, attempt.finished_at = "failed", "DISPATCH_EXHAUSTED", current
                db.add(JobEvent(job_id=job.id, attempt_id=job.attempt, event_type="failed", payload={"error_code": "DISPATCH_EXHAUSTED"}))
                db.delete(item); continue
            token = str(uuid4())
            item.lease_token, item.lease_until = token, current + timedelta(seconds=30)
            item.deliveries += 1
            deliveries.append((job.id, item.attempt_id, token, job.resource_profile, job.config_snapshot['timeout_seconds']))
    # Network publication deliberately occurs after the row-lock transaction commits.
    for job_id, attempt_id, token, profile, timeout in deliveries:
        sent = False
        try:
            execute.apply_async(args=[job_id, attempt_id], task_id=str(uuid4()), queue="toolbox." + profile,
                                retry=False, soft_time_limit=timeout, time_limit=timeout + 30)
            sent = True
        except Exception:
            logging.exception("outbox publication failed: %s", job_id)
        with transaction() as db:
            item = db.scalar(select(Outbox).where(Outbox.job_id == job_id).with_for_update())
            if item and item.lease_token == token:
                current = db_now(db)
                if sent: item.sent_at = current
                # Allow the resource queue's preceding bounded execution to finish.
                item.not_before = current + timedelta(seconds=timeout + 60 if sent else min(60, 2 ** item.deliveries))
                item.lease_token = item.lease_until = None


if __name__ == "__main__":
    while True:
        try: dispatch_once()
        except Exception: logging.exception("outbox recovery failed")
        time.sleep(3)
