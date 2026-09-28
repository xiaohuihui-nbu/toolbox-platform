"""Live search and batch contract checks; run inside API container."""

import json
import secrets
import time
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, Outbox, User
from app.toolbox.search.videos import store
from app.toolbox.storage.s3 import client

BASE = "http://api:8000/api"
owners, tickets, checks = [], [], []


def check(ok, label):
    assert ok, label
    checks.append(label)
    print("PASS " + label, flush=True)


def main():
    with httpx.Client(base_url=BASE, timeout=30) as admin, httpx.Client(base_url=BASE, timeout=30) as a, httpx.Client(base_url=BASE, timeout=30) as b:
        admin.post("/auth/login", json={"username": "admin", "password": settings().admin_password}).raise_for_status()
        for session in (a, b):
            username, password = "batch_" + secrets.token_hex(4), secrets.token_urlsafe(24)
            response = admin.post("/admin/users", json={"username": username, "name": "批量下载测试", "password": password})
            response.raise_for_status()
            owners.append(response.json()["id"])
            session.post("/auth/login", json={"username": username, "password": password}).raise_for_status()
        for platform in ("bilibili", "youtube"):
            response = a.post("/video-search", json={"query": "Blender Sintel trailer", "platform": platform, "limit": 3})
            check(response.status_code == 202, platform + " search queued")
            ticket = response.json()["id"]
            tickets.append(ticket)
            check(b.get(f"/video-search/{ticket}").status_code == 404, platform + " search owner isolation")
            for _ in range(60):
                data = a.get(f"/video-search/{ticket}").json()
                if data["state"] in {"succeeded", "failed"}:
                    break
                time.sleep(1.5)
            check(data["state"] == "succeeded" and 0 < len(data["items"]) <= 3, platform + " real search results: " + str(data.get("error") or len(data["items"])))
            check(all(item["title"] and item["url"].startswith("https://") for item in data["items"]), platform + " titles and source URLs")
            thumbnail = data["items"][0].get("thumbnail")
            if thumbnail:
                check(b.get(thumbnail.removeprefix("/api")).status_code == 404, platform + " thumbnail owner isolation")
        sample = "https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4"
        body = {"items": [{"url": sample, "title": "批量验证 A"}, {"url": sample}, {"url": "not-a-url"}, {"url": sample + "?batch=2", "title": "批量验证 B"}]}
        key = {"Idempotency-Key": str(uuid4())}
        response = a.post("/video-downloads/batch", json=body, headers=key)
        response.raise_for_status()
        data = response.json()
        check((data["accepted"], data["duplicates"], data["rejected"]) == (2, 1, 1), "Batch accepts two, skips duplicate, rejects invalid item independently")
        jobs = [item["job"]["id"] for item in data["items"] if item.get("job")]
        again = a.post("/video-downloads/batch", json=body, headers=key).json()
        check(jobs == [item["job"]["id"] for item in again["items"] if item.get("job")], "Retry same batch key does not duplicate jobs")
        changed = a.post("/video-downloads/batch", json={"items": [{"url": sample + "?changed=1"}]}, headers=key).json()
        check(changed["items"][0]["status"] == 409, "Reusing batch key with changed input rejected")
        check(a.post("/video-downloads/batch", json={"items": [{"url": sample}] * 21}, headers={"Idempotency-Key": str(uuid4())}).status_code == 422, "Batch limit 20 enforced")
        for job_id in jobs:
            for _ in range(150):
                job = a.get(f"/jobs/{job_id}").json()
                if job["state"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(1)
            check(job["state"] == "succeeded", "Batch job completes: " + job["title"] + " / " + job["message"])
            preview = a.get(f"/assets/{job['result']['asset_id']}/preview", headers={"Range": "bytes=0-127"})
            check(preview.status_code == 206 and len(preview.content) == 128, "Batch result supports video preview")
        for session in (a, b, admin):
            session.post("/auth/logout")
    print(json.dumps({"passed": len(checks), "checks": checks}, ensure_ascii=False), flush=True)


try:
    main()
finally:
    for ticket in tickets:
        store().delete("tb:search:" + ticket, "tb:search-lock:" + ticket)
    with transaction() as db:
        for owner in owners:
            # The live jobs above are awaited before deleting their test data.
            active = db.scalar(select(Job).where(Job.owner_id == owner, Job.state.in_(["queued", "running", "cancel_requested"])))
            if active:
                print("Test account retained because a job is still active: " + owner)
                continue
            for asset in db.scalars(select(Asset).where(Asset.owner_id == owner)).all():
                client().delete_object(Bucket=settings().s3_bucket, Key=asset.object_key)
            ids = list(db.scalars(select(Job.id).where(Job.owner_id == owner)))
            if ids:
                db.execute(delete(Outbox).where(Outbox.job_id.in_(ids)))
            db.execute(delete(Asset).where(Asset.owner_id == owner))
            db.execute(delete(Job).where(Job.owner_id == owner))
            db.execute(delete(User).where(User.id == owner))
