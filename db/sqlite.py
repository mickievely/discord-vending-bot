from __future__ import annotations

import asyncio
import random
from pathlib import Path

import aiosqlite

_LOCKS: dict[str, asyncio.Lock] = {}
_CONNS: dict[str, aiosqlite.Connection] = {}
_POOL_LOCK = asyncio.Lock()


def _key(path: Path) -> str:
    return str(path.resolve())


def _lock_for(path: Path) -> asyncio.Lock:
    key = _key(path)
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def _dict_row_factory(cursor, row):
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


async def _apply_pragmas(conn: aiosqlite.Connection):
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=8000")
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA temp_store=MEMORY")
    await conn.execute("PRAGMA cache_size=-8000")


async def _pooled(path: Path) -> aiosqlite.Connection:
    key = _key(path)
    conn = _CONNS.get(key)
    if conn is not None:
        return conn
    async with _POOL_LOCK:
        conn = _CONNS.get(key)
        if conn is not None:
            return conn
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(path), timeout=8)
        conn.row_factory = _dict_row_factory
        await _apply_pragmas(conn)
        _CONNS[key] = conn
        return conn


def _drop(path: Path) -> None:
    _CONNS.pop(_key(path), None)


async def connect(path: Path) -> aiosqlite.Connection:
    return await _pooled(path)


async def _run(path: Path, fn):
    lock = _lock_for(path)
    async with lock:
        last = None
        for i in range(8):
            try:
                conn = await _pooled(path)
                return await fn(conn)
            except aiosqlite.OperationalError as e:
                last = e
                msg = str(e).lower()
                if "closed" in msg or "not open" in msg:
                    _drop(path)
                    continue
                if "locked" in msg or "busy" in msg:
                    await asyncio.sleep(0.05 * (2 ** i) + random.random() * 0.03)
                    continue
                raise
        if last:
            raise last


async def execute(path: Path, sql: str, params: tuple = ()):
    async def _fn(conn):
        await conn.execute(sql, params)
        await conn.commit()
    await _run(path, _fn)


async def executemany(path: Path, sql: str, seq: list[tuple]):
    if not seq:
        return

    async def _fn(conn):
        await conn.executemany(sql, seq)
        await conn.commit()
    await _run(path, _fn)


async def fetchone(path: Path, sql: str, params: tuple = ()):
    async def _fn(conn):
        cur = await conn.execute(sql, params)
        return await cur.fetchone()
    return await _run(path, _fn)


async def fetchall(path: Path, sql: str, params: tuple = ()):
    async def _fn(conn):
        cur = await conn.execute(sql, params)
        return await cur.fetchall()
    return await _run(path, _fn)


async def tx(path: Path, fn):
    async def _fn(conn):
        try:
            await conn.execute("BEGIN IMMEDIATE")
            out = await fn(conn)
            await conn.commit()
            return out
        except Exception:
            try:
                await conn.rollback()
            except Exception:
                pass
            raise
    return await _run(path, _fn)
