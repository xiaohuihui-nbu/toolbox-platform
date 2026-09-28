"""Short-lived, owner-scoped search results. Download jobs remain durable in MySQL."""

import html
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
from redis import Redis

from app.toolbox.config import settings


def store():
    return Redis.from_url(settings().redis_url, decode_responses=True)


def search(query, platform, limit):
    if platform == "bilibili":
        with httpx.Client(proxy=settings().download_proxy, timeout=20, trust_env=False) as client:
            response = client.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params={"keyword": query, "search_type": "video", "page": 1, "highlight": 0},
                # Anonymous public search: do not invent a device/session Cookie.
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"},
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") in {-352, -412, -403}:
                raise ValueError("B站暂时限制了搜索访问，请稍后重试；也可粘贴视频链接尝试下载")
            if data.get("code") != 0:
                raise ValueError("B站搜索暂不可用，请稍后重试或切换平台")
            return [
                {
                    "title": html.unescape(re.sub(r"<[^>]+>", "", item.get("title", "视频"))),
                    "url": item["arcurl"].replace("http://", "https://", 1),
                    "uploader": item.get("author", ""),
                    "duration": item.get("duration", ""),
                    "thumbnail_source": "https:" + item["pic"] if item.get("pic", "").startswith("//") else item.get("pic", ""),
                    "platform": platform,
                }
                for item in data.get("data", {}).get("result", [])[:limit]
                if item.get("arcurl", "").startswith(("http://www.bilibili.com/video/", "https://www.bilibili.com/video/"))
            ]
    with tempfile.TemporaryDirectory(prefix="tb-search-") as temp:
        output = Path(temp) / "search.json"
        with output.open("wb") as target:
            process = subprocess.run(
                [
                    "yt-dlp",
                    "--ignore-config",
                    "--proxy",
                    settings().download_proxy,
                    "--flat-playlist",
                    "--dump-single-json",
                    "--skip-download",
                    "--socket-timeout",
                    "12",
                    "--retries",
                    "0",
                    "--",
                    f"ytsearch{limit}:{query}",
                ],
                stdout=target,
                stderr=subprocess.DEVNULL,
                timeout=50,
                check=False,
            )
        if process.returncode or output.stat().st_size > 3 * 1024 * 1024:
            raise ValueError("YouTube 搜索暂不可用，请稍后重试或切换平台")
        data = json.loads(output.read_text(encoding="utf-8"))
    return [
        {
            "title": entry.get("title") or "视频",
            "url": entry["url"],
            "uploader": entry.get("channel") or entry.get("uploader") or "",
            "duration": entry.get("duration"),
            "thumbnail_source": (entry.get("thumbnails") or [{}])[-1].get("url", ""),
            "platform": platform,
        }
        for entry in data.get("entries", [])[:limit]
        if entry and entry.get("url", "").startswith("https://www.youtube.com/watch?")
    ]


def search_error(exc, platform):
    name = "B站" if platform == "bilibili" else "YouTube"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403, 412}:
            return f"{name}拒绝了搜索请求（HTTP {status}），请稍后重试；也可粘贴视频链接尝试下载"
        if status == 429:
            return f"{name}搜索请求过于频繁（HTTP 429），请稍后再试"
        return f"{name}搜索服务暂不可用（HTTP {status}），请稍后再试"
    if isinstance(exc, (httpx.TimeoutException, subprocess.TimeoutExpired)):
        return f"{name}搜索连接超时，请稍后重试或切换平台"
    if isinstance(exc, httpx.RequestError):
        return f"无法连接{name}搜索服务，请稍后重试或检查服务器网络"
    if isinstance(exc, json.JSONDecodeError):
        return f"{name}搜索返回了异常响应，请稍后再试"
    return str(exc) if isinstance(exc, ValueError) else "搜索平台请求失败，请稍后再试"


def execute_search(search_id):
    redis = store()
    key = "tb:search:" + search_id
    raw = redis.get(key)
    if not raw:
        return
    payload = json.loads(raw)
    if payload["state"] != "queued":
        return
    # Search is disposable and safe to retry, but duplicate deliveries still avoid parallel work.
    if not redis.set("tb:search-lock:" + search_id, "1", nx=True, ex=90):
        return
    payload["state"] = "running"
    redis.setex(key, 900, json.dumps(payload))
    try:
        # Only public anonymous metadata is shared; tickets and thumbnails stay owner-scoped.
        query = payload["query"].strip()
        cache_key = "tb:search-cache:v1:" + hashlib.sha256(
            json.dumps([payload["platform"], query, payload["limit"]], ensure_ascii=False).encode()
        ).hexdigest()
        cached = redis.get(cache_key)
        if cached is not None:
            payload["items"] = json.loads(cached)
        else:
            payload["items"] = search(query, payload["platform"], payload["limit"])
            redis.setex(cache_key, 120, json.dumps(payload["items"]))
        payload["state"] = "succeeded"
    except Exception as exc:
        payload["state"] = "failed"
        payload["error"] = search_error(exc, payload["platform"])
    redis.setex(key, 900, json.dumps(payload))
