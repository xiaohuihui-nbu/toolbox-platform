import mimetypes
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from sqlalchemy import func, select

from app.toolbox.config import settings
from app.toolbox.models.entities import Asset, User


def client():
    cfg = settings()
    return boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=30),
    )


def prepare_output(path: Path, owner_id: int, name: str, job_id: str, attempt_id: str):
    """Upload an immutable attempt object outside the database transaction."""
    import hashlib

    asset_id = str(uuid4())
    safe_name = Path(name.replace("\\", "/")).name[:180] or "output.bin"
    key = f"users/{owner_id}/jobs/{job_id}/attempts/{attempt_id}/{asset_id}"
    mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    size = path.stat().st_size
    with path.open('rb') as source:
        checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    storage = client()
    storage.upload_file(str(path), settings().s3_bucket, key,
                        ExtraArgs={"ContentType": mime, "Metadata": {"sha256": checksum}})
    head = storage.head_object(Bucket=settings().s3_bucket, Key=key)
    if head['ContentLength'] != size or head['Metadata'].get('sha256') != checksum:
        storage.delete_object(Bucket=settings().s3_bucket, Key=key)
        raise ValueError("产物上传校验失败")
    return Asset(id=asset_id, owner_id=owner_id, job_id=job_id, name=safe_name,
                 object_key=key, size=size, mime=mime)


def check_storage_quota(db, owner_id: int, size: int):
    db.execute(select(User).where(User.id == owner_id).with_for_update()).scalar_one()
    used = db.scalar(select(func.coalesce(func.sum(Asset.size), 0)).where(Asset.owner_id == owner_id))
    if used + size > settings().user_storage_mb * 1024 * 1024:
        raise ValueError("个人文件空间已满，请联系管理员清理或扩容")


def save_file(db, path: Path, owner_id: int, name: str, job_id=None):
    # Serialize quota checks for an owner, including simultaneous worker outputs.
    size = path.stat().st_size
    check_storage_quota(db, owner_id, size)
    asset_id = str(uuid4())
    safe_name = Path(name.replace("\\", "/")).name[:180] or "output.bin"
    key = f"users/{owner_id}/{asset_id}/{safe_name}"
    mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    client().upload_file(str(path), settings().s3_bucket, key, ExtraArgs={"ContentType": mime})
    asset = Asset(id=asset_id, owner_id=owner_id, job_id=job_id, name=safe_name, object_key=key, size=size, mime=mime)
    db.add(asset)
    db.flush()
    return asset
