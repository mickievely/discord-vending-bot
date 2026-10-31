from __future__ import annotations

import time
from pathlib import Path

from db import sqlite as s
from utils.paths import data_root


def web_db_path() -> Path:
    return data_root() / "web.db"


async def init():
    path = web_db_path()
    await s.execute(
        path,
        """
        CREATE TABLE IF NOT EXISTS web_login_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT,
          ip TEXT,
          ok INTEGER NOT NULL,
          created_at INTEGER NOT NULL
        )
        """,
    )


async def add_login(username: str, ip: str, ok: bool):
    await init()
    await s.execute(
        web_db_path(),
        "INSERT INTO web_login_logs(username, ip, ok, created_at) VALUES(?,?,?,?)",
        (str(username or ""), str(ip or ""), 1 if ok else 0, int(time.time())),
    )


async def list_logins(limit: int = 200):
    await init()
    rows = await s.fetchall(
        web_db_path(),
        "SELECT id, username, ip, ok, created_at FROM web_login_logs ORDER BY id DESC LIMIT ?",
        (int(limit),),
    )
    return [dict(r) for r in (rows or [])]
