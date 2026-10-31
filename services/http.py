from __future__ import annotations

import aiohttp

_SESSION: aiohttp.ClientSession | None = None


async def session() -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is None or _SESSION.closed:
        _SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=40),
            connector=aiohttp.TCPConnector(limit=40, ttl_dns_cache=300),
        )
    return _SESSION


async def close() -> None:
    global _SESSION
    if _SESSION is not None and not _SESSION.closed:
        await _SESSION.close()
    _SESSION = None
