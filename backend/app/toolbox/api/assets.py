from app.core.router_class import OperationLogRoute
import tempfile
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.toolbox.api.dependencies import current_user
from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset
from app.toolbox.services.presenters import asset_data
from app.toolbox.storage.media import PREVIEW_MIMES, byte_range
from app.toolbox.storage.s3 import client, save_file

router = APIRouter(route_class=OperationLogRoute)


@router.get("/assets")
def assets(page: int = 1, user=Depends(current_user)):
    if page < 1 or page > 10000:
        raise HTTPException(400, "页码无效")
    with transaction() as db:
        return [asset_data(a) for a in db.scalars(select(Asset).where(Asset.owner_id == user.id).order_by(Asset.created_at.desc()).offset((page - 1) * 50).limit(50)).all()]


@router.post("/assets", status_code=201)
def upload(file: Annotated[UploadFile, File()], user=Depends(current_user)):
    with tempfile.TemporaryDirectory(prefix="tb-upload-") as temp:
        path = Path(temp) / "upload"
        count = 0
        with path.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                count += len(chunk)
                if count > settings().max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "单个文件不能超过 100 MB")
                target.write(chunk)
        if not count:
            raise HTTPException(400, "不能上传空文件")
        try:
            with transaction() as db:
                return asset_data(save_file(db, path, user.id, file.filename or "upload.bin"))
        except ValueError as exc:
            raise HTTPException(409, str(exc))


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: str, user=Depends(current_user)):
    with transaction() as db:
        asset = db.get(Asset, asset_id)
        if not asset or asset.owner_id != user.id:
            raise HTTPException(404, "文件不存在")
        return asset_data(asset)


@router.api_route("/assets/{asset_id}/preview", methods=["GET", "HEAD"])
def preview_asset(asset_id: str, request: Request, user=Depends(current_user)):
    with transaction() as db:
        asset = db.get(Asset, asset_id)
        if not asset or asset.owner_id != user.id:
            raise HTTPException(404, "文件不存在")
        if asset.mime not in PREVIEW_MIMES:
            raise HTTPException(415, "此文件类型不支持在线预览，请下载后打开")
    etag = '"' + asset.id + '"'
    range_header = request.headers.get("range") if request.method == "GET" else None
    if request.headers.get("if-range") not in {None, etag}:
        range_header = None
    try:
        selected_range = byte_range(range_header, asset.size)
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{asset.size}", "Accept-Ranges": "bytes"})
    start, end = selected_range or (0, asset.size - 1)
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1), "Content-Disposition": "inline; filename*=UTF-8''" + quote(asset.name), "ETag": etag}
    if selected_range:
        headers["Content-Range"] = f"bytes {start}-{end}/{asset.size}"
    status = 206 if selected_range else 200
    if request.method == "HEAD":
        return Response(status_code=status, media_type=asset.mime, headers=headers)
    options = {"Range": f"bytes={start}-{end}"} if selected_range else {}
    body = client().get_object(Bucket=settings().s3_bucket, Key=asset.object_key, **options)["Body"]

    def chunks():
        try:
            yield from body.iter_chunks(256 * 1024)
        finally:
            body.close()

    return StreamingResponse(chunks(), status_code=status, media_type=asset.mime, headers=headers)


@router.get("/assets/{asset_id}/download")
def download_asset(asset_id: str, user=Depends(current_user)):
    with transaction() as db:
        asset = db.get(Asset, asset_id)
        if not asset or asset.owner_id != user.id:
            raise HTTPException(404, "文件不存在")
    obj = client().get_object(Bucket=settings().s3_bucket, Key=asset.object_key)
    body = obj["Body"]

    def chunks():
        try:
            yield from body.iter_chunks(1024 * 256)
        finally:
            body.close()

    return StreamingResponse(chunks(), media_type="application/octet-stream", headers={"Content-Length": str(asset.size), "Content-Disposition": "attachment; filename*=UTF-8''" + quote(asset.name)})
