import json

from fastapi import HTTPException

from app.toolbox.search.videos import store


def owned_search(search_id, owner_id):
    raw = store().get("tb:search:" + search_id)
    payload = json.loads(raw) if raw else None
    if not payload or payload["owner_id"] != owner_id:
        raise HTTPException(404, "搜索结果不存在或已过期")
    return payload
