from app.core.router_class import OperationLogRoute
from fastapi import APIRouter, Depends
from sqlalchemy import text, select, func

from app.toolbox.api.dependencies import redis, administrator
from app.toolbox.models.entities import WorkerHeartbeat
from app.toolbox.registry.catalog import REGISTRY_HASH, TOOLS
from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.storage.s3 import client

router = APIRouter(route_class=OperationLogRoute)


@router.get("/health")
def health():
    with transaction() as db:
        db.execute(text("SELECT 1"))
    redis.ping()
    client().head_bucket(Bucket=settings().s3_bucket)
    return {"status": "ok", "version": "0.2.0", "foundation": "FastapiAdmin"}


@router.get('/admin/runtime')
def runtime_status(user=Depends(administrator)):
    required = sorted({tool['resource_profile'] for tool in TOOLS if tool['mode'] == 'job'})
    with transaction() as db:
        workers = db.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.expires_at > func.utc_timestamp())).all()
        available = {w.resource_profile for w in workers if w.registry_hash == REGISTRY_HASH}
        return {'registry_hash': REGISTRY_HASH, 'ready': set(required) <= available,
                'profiles': [{'name': name, 'ready': name in available} for name in required],
                'workers': [{'id': w.worker_id, 'profile': w.resource_profile,
                             'compatible': w.registry_hash == REGISTRY_HASH, 'heartbeat_at': w.heartbeat_at} for w in workers]}
