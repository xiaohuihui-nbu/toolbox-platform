from app.core.router_class import OperationLogRoute
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from app.toolbox.api.dependencies import current_user

router = APIRouter(route_class=OperationLogRoute)


@router.get("/tts/status")
def tts_status(user=Depends(current_user)):
    from app.toolbox.providers.gptsovits import provider_get

    try:
        data = provider_get("/health").json()
        return {"status": data.get("status", "unavailable"), "model": data.get("model"), "queued": data.get("queued", 0)}
    except (httpx.HTTPError, ValueError):
        return {"status": "unavailable", "model": "GPT-SoVITS v2ProPlus", "queued": 0}


@router.get("/tts/voices")
def tts_voices(user=Depends(current_user)):
    from app.toolbox.providers.gptsovits import provider_get

    try:
        return [{k: voice.get(k) for k in ("id", "name", "description", "gender")} for voice in provider_get("/api/voices").json()]
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "音色服务暂不可用，请启动 GPT-SoVITS")


@router.get("/tts/voices/{voice_id}/preview")
def voice_preview(voice_id: str, user=Depends(current_user)):
    from app.toolbox.providers.gptsovits import provider_get

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", voice_id):
        raise HTTPException(404)
    try:
        response = provider_get(f"/api/voices/{voice_id}/preview")
        return Response(response.content, media_type="audio/wav")
    except httpx.HTTPError:
        raise HTTPException(503, "参考音暂不可用")
