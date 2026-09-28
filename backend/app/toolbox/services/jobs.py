import hashlib
import json
from uuid import uuid4
from contextlib import nullcontext

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, Outbox, ToolSetting, User, JobAttempt, JobEvent
from app.toolbox.jobs.capabilities import require_worker
from app.toolbox.registry.catalog import REGISTRY
from app.toolbox.services.presenters import job_data


def submit(data, key, owner, parent_job_id=None, session=None):
    from app.toolbox.api.dependencies import require_tool
    require_tool(owner, data.tool_id)
    tool = REGISTRY.get(data.tool_id)
    if not tool or tool["mode"] != "job":
        raise HTTPException(404, "异步工具不存在")
    try:
        params = tool["schema"](**data.params).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(422, str(exc))
    # Preserve the original video payload/digest for clients retrying pre-upgrade requests.
    if data.tool_id == "video.download" and params.get("quality") == "best":
        params.pop("quality")
    digest = hashlib.sha256(json.dumps({"tool": data.tool_id, "params": params}, sort_keys=True).encode()).hexdigest()
    with (nullcontext(session) if session is not None else transaction()) as db:
        db.execute(select(User).where(User.id == owner.id).with_for_update()).scalar_one()
        existing = db.scalar(select(Job).where(Job.owner_id == owner.id, Job.idempotency_key == key))
        if existing:
            if existing.request_hash != digest:
                raise HTTPException(409, "幂等键已用于不同的请求")
            return job_data(existing)
        flag = db.get(ToolSetting, data.tool_id)
        if flag and not flag.enabled:
            raise HTTPException(409, "工具已被管理员停用")
        require_worker(db, tool['resource_profile'])
        count = db.scalar(select(func.count()).select_from(Job).where(Job.owner_id == owner.id, Job.state.in_(["queued", "running", "cancel_requested"])))
        if count >= settings().max_active_jobs:
            raise HTTPException(429, "进行中的任务较多，请等待完成后再提交")
        if "asset_id" in params:
            asset = db.get(Asset, params["asset_id"])
            if not asset or asset.owner_id != owner.id:
                raise HTTPException(404, "输入文件不存在")
        attempt_id = str(uuid4())
        job = Job(owner_id=owner.id, tool_id=data.tool_id, title=params.get("title") or tool["name"],
                  params=params, idempotency_key=key, request_hash=digest, attempt=attempt_id,
                  tool_version=tool['version'], plugin_id=tool['plugin_id'], plugin_version=tool['plugin_version'],
                  schema_hash=tool['schema_hash'], resource_profile=tool['resource_profile'], parent_job_id=parent_job_id,
                  config_snapshot={'timeout_seconds': tool['timeout_seconds'], 'max_output_bytes': tool['max_output_bytes'],
                                   'implementation_hash': tool['implementation_hash']})
        db.add(job)
        db.flush()
        db.add(JobAttempt(id=attempt_id, job_id=job.id, attempt_no=1, state='queued'))
        db.add(JobEvent(job_id=job.id, attempt_id=attempt_id, event_type='accepted', payload={}))
        db.add(Outbox(job_id=job.id, attempt_id=attempt_id))
        return job_data(job)
