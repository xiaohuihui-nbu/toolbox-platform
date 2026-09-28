"""Fixed-origin relay for the existing host TTS service; never an arbitrary URL proxy."""

import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

app = FastAPI(docs_url=None, openapi_url=None)
ORIGIN = os.getenv("TB_GPTSOVITS_ORIGIN", "http://host.docker.internal:9880").rstrip("/")


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def relay(path: str, request: Request):
    allowed = (
        re.fullmatch(r"health|api/voices|api/voices/[a-zA-Z0-9_-]+/preview|api/jobs/[a-f0-9]{32}|audio/[a-f0-9]{32}-(?:full|[0-9]+)-[a-f0-9]{8}\.(?:wav|mp3)", path)
        if request.method == "GET"
        else re.fullmatch(r"api/jobs|api/jobs/[a-f0-9]{32}/cancel", path)
    )
    if not allowed:
        raise HTTPException(404)
    body = await request.body()
    if len(body) > 20000:
        raise HTTPException(413)
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False) as client:
            async with client.stream(request.method, ORIGIN + "/" + path, content=body, headers={"Content-Type": "application/json"}) as result:
                chunks, total = [], 0
                async for chunk in result.aiter_bytes():
                    total += len(chunk)
                    if total > 100 * 1024 * 1024:
                        raise HTTPException(413, "引擎文件超过上限")
                    chunks.append(chunk)
                return Response(b"".join(chunks), status_code=result.status_code, media_type=result.headers.get("content-type", "application/json"))
    except httpx.HTTPError:
        raise HTTPException(503, "GPT-SoVITS 服务暂不可用，请启动本机配音服务")
