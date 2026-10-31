from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _get_int(key: str, default: int) -> int:
    raw = _get(key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(key: str, *, default: bool) -> bool:
    raw = _get(key, "1" if default else "0").lower()
    return raw not in {"0", "false", "no", "off"}


DISCORD_TOKEN = _get("DISCORD_TOKEN")

_guild_raw = _get("DISCORD_GUILD_ID")
DISCORD_GUILD_ID = int(_guild_raw) if _guild_raw.isdigit() else 0

DATA_DIR = _get("DATA_DIR", "./data") or "./data"

EMBED_COLOR_DEFAULT = 0x6C63FF

WEB_ADMIN_ID = _get("WEB_ADMIN_ID", "admin") or "admin"
WEB_ADMIN_PASSWORD = _get("WEB_ADMIN_PASSWORD", "admin1234") or "admin1234"
WEB_PANEL_HOST = _get("WEB_PANEL_HOST", "127.0.0.1") or "127.0.0.1"
WEB_PANEL_PORT = _get_int("WEB_PANEL_PORT", 8765)
WEB_PANEL_AUTO_START = _get_bool("WEB_PANEL_AUTO_START", default=True)
WEB_SESSION_TTL_SEC = _get_int("WEB_SESSION_TTL", 30 * 24 * 3600)

_jwt_secret = _get("WEB_JWT_SECRET")
WEB_JWT_SECRET = _jwt_secret or hashlib.sha256(
    f"{WEB_ADMIN_ID}|{WEB_ADMIN_PASSWORD}|vending-web".encode("utf-8")
).hexdigest()

PRODUCT_ADD_WEBHOOK_URL = _get("PRODUCT_ADD_WEBHOOK_URL")
