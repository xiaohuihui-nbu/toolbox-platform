import hashlib
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select, update

from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, Outbox
from app.toolbox.models.entities import User, JobAttempt, JobEvent, now
from app.toolbox.schemas.http import JobInput
from app.toolbox.services.jobs import submit
from uuid import uuid4
from app.toolbox.registry.catalog import REGISTRY
from app.toolbox.services.presenters import job_data


def owned_locked(db, job_id, owner_id):
    row = db.scalar(select(Job).where(Job.id == job_id, Job.owner_id == owner_id).with_for_update())
    if row is None:
        raise HTTPException(404, "任务不存在")
    return row


def edit_job(job_id, owner, data):
    if data.title is None and data.params is None:
        raise HTTPException(422, "至少修改一个字段")
    with transaction() as db:
        owner_id = owner.id
        db.scalar(select(User).where(User.id == owner_id).with_for_update())
        row = owned_locked(db, job_id, owner_id)
        if data.title is not None:
            title = data.title.strip()
            if not title:
                raise HTTPException(422, "任务名称不能为空")
            row.title = title
        if data.params is not None:
            if row.state != "queued":
                raise HTTPException(409, "任务已开始，不能修改输入参数；可以新建任务")
            tool = REGISTRY.get(row.tool_id)
            if not tool or tool["schema"] is None:
                raise HTTPException(409, "工具版本暂不可编辑")
            try:
                params = tool["schema"](**data.params).model_dump(mode="json")
            except ValidationError as exc:
                raise HTTPException(422, str(exc))
            if row.tool_id == "video.download" and params.get("quality") == "best":
                params.pop("quality")
            if "asset_id" in params:
                asset = db.get(Asset, params["asset_id"])
                if not asset or asset.owner_id != owner_id:
                    raise HTTPException(404, "输入文件不存在")
            # The old input snapshot is immutable; replace queued execution atomically.
            row.state = row.stage = 'cancelled'
            db.flush()  # Release this queued slot inside the same atomic replacement.
            result = submit(JobInput(tool_id=row.tool_id, params=params), str(uuid4()), owner, parent_job_id=row.id, session=db)
            replacement = db.get(Job, result['id'])
            replacement.title = row.title
            row.finished_at, row.message = now(), '参数已更新，已创建关联的新任务'
            attempt = db.get(JobAttempt, row.attempt) if row.attempt else None
            if attempt:
                attempt.state, attempt.finished_at = 'cancelled', row.finished_at
            db.execute(delete(Outbox).where(Outbox.job_id == row.id))
            db.add(JobEvent(job_id=row.id, attempt_id=row.attempt, event_type='superseded', payload={'replacement_job_id': replacement.id}))
            return {**job_data(replacement), 'params': replacement.params}
        return {**job_data(row), "params": row.params}


def remove_job(job_id, owner_id):
    with transaction() as db:
        row = owned_locked(db, job_id, owner_id)
        if row.state in {"running", "cancel_requested", "reconciling"}:
            raise HTTPException(409, "请等待任务停止；外部结果待核对的任务须先完成核对")
        remove_records(db, [row.id], owner_id)


def remove_records(db, ids, owner_id):
    # Keep generated files. A queued worker delivered after deletion exits on missing job.
    if not ids:
        return
    db.execute(update(Asset).where(Asset.job_id.in_(ids), Asset.owner_id == owner_id).values(job_id=None))
    db.execute(delete(Outbox).where(Outbox.job_id.in_(ids)))
    db.execute(delete(Job).where(Job.id.in_(ids), Job.owner_id == owner_id))


def remove_jobs(job_ids, owner_id):
    ids = list(dict.fromkeys(str(job_id) for job_id in job_ids))
    deleted, skipped = [], []
    with transaction() as db:
        # Lock in stable order and recheck state against workers, not the browser snapshot.
        rows = {row.id: row for row in db.scalars(
            select(Job).where(Job.id.in_(ids), Job.owner_id == owner_id).order_by(Job.id).with_for_update()
        ).all()}
        for job_id in ids:
            row = rows.get(job_id)
            if row is None:
                skipped.append({"id": job_id, "code": "not_found", "message": "任务不存在或已删除"})
            elif row.state in {"running", "cancel_requested", "reconciling"}:
                skipped.append({"id": job_id, "code": "active", "message": "任务正在执行或取消中，请等待停止后再删除"})
            else:
                deleted.append(job_id)
        remove_records(db, deleted, owner_id)
    return {"deleted_ids": deleted, "skipped": skipped}
