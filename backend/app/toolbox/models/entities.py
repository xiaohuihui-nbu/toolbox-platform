from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

# Reuse the upstream declarative base and named constraints. No second ORM.
from app.core.base_model import MappedBase
from app.toolbox.models.identity import User


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def uid():
    return str(uuid4())


class UserProfile(MappedBase):
    __tablename__ = "tb_user_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id", ondelete="CASCADE"), primary_key=True)
    legacy_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class Job(MappedBase):
    __tablename__ = "tb_jobs"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"), Index("ix_tb_job_owner_created", "owner_id", "created_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    tool_id: Mapped[str] = mapped_column(String(64))
    tool_version: Mapped[str] = mapped_column(String(16), default="1.0.0")
    plugin_id: Mapped[str] = mapped_column(String(64), default="")
    plugin_version: Mapped[str] = mapped_column(String(32), default="")
    schema_hash: Mapped[str] = mapped_column(String(64), default="")
    resource_profile: Mapped[str] = mapped_column(String(32), default="media_cpu")
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    parent_job_id: Mapped[str | None] = mapped_column(ForeignKey("tb_jobs.id", ondelete="SET NULL"))
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    title: Mapped[str] = mapped_column(String(200))
    params: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[str | None] = mapped_column(String(36))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    message: Mapped[str] = mapped_column(Text, default="等待执行")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Outbox(MappedBase):
    __tablename__ = "tb_outbox"
    job_id: Mapped[str] = mapped_column(ForeignKey("tb_jobs.id"), primary_key=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempt_id: Mapped[str | None] = mapped_column(String(36))
    not_before: Mapped[datetime] = mapped_column(DateTime, default=now)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    deliveries: Mapped[int] = mapped_column(Integer, default=0)


class JobAttempt(MappedBase):
    __tablename__ = "tb_job_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_no"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("tb_jobs.id", ondelete="CASCADE"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(24), default="queued")
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(64))
    provider_job_id: Mapped[str | None] = mapped_column(String(128))


class JobEvent(MappedBase):
    __tablename__ = "tb_job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("tb_jobs.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[str | None] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class WorkerHeartbeat(MappedBase):
    __tablename__ = "tb_worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    resource_profile: Mapped[str] = mapped_column(String(32), index=True)
    registry_hash: Mapped[str] = mapped_column(String(64))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Asset(MappedBase):
    __tablename__ = "tb_assets"
    __table_args__ = (Index("ix_tb_asset_owner_created", "owner_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("tb_jobs.id"))
    name: Mapped[str] = mapped_column(String(200))
    object_key: Mapped[str] = mapped_column(String(255), unique=True)
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ToolSetting(MappedBase):
    __tablename__ = "tb_tool_settings"
    tool_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
