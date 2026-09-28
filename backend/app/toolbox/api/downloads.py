from app.core.router_class import OperationLogRoute
import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.toolbox.api.dependencies import current_user
from app.toolbox.schemas.http import BatchVideoInput, JobInput
from app.toolbox.services.jobs import submit

router = APIRouter(route_class=OperationLogRoute)


@router.post("/video-downloads/batch", status_code=202)
def batch_video_download(data: BatchVideoInput, idempotency_key: Annotated[str, Header(min_length=8, max_length=64)], user=Depends(current_user)):
    items, seen = [], set()
    for index, item in enumerate(data.items):
        url = item.url.strip()
        if url in seen:
            items.append({"url": url, "state": "duplicate", "message": "本批次重复链接已跳过"})
            continue
        seen.add(url)
        key = hashlib.sha256(f"batch:{idempotency_key}:{index}".encode()).hexdigest()
        try:
            job = submit(JobInput(tool_id="video.download", params={"url": url, "title": item.title, "quality": data.quality}), key, user)
            items.append({"url": url, "state": "accepted", "job": job})
        except HTTPException as exc:
            items.append({"url": url, "state": "rejected", "status": exc.status_code, "message": str(exc.detail)})
    return {
        "items": items,
        "accepted": sum(item["state"] == "accepted" for item in items),
        "rejected": sum(item["state"] == "rejected" for item in items),
        "duplicates": sum(item["state"] == "duplicate" for item in items),
    }
