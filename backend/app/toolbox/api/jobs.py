from app.core.router_class import OperationLogRoute
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, or_, select

from app.toolbox.api.dependencies import current_user
from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, JobAttempt, JobEvent, now
from app.toolbox.schemas.http import JobBatchDelete, JobInput, JobPatch
from app.toolbox.services.job_management import edit_job, remove_job, remove_jobs
from app.toolbox.services.jobs import submit
from app.toolbox.services.presenters import job_data

router = APIRouter(route_class=OperationLogRoute)


@router.post("/jobs", status_code=202)
def create_job(data: JobInput, idempotency_key: Annotated[str, Header(min_length=8, max_length=64)], user=Depends(current_user)):
    return submit(data, idempotency_key, user)


@router.get("/jobs")
def jobs(page: int = 1, user=Depends(current_user)):
    if page < 1 or page > 10000:
        raise HTTPException(400, "页码无效")
    with transaction() as db:
        return [job_data(j) for j in db.scalars(select(Job).where(Job.owner_id == user.id).order_by(Job.created_at.desc()).offset((page - 1) * 50).limit(50)).all()]


@router.get("/jobs/query")
def query_jobs(
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
    q: Annotated[str, Query(max_length=200)] = "",
    state: Literal["", "queued", "running", "cancel_requested", "succeeded", "failed", "cancelled", "reconciling"] = "",
    tool_id: Annotated[str, Query(max_length=64)] = "",
    sort: Literal["newest", "oldest"] = "newest",
    user=Depends(current_user),
):
    filters = [Job.owner_id == user.id]
    if q.strip():
        filters.append(or_(Job.title.contains(q.strip(), autoescape=True), Job.id == q.strip()))
    if state:
        filters.append(Job.state == state)
    if tool_id:
        filters.append(Job.tool_id == tool_id)
    with transaction() as db:
        total = db.scalar(select(func.count()).select_from(Job).where(*filters))
        order = (Job.created_at.desc(), Job.id.desc()) if sort == "newest" else (Job.created_at.asc(), Job.id.asc())
        rows = db.scalars(select(Job).where(*filters).order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
        return {"items": [job_data(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/jobs/batch-delete")
def batch_delete_jobs(data: JobBatchDelete, user=Depends(current_user)):
    return remove_jobs(data.job_ids, user.id)


@router.patch("/jobs/{job_id}")
def update_job(job_id: str, data: JobPatch, user=Depends(current_user)):
    return edit_job(job_id, user, data)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, user=Depends(current_user)):
    remove_job(job_id, user.id)
    return Response(status_code=204)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user=Depends(current_user)):
    with transaction() as db:
        job = db.get(Job, job_id)
        if not job or job.owner_id != user.id:
            raise HTTPException(404, "任务不存在")
        return {**job_data(job), "params": job.params, "tool_version": job.tool_version}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user=Depends(current_user)):
    with transaction() as db:
        job = db.execute(select(Job).where(Job.id == job_id, Job.owner_id == user.id).with_for_update()).scalar_one_or_none()
        if not job:
            raise HTTPException(404, "任务不存在")
        previous_state = job.state
        if job.state == "queued":
            job.state, job.message, job.finished_at = "cancelled", "已取消", now()
        elif job.state == "running":
            job.state, job.message = "cancel_requested", "正在停止处理"
        job.stage = job.state
        if job.attempt and job.state != previous_state:
            attempt = db.get(JobAttempt, job.attempt)
            if attempt and job.state == "cancelled":
                attempt.state, attempt.finished_at = "cancelled", job.finished_at
            db.add(JobEvent(job_id=job.id, attempt_id=job.attempt, event_type=job.state, payload={}))
        return job_data(job)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, idempotency_key: Annotated[str, Header(min_length=8, max_length=64)], user=Depends(current_user)):
    with transaction() as db:
        job = db.get(Job, job_id)
        if not job or job.owner_id != user.id:
            raise HTTPException(404, "任务不存在")
        if job.state not in {"failed", "cancelled"}:
            raise HTTPException(409, "仅失败或取消的任务可重试")
        if job.result.get("submission_state") in {"submitting", "unknown"}:
            raise HTTPException(409, "引擎提交结果未知，请先在 GPT-SoVITS 核对，避免重复合成")
        data = JobInput(tool_id=job.tool_id, params=job.params)
    return submit(data, idempotency_key, user, parent_job_id=job_id)


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, after: int = 0, user=Depends(current_user)):
    with transaction() as db:
        job = db.get(Job, job_id)
        if not job or job.owner_id != user.id:
            raise HTTPException(404, "任务不存在")
        events = db.scalars(select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id > after).order_by(JobEvent.id).limit(100)).all()
        attempts = db.scalars(select(JobAttempt).where(JobAttempt.job_id == job_id).order_by(JobAttempt.attempt_no)).all()
        return {"events": [{k: getattr(row, k) for k in ('id', 'attempt_id', 'event_type', 'payload', 'created_at')} for row in events],
                "attempts": [{k: getattr(row, k) for k in ('id', 'attempt_no', 'state', 'started_at', 'finished_at', 'error_code')} for row in attempts]}


@router.get("/stats")
def stats(user=Depends(current_user)):
    with transaction() as db:
        counts = dict(db.execute(select(Job.state, func.count()).where(Job.owner_id == user.id).group_by(Job.state)).all())
        size = db.scalar(select(func.coalesce(func.sum(Asset.size), 0)).where(Asset.owner_id == user.id))
        files = db.scalar(select(func.count()).select_from(Asset).where(Asset.owner_id == user.id))
        return {"jobs": counts, "storage_bytes": size, "file_count": files, "storage_limit": settings().user_storage_mb * 1024 * 1024}
