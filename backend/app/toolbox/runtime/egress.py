"""Restricted HTTP proxy: resolve once, reject every non-global address, connect to pinned IP.

The downloader must route extraction AND media requests through this proxy. Workers are
on an internal Docker network; only this service has a network with Internet routing.
"""

import asyncio
import ipaddress
import os
import socket
import time
from collections import OrderedDict
from urllib.parse import urlsplit

_doh_cache = OrderedDict()
DOMESTIC_DOMAINS = "bilibili.com,bilivideo.com,bilivideo.cn,biliimg.com,hdslb.com,b23.tv"


def doh_endpoint(host):
    """Choose an operator-configured resolver using exact DNS label boundaries."""
    domestic = os.getenv("TB_EGRESS_DOMESTIC_DOH", "").strip()
    normalized = host.lower().rstrip(".")
    if domestic:
        suffixes = os.getenv("TB_EGRESS_DOMESTIC_DOMAINS", DOMESTIC_DOMAINS).split(",")
        for suffix in suffixes:
            suffix = suffix.strip().lower().strip(".")
            if suffix and (normalized == suffix or normalized.endswith("." + suffix)):
                return domestic
    return os.getenv("TB_EGRESS_DOH", "")


async def resolve_doh(host, endpoint):
    """Cache validated public answers for at most 30 seconds and never past DNS TTL."""
    import httpx

    key = (host.lower(), endpoint)
    cached = _doh_cache.get(key)
    if cached and cached[0] > time.monotonic():
        _doh_cache.move_to_end(key)
        return list(cached[1])
    _doh_cache.pop(key, None)
    async with httpx.AsyncClient(timeout=15, trust_env=False) as http:
        response = await http.get(endpoint, params={"name": host, "type": "A"})
        response.raise_for_status()
        answers = [answer for answer in response.json().get("Answer", []) if answer.get("type") == 1]
    addresses = [answer["data"] for answer in answers]
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("private address denied")
    ttl = min(30, *(max(0, int(answer.get("TTL", 0))) for answer in answers))
    if ttl:
        _doh_cache[key] = (time.monotonic() + ttl, tuple(addresses))
        while len(_doh_cache) > 256:
            _doh_cache.popitem(last=False)
    return addresses


async def connect_public(host, port):
    # Bilibili's media CDN also serves HTTPS on 8082. Keep this exception
    # limited to the observed CDN DNS suffix; public-IP pinning still applies.
    normalized = host.lower().rstrip(".")
    bili_media = normalized.endswith(".mcdn.bilivideo.cn")
    if port not in (80, 443) and not (port == 8082 and bili_media):
        raise ValueError("port denied")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    doh = doh_endpoint(host)
    if literal:
        addresses = [str(literal)]
    else:
        records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(record[4][0] for record in records))
        # Only the explicitly configured TUN fake-IP range may trigger DoH.
        # Ordinary internal DNS answers are rejected without any external lookup.
        if doh and addresses and all(ipaddress.ip_address(address) in ipaddress.ip_network("198.18.0.0/15") for address in addresses):
            addresses = await resolve_doh(host, doh)
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("private address denied")
    for ip in addresses[:3]:
        try:
            return await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=5)
        except (OSError, TimeoutError):
            continue
    raise ValueError("public host unreachable")


async def proxy(reader, writer):
    remote = None
    try:
        header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
        if len(header) > 16384:
            raise ValueError("header too large")
        line, *headers = header.decode("latin1").split("\r\n")
        method, target, version = line.split(" ", 2)
        parsed = urlsplit("https://" + target if method == "CONNECT" else target)
        if parsed.username or parsed.password or not parsed.hostname:
            raise ValueError("invalid target")
        if method == "CONNECT":
            port = parsed.port or 443
        elif method in {"GET", "HEAD"} and parsed.scheme == "http":
            port = parsed.port or 80
        else:
            raise ValueError("method denied")
        remote_reader, remote = await connect_public(parsed.hostname, port)
        if method == "CONNECT":
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        else:
            clean = [h for h in headers if h and h.split(":", 1)[0].lower() not in {"host", "connection", "proxy-connection", "proxy-authorization", "transfer-encoding", "content-length"}]
            path = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
            payload = f"{method} {path} HTTP/1.1\r\nHost: {parsed.netloc}\r\nConnection: close\r\n" + "\r\n".join(clean) + "\r\n\r\n"
            remote.write(payload.encode("latin1"))
            await remote.drain()
        await writer.drain()

        async def pipe(source, destination):
            count = 0
            while block := await source.read(65536):
                count += len(block)
                if count > 220 * 1024 * 1024:
                    return
                destination.write(block)
                await destination.drain()

        tasks = [asyncio.create_task(pipe(reader, remote)), asyncio.create_task(pipe(remote_reader, writer))]
        try:
            await asyncio.wait(tasks, timeout=620, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        try:
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        except Exception:
            pass
    finally:
        if remote:
            remote.close()
        writer.close()


async def main():
    server = await asyncio.start_server(proxy, "0.0.0.0", 8899, limit=32768)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
