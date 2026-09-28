"""Real ownership, execution/edit conflict and deletion-retention integration tests."""

import json
import secrets
import time
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, Outbox, User, now
from app.toolbox.storage.s3 import client
from workers.tasks import execute

BASE = "http://api:8000/api"
owners, checks = [], []


def check(value, message):
    assert value, message
    checks.append(message)
    print("PASS " + message, flush=True)


def fixture(owner, state="queued", title="CRUD fixture"):
    with transaction() as db:
        row = Job(owner_id=owner, tool_id="text.export", title=title, state=state, params={"text": "before"}, idempotency_key=str(uuid4()), request_hash="fixture", heartbeat_at=now())
        db.add(row)
        db.flush()
        return row.id


def main():
    with httpx.Client(base_url=BASE, timeout=30) as admin, httpx.Client(base_url=BASE, timeout=30) as a, httpx.Client(base_url=BASE, timeout=30) as b:
        admin.post("/auth/login", json={"username": "admin", "password": settings().admin_password}).raise_for_status()
        for c in (a, b):
            name, password = "crud_" + secrets.token_hex(5), secrets.token_urlsafe(24)
            r = admin.post("/admin/users", json={"username": name, "name": "CRUD 测试", "password": password})
            r.raise_for_status()
            owners.append(r.json()["id"])
            c.post("/auth/login", json={"username": name, "password": password}).raise_for_status()
        job_id = fixture(owners[0])
        foreign = fixture(owners[1], title="foreign only")
        check(
            b.get(f"/jobs/{job_id}").status_code == 404 and b.patch(f"/jobs/{job_id}", json={"title": "intrusion"}).status_code == 404 and b.delete(f"/jobs/{job_id}").status_code == 404,
            "Foreign read, edit and delete blocked",
        )
        check(a.get("/jobs/query", params={"q": "foreign only"}).json()["total"] == 0, "Query cannot leak another account's tasks")
        check(a.patch(f"/jobs/{job_id}", json={"title": "   "}).status_code == 422, "Blank title rejected")
        check(a.patch(f"/jobs/{job_id}", json={"state": "succeeded"}).status_code == 422, "Client cannot assign execution state")
        invalid = a.patch(f"/jobs/{job_id}", json={"title": "should rollback", "params": {"text": ""}})
        check(invalid.status_code == 422 and a.get(f"/jobs/{job_id}").json()["title"] == "CRUD fixture", "Invalid parameters roll back title changes")
        edited = a.patch(f"/jobs/{job_id}", json={"title": "edited % task", "params": {"text": "after edit"}})
        check(edited.status_code == 200 and edited.json()["params"] == {"text": "after edit"}, "Queued task title and parameters edited")
        filtered = a.get("/jobs/query", params={"q": "%", "state": "queued", "tool_id": "text.export", "page_size": 1}).json()
        check(filtered["total"] == 1 and filtered["items"][0]["id"] == job_id, "Filtering and literal wildcard search work")
        check(a.get("/jobs/query", params={"page": 0}).status_code == 422 and a.get("/jobs/query", params={"page_size": 101}).status_code == 422, "Pagination limits validated")
        execute.apply_async(args=[job_id])
        for _ in range(40):
            job = a.get(f"/jobs/{job_id}").json()
            if job["state"] in {"succeeded", "failed"}:
                break
            time.sleep(0.5)
        check(job["state"] == "succeeded", "Worker executes edited queued task")
        asset_id = job["result"]["asset_id"]
        check(a.get(f"/assets/{asset_id}/download").text == "after edit", "Result uses updated input snapshot")
        check(a.patch(f"/jobs/{job_id}", json={"params": {"text": "too late"}}).status_code == 409, "Completed task parameters immutable")
        check(a.patch(f"/jobs/{job_id}", json={"title": "renamed result"}).status_code == 200, "Completed task can be renamed")
        running = fixture(owners[0], "running")
        check(a.patch(f"/jobs/{running}", json={"params": {"text": "too late"}}).status_code == 409 and a.delete(f"/jobs/{running}").status_code == 409, "Running task edit/delete conflicts protected")
        check(a.post(f"/jobs/{running}/cancel").json()["state"] == "cancel_requested" and a.delete(f"/jobs/{running}").status_code == 409, "Must wait for cancellation completion before deletion")
        check(a.delete(f"/jobs/{job_id}").status_code == 204 and a.get(f"/jobs/{job_id}").status_code == 404, "Completed task record deleted")
        check(a.get(f"/assets/{asset_id}/download").text == "after edit" and a.get(f"/assets/{asset_id}").json()["job_id"] is None, "Generated file retained after task deletion")
        queued = fixture(owners[0])
        check(a.delete(f"/jobs/{queued}").status_code == 204, "Queued task record can be deleted")
        execute.apply_async(args=[queued])
        time.sleep(1)
        check(a.get(f"/jobs/{queued}").status_code == 404 and len(a.get("/assets").json()) == 1, "Late delivery cannot recreate deleted task or output")
        # Batch deletion exercises the same worker/ownership boundary, plus partial outcomes.
        batch_url = "/jobs/batch-delete"
        with httpx.Client(base_url=BASE) as guest:
            check(guest.post(batch_url, json={"job_ids": [foreign]}).status_code == 401, "Batch delete requires authentication")
        for payload in ({"job_ids": []}, {"job_ids": ["bad-id"]}, {"job_ids": [str(uuid4())] * 101}, {"job_ids": [foreign], "all": True}):
            check(a.post(batch_url, json=payload).status_code == 422, "Invalid batch payload rejected")
        complete = fixture(owners[0], "succeeded")
        waiting = fixture(owners[0])
        active = fixture(owners[0], "running")
        failed = fixture(owners[0], "failed")
        cancelled = fixture(owners[0], "cancelled")
        missing = str(uuid4())
        with transaction() as db:
            db.get(Asset, asset_id).job_id = complete
            db.add(Outbox(job_id=waiting, sent_at=now()))
        ids = [waiting, complete, complete, active, running, foreign, missing, failed, cancelled]
        response = a.post(batch_url, json={"job_ids": ids})
        check(response.status_code == 200, "Mixed batch reports partial outcomes")
        outcome = response.json()
        check(set(outcome["deleted_ids"]) == {waiting, complete, failed, cancelled} and len(outcome["deleted_ids"]) == 4, "Batch deletes all eligible states and deduplicates IDs")
        codes = {item["id"]: item["code"] for item in outcome["skipped"]}
        check(codes == {active: "active", running: "active", foreign: "not_found", missing: "not_found"}, "Active tasks skipped and foreign existence hidden")
        check(b.get(f"/jobs/{foreign}").status_code == 200 and a.get(f"/jobs/{active}").json()["state"] == "running", "Skipped tasks unchanged")
        check(a.get(f"/assets/{asset_id}/download").text == "after edit" and a.get(f"/assets/{asset_id}").json()["job_id"] is None, "Batch deletion retains downloadable files")
        with transaction() as db:
            check(db.get(Outbox, waiting) is None and db.get(Job, waiting) is None, "Batch removes queued task and its outbox")
        repeat = a.post(batch_url, json={"job_ids": ids}).json()
        check(not repeat["deleted_ids"] and len(repeat["skipped"]) == 8, "Repeated batch safely reports already removed tasks")
        check(a.post(batch_url, json={"job_ids": [str(uuid4()) for _ in range(100)]}).status_code == 200, "Batch accepts upper bound of 100 IDs")
        execute.apply_async(args=[waiting])
        time.sleep(1)
        check(a.get(f"/jobs/{waiting}").status_code == 404 and len(a.get("/assets").json()) == 1, "Late delivery after batch deletion produces no output")
        for c in (a, b, admin):
            c.post("/auth/logout")
    print(json.dumps({"passed": len(checks), "checks": checks}, ensure_ascii=False))


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
