import json
from unittest.mock import patch

import httpx
import pytest

from app.toolbox.search.videos import execute_search, search, search_error


def test_anonymous_bilibili_search_and_normalized_results():
    def respond(request):
        assert "cookie" not in request.headers
        assert request.headers["referer"] == "https://www.bilibili.com/"
        assert request.url.params["keyword"] == "舞蹈"
        return httpx.Response(200, json={"code": 0, "data": {"result": [
            {"title": '<em class="keyword">舞蹈</em> &amp; 音乐',
             "arcurl": "http://www.bilibili.com/video/BV1test", "author": "作者",
             "pic": "//i0.hdslb.com/test.jpg", "duration": "3:20"},
            {"title": "广告", "arcurl": "https://example.invalid/"},
        ]}})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    with patch("app.toolbox.search.videos.httpx.Client", return_value=client):
        items = search("舞蹈", "bilibili", 8)
    assert len(items) == 1
    assert items[0]["title"] == "舞蹈 & 音乐"
    assert items[0]["url"].startswith("https://www.bilibili.com/video/")
    assert items[0]["thumbnail_source"] == "https://i0.hdslb.com/test.jpg"


@pytest.mark.parametrize("status", [401, 403, 412, 429, 502])
def test_http_failures_are_specific_and_do_not_expose_request(status):
    response = httpx.Response(status, request=httpx.Request("GET", "https://example.invalid/?token=SECRET"))
    with pytest.raises(httpx.HTTPStatusError) as error:
        response.raise_for_status()
    message = search_error(error.value, "bilibili")
    assert str(status) in message
    assert "SECRET" not in message


def test_timeout_is_not_reported_as_zero_results():
    assert "超时" in search_error(httpx.ReadTimeout("SECRET"), "youtube")


def test_source_restriction_is_not_an_empty_success():
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"code": -412})))
    with patch("app.toolbox.search.videos.httpx.Client", return_value=client):
        with pytest.raises(ValueError, match="限制"):
            search("舞蹈", "bilibili", 8)


def test_search_ticket_records_failure_for_polling():
    class MemoryStore:
        payload = None

        def get(self, key):
            if key.startswith("tb:search-cache:"):
                return None
            return json.dumps({"state": "queued", "platform": "bilibili", "query": "舞蹈", "limit": 8, "items": []})

        def set(self, *args, **kwargs):
            return True

        def setex(self, key, ttl, payload):
            self.payload = json.loads(payload)

    store = MemoryStore()
    response = httpx.Response(412, request=httpx.Request("GET", "https://api.bilibili.com/"))
    failure = httpx.HTTPStatusError("denied", request=response.request, response=response)
    with patch("app.toolbox.search.videos.store", return_value=store), patch("app.toolbox.search.videos.search", side_effect=failure):
        execute_search("test-ticket")
    assert store.payload["state"] == "failed"
    assert "412" in store.payload["error"]
    assert store.payload["items"] == []


def test_success_cache_reuses_results_without_sharing_ticket_owner():
    class MemoryStore:
        def __init__(self):
            self.values = {}
            self.ttls = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, *args, **kwargs):
            return True

        def setex(self, key, ttl, value):
            self.values[key] = value
            self.ttls[key] = ttl

    store = MemoryStore()
    for ticket, owner in [("one", "alice"), ("two", "bob")]:
        store.values["tb:search:" + ticket] = json.dumps({"state": "queued", "owner_id": owner, "query": "舞蹈", "platform": "bilibili", "limit": 8, "items": []})
    items = [{"title": "公开结果", "url": "https://www.bilibili.com/video/BV1test"}]
    with patch("app.toolbox.search.videos.store", return_value=store), patch("app.toolbox.search.videos.search", return_value=items) as upstream:
        execute_search("one")
        execute_search("two")
    upstream.assert_called_once()
    assert json.loads(store.values["tb:search:one"])["owner_id"] == "alice"
    assert json.loads(store.values["tb:search:two"])["owner_id"] == "bob"
    assert json.loads(store.values["tb:search:two"])["items"] == items
    cache = next(key for key in store.values if key.startswith("tb:search-cache:"))
    assert store.ttls[cache] == 120
    assert "owner_id" not in store.values[cache]
