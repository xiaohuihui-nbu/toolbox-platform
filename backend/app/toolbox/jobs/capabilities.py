"""Database-clock worker availability and immutable registry fingerprint."""
import logging
import os
import threading
from datetime import timedelta

from celery.signals import worker_ready, worker_shutdown
from fastapi import HTTPException
from sqlalchemy import func, select

from app.toolbox.models.database import transaction
from app.toolbox.models.entities import WorkerHeartbeat
from app.toolbox.registry.catalog import REGISTRY_HASH

_stop = threading.Event()


def db_now(db):
    return db.scalar(select(func.utc_timestamp()))


def require_worker(db, profile):
    worker = db.scalar(select(WorkerHeartbeat.worker_id).where(
        WorkerHeartbeat.resource_profile == profile,
        WorkerHeartbeat.registry_hash == REGISTRY_HASH,
        WorkerHeartbeat.expires_at > func.utc_timestamp()).limit(1))
    if not worker:
        raise HTTPException(503, "对应工具执行器尚未就绪或版本不匹配，请稍后重试")


@worker_ready.connect
def announce_worker(sender=None, **kwargs):
    profile = os.getenv('TB_RESOURCE_PROFILE', 'media_cpu')
    if profile == 'search':
        return
    worker_id = sender.hostname
    def publish():
        while not _stop.is_set():
            try:
                with transaction() as db:
                    current = db_now(db)
                    db.merge(WorkerHeartbeat(worker_id=worker_id, resource_profile=profile,
                        registry_hash=REGISTRY_HASH, heartbeat_at=current, expires_at=current + timedelta(seconds=35)))
            except Exception:
                logging.exception('worker capability heartbeat failed')
            _stop.wait(10)
    threading.Thread(target=publish, daemon=True).start()


@worker_shutdown.connect
def stop_worker(**kwargs):
    _stop.set()
