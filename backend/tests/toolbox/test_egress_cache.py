import asyncio

import httpx
import pytest

from app.toolbox.runtime import egress


@pytest.fixture
def resolver(monkeypatch):
    egress._doh_cache.clear()
    state = {"calls": 0, "ip": "8.8.8.8", "ttl": 20}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            state["calls"] += 1
            return httpx.Response(200, request=httpx.Request("GET", url), json={"Answer": [{"type": 1, "data": state["ip"], "TTL": state["ttl"]}]})

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    yield state
    egress._doh_cache.clear()


def lookup(endpoint="https://resolver.example/dns"):
    return asyncio.run(egress.resolve_doh("video.example", endpoint))


def test_repeated_lookup_reuses_only_live_public_answer(resolver):
    assert lookup() == lookup() == ["8.8.8.8"]
    assert resolver["calls"] == 1
    key = next(iter(egress._doh_cache))
    egress._doh_cache[key] = (0, ("8.8.8.8",))
    resolver["ip"] = "1.1.1.1"
    assert lookup() == ["1.1.1.1"]
    assert resolver["calls"] == 2


def test_expired_answer_cannot_hide_private_dns_change(resolver):
    lookup()
    key = next(iter(egress._doh_cache))
    egress._doh_cache[key] = (0, ("8.8.8.8",))
    resolver["ip"] = "127.0.0.1"
    with pytest.raises(ValueError, match="private"):
        lookup()
    assert not egress._doh_cache


def test_zero_ttl_not_cached_and_resolvers_are_isolated(resolver):
    resolver["ttl"] = 0
    lookup()
    lookup()
    assert resolver["calls"] == 2
    resolver["ttl"] = 20
    lookup()
    lookup("https://other.example/dns")
    assert resolver["calls"] == 4


def test_repeated_lookup_cannot_extend_ttl(resolver):
    lookup()
    original = next(iter(egress._doh_cache.values()))[0]
    lookup()
    assert next(iter(egress._doh_cache.values()))[0] == original


def test_resolver_split_respects_domain_boundaries(monkeypatch):
    monkeypatch.setenv("TB_EGRESS_DOH", "https://global.example/resolve")
    monkeypatch.setenv("TB_EGRESS_DOMESTIC_DOH", "https://local.example/resolve")
    monkeypatch.delenv("TB_EGRESS_DOMESTIC_DOMAINS", raising=False)
    for host in ("bilibili.com", "API.BILIBILI.COM.", "cn.example.bilivideo.cn", "a.bilivideo.com"):
        assert egress.doh_endpoint(host) == "https://local.example/resolve"
    for host in ("youtube.com", "evilbilibili.com", "bilibili.com.evil.example", "127.0.0.1"):
        assert egress.doh_endpoint(host) == "https://global.example/resolve"


def test_resolver_split_is_optional_and_operator_configurable(monkeypatch):
    monkeypatch.setenv("TB_EGRESS_DOH", "https://global.example/resolve")
    monkeypatch.delenv("TB_EGRESS_DOMESTIC_DOH", raising=False)
    assert egress.doh_endpoint("api.bilibili.com") == "https://global.example/resolve"
    monkeypatch.setenv("TB_EGRESS_DOMESTIC_DOH", "https://local.example/resolve")
    monkeypatch.setenv("TB_EGRESS_DOMESTIC_DOMAINS", " example.org, ")
    assert egress.doh_endpoint("cdn.example.org") == "https://local.example/resolve"
    assert egress.doh_endpoint("api.bilibili.com") == "https://global.example/resolve"


@pytest.mark.parametrize("dns_address", ["198.18.0.8", "127.0.0.1", "8.8.8.8"])
def test_split_still_pins_public_ip_and_rejects_private_dns(monkeypatch, dns_address):
    monkeypatch.setenv("TB_EGRESS_DOH", "https://global.example/resolve")
    monkeypatch.setenv("TB_EGRESS_DOMESTIC_DOH", "https://local.example/resolve")
    monkeypatch.delenv("TB_EGRESS_DOMESTIC_DOMAINS", raising=False)
    lookups, connections = [], []

    async def lookup(host, endpoint):
        lookups.append((host, endpoint))
        return ["1.1.1.1"]

    async def open_connection(ip, port):
        connections.append((ip, port))
        return "reader", "writer"

    async def resolve(*args, **kwargs):
        return [(2, 1, 6, "", (dns_address, 443))]

    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        monkeypatch.setattr(egress, "resolve_doh", lookup)
        monkeypatch.setattr(asyncio, "open_connection", open_connection)
        if dns_address == "127.0.0.1":
            with pytest.raises(ValueError, match="private"):
                await egress.connect_public("api.bilibili.com", 443)
            assert not connections and not lookups
        else:
            assert await egress.connect_public("api.bilibili.com", 443) == ("reader", "writer")
            assert connections == [("1.1.1.1" if dns_address.startswith("198.18.") else dns_address, 443)]
            assert lookups == ([("api.bilibili.com", "https://local.example/resolve")] if dns_address.startswith("198.18.") else [])

    asyncio.run(run())


@pytest.mark.parametrize(("host", "port", "address", "allowed"), [
    ("xy113x207x85x202xy.mcdn.bilivideo.cn", 8082, "8.8.8.8", True),
    ("XY113.MCDN.BILIVIDEO.CN.", 8082, "8.8.8.8", True),
    ("xy113.mcdn.bilivideo.cn", 8082, "127.0.0.1", False),
    ("xy113.mcdn.bilivideo.cn", 8082, "192.168.1.1", False),
    ("xy113.mcdn.bilivideo.cn", 3306, "8.8.8.8", False),
    ("mcdn.bilivideo.cn.attacker.example", 8082, "8.8.8.8", False),
    ("evilmcdn.bilivideo.cn", 8082, "8.8.8.8", False),
    ("example.com", 8082, "8.8.8.8", False),
    ("8.8.8.8", 8082, "8.8.8.8", False),
])
def test_bilibili_media_port_keeps_host_and_ip_boundaries(monkeypatch, host, port, address, allowed):
    connections = []
    async def resolve(*args, **kwargs):
        return [(2, 1, 6, "", (address, port))]
    async def connect(ip, target_port):
        connections.append((ip, target_port))
        return "reader", "writer"
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        monkeypatch.setattr(asyncio, "open_connection", connect)
        if allowed:
            assert await egress.connect_public(host, port) == ("reader", "writer")
            assert connections == [(address, port)]
        else:
            with pytest.raises(ValueError):
                await egress.connect_public(host, port)
            assert not connections
    asyncio.run(run())
