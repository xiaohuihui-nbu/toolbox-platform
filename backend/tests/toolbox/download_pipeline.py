"""Opt-in real download timing through API/Celery/MinIO, using a disposable account."""

import hashlib
import json
import secrets
import time
from datetime import datetime
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, Outbox, User
from app.toolbox.storage.s3 import client

owner = None
try:
    with httpx.Client(base_url="http://api:8000/api", timeout=30) as admin, httpx.Client(base_url="http://api:8000/api", timeout=30) as user:
        admin.post("/auth/login", json={"username": "admin", "password": settings().admin_password}).raise_for_status()
        username, password = "speed_" + secrets.token_hex(5), secrets.token_urlsafe(24)
        response = admin.post("/admin/users", json={"username": username, "password": password, "name": "临时下载性能验收"})
        response.raise_for_status()
        owner = response.json()["id"]
        user.post("/auth/login", json={"username": username, "password": password}).raise_for_status()
        start = time.monotonic()
        response = user.post("/jobs", headers={"Idempotency-Key": str(uuid4())}, json={
            "tool_id": "video.download", "params": {"url": "https://www.bilibili.com/video/av117322685618746", "quality": "1080p"},
        })
        response.raise_for_status()
        job_id = response.json()["id"]
        while time.monotonic() - start < 120:
            job = user.get(f"/jobs/{job_id}").json()
            if job["state"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.4)
        assert job["state"] == "succeeded", job["state"]
        duration = round(time.monotonic() - start, 3)
        asset = user.get(f"/assets/{job['result']['asset_id']}").json()
        file = user.get(f"/assets/{asset['id']}/download")
        file.raise_for_status()
        print(json.dumps({
            "state": job["state"], "observed_total_s": duration,
            "queue_s": (datetime.fromisoformat(job["started_at"]) - datetime.fromisoformat(job["created_at"])).total_seconds(),
            "processing_s": (datetime.fromisoformat(job["finished_at"]) - datetime.fromisoformat(job["started_at"])).total_seconds(),
            "bytes": len(file.content), "sha256": hashlib.sha256(file.content).hexdigest(),
        }), flush=True)
        user.post("/auth/logout")
        admin.post("/auth/logout")
finally:
    if owner:
        with transaction() as db:
            jobs = list(db.scalars(select(Job).where(Job.owner_id == owner)))
            # Never remove state underneath a live worker; timeout leaves the account for inspection.
            if all(job.state not in {"running", "queued", "cancel_requested"} for job in jobs):
                for asset in db.scalars(select(Asset).where(Asset.owner_id == owner)).all():
                    client().delete_object(Bucket=settings().s3_bucket, Key=asset.object_key)
                db.execute(delete(Asset).where(Asset.owner_id == owner))
                db.execute(delete(Outbox).where(Outbox.job_id.in_([job.id for job in jobs])))
                db.execute(delete(Job).where(Job.owner_id == owner))
                db.execute(delete(User).where(User.id == owner))
