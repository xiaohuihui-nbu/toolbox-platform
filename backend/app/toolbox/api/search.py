from app.core.router_class import OperationLogRoute
import json
import time
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from app.toolbox.api.dependencies import current_user, redis, require_tool
from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import ToolSetting
from app.toolbox.schemas.http import VideoSearchInput
from app.toolbox.search.tickets import owned_search

router = APIRouter(route_class=OperationLogRoute)


@router.post("/video-search", status_code=202)
def create_video_search(data: VideoSearchInput, user=Depends(current_user)):
    require_tool(user, "video.download")
    from workers.tasks import search_videos

    if not data.query.strip():
        raise HTTPException(422, "请输入搜索关键词")
    with transaction() as db:
        flag = db.get(ToolSetting, "video.download")
        if flag and not flag.enabled:
            raise HTTPException(409, "视频工具已被停用")
    throttle = "tb:search-rate:" + str(user.id)
    count = redis.incr(throttle)
    if count == 1:
        redis.expire(throttle, 60)
    if count > 6:
        raise HTTPException(429, "搜索较频繁，请一分钟后再试")
    search_id = str(uuid4())
    payload = {**data.model_dump(), "id": search_id, "owner_id": user.id, "state": "queued", "created": time.time(), "items": []}
    redis.setex("tb:search:" + search_id, 900, json.dumps(payload))
    try:
        search_videos.apply_async(args=[search_id], queue="toolbox-search")
    except Exception:
        redis.delete("tb:search:" + search_id)
        raise HTTPException(503, "搜索队列暂不可用")
    return {"id": search_id, "state": "queued"}


@router.get("/video-search/{search_id}")
def get_video_search(search_id: str, user=Depends(current_user)):
    payload = owned_search(search_id, user.id)
    if payload["state"] in {"queued", "running"} and time.time() - payload["created"] > 100:
        return {"id": search_id, "state": "failed", "items": [], "error": "搜索超时，请稍后重新搜索"}
    return {
        "id": search_id,
        "state": payload["state"],
        "error": payload.get("error"),
        "items": [
            {**{k: v for k, v in item.items() if k != "thumbnail_source"}, "thumbnail": f"/api/video-search/{search_id}/items/{index}/thumbnail" if item.get("thumbnail_source") else None}
            for index, item in enumerate(payload["items"])
        ],
    }


@router.get("/video-search/{search_id}/items/{index}/thumbnail")
def search_thumbnail(search_id: str, index: int, user=Depends(current_user)):
    data = owned_search(search_id, user.id)
    if index < 0 or index >= len(data["items"]):
        raise HTTPException(404)
    url = data["items"][index].get("thumbnail_source", "")
    if not url.startswith(("https://", "http://")):
        raise HTTPException(404)
    try:
        with httpx.Client(proxy=settings().download_proxy, timeout=12, trust_env=False, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                mime = response.headers.get("content-type", "").split(";")[0]
                if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                    raise HTTPException(415)
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 1500000:
                        raise HTTPException(413)
                return Response(bytes(content), media_type=mime)
    except httpx.HTTPError:
        raise HTTPException(502, "缩略图暂不可用")
