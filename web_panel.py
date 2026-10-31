from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from aiohttp import web

from config import (
    DATA_DIR,
    DISCORD_TOKEN,
    WEB_ADMIN_ID,
    WEB_ADMIN_PASSWORD,
    WEB_JWT_SECRET,
    WEB_PANEL_HOST,
    WEB_PANEL_PORT,
    WEB_SESSION_TTL_SEC,
)
from db import server_repo
from db import sqlite as db
from db import web_repo
from db.cache import DISCORD
from services import http as http_pool


ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"
DATA_ROOT = Path(DATA_DIR)
SERVER_ROOT = DATA_ROOT / "servers"


DISCORD_API_BASE = "https://discord.com/api/v10"

SESSION_TTL_SEC = WEB_SESSION_TTL_SEC
LOGIN_WINDOW_SEC = 600
LOGIN_MAX_FAILS = 8
CLIENT_MAX_SIZE = 2 * 1024 * 1024
STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    ),
}

JWT_SECRET = WEB_JWT_SECRET
JWT_REVOKED: set[str] = set()
LOGIN_FAILS: dict[str, list[float]] = {}
DISCORD_BOT: Any | None = None
SPA_VIEWS = {"products", "orders", "users", "charges", "panel", "logs", "login-logs", "announce", "vip"}
NO_STORE = "no-store, no-cache, must-revalidate, max-age=0"
_ASSET_V = ""
_ASSET_V_RE = re.compile(r"\?v=\d+")


def asset_version() -> str:
    global _ASSET_V
    if _ASSET_V:
        return _ASSET_V
    latest = 0
    if WEB_DIR.is_dir():
        for path in WEB_DIR.rglob("*"):
            if path.is_file():
                try:
                    latest = max(latest, int(path.stat().st_mtime))
                except OSError:
                    pass
    _ASSET_V = str(latest or int(time.time()))
    return _ASSET_V


def apply_nocache(resp: web.StreamResponse) -> web.StreamResponse:
    resp.headers["Cache-Control"] = NO_STORE
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Surrogate-Control"] = "no-store"
    resp.headers.pop("ETag", None)
    resp.headers.pop("Last-Modified", None)
    return resp


def set_discord_bot(bot: Any) -> None:
    global DISCORD_BOT
    DISCORD_BOT = bot


def json_response(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=json.dumps)


KST = timezone(timedelta(hours=9))


def ts_to_iso(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    except Exception:
        return ""


DASH_PERIODS = {1, 7, 30, 90, 0}


def parse_dash_days(request: web.Request) -> int:
    try:
        days = int(request.query.get("days") or 7)
    except (TypeError, ValueError):
        days = 7
    return days if days in DASH_PERIODS else 7


def kst_midnight(day) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=KST).timestamp())


def dashboard_range(days: int) -> tuple[int, datetime]:
    now = datetime.now(KST)
    if days <= 0:
        return 0, now
    if days == 1:
        return kst_midnight(now.date()), now
    start = now.date() - timedelta(days=days - 1)
    return kst_midnight(start), now


def _sale_points(rows: list) -> list[tuple[int, int]]:
    out = []
    for row in rows or []:
        try:
            out.append((int(row["created_at"] or 0), int(row["total"] or 0)))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def bucket_sales(rows: list, days: int, now: datetime) -> list[dict[str, Any]]:
    today = now.date()
    items = _sale_points(rows)
    if days == 1:
        start = kst_midnight(today)
        sales = [0] * 24
        for ts, amount in items:
            hour = (ts - start) // 3600
            if 0 <= hour < 24:
                sales[hour] += amount
        return [{"label": f"{h}시", "sales": sales[h]} for h in range(24)]
    if days in (7, 30):
        start_d = today - timedelta(days=days - 1)
        start = kst_midnight(start_d)
        sales = [0] * days
        for ts, amount in items:
            idx = (ts - start) // 86400
            if 0 <= idx < days:
                sales[idx] += amount
        out = []
        for i in range(days):
            day = start_d + timedelta(days=i)
            label = f"{day.month}월 {day.day}일" if days == 7 else f"{day.month}/{day.day}"
            out.append({"label": label, "sales": sales[i]})
        return out
    if days == 90:
        weeks = 13
        start_d = today - timedelta(days=7 * weeks - 1)
        start = kst_midnight(start_d)
        sales = [0] * weeks
        span = 7 * 86400
        for ts, amount in items:
            idx = (ts - start) // span
            if 0 <= idx < weeks:
                sales[idx] += amount
        return [{"label": f"{(start_d + timedelta(days=i * 7)).month}/{(start_d + timedelta(days=i * 7)).day}", "sales": sales[i]} for i in range(weeks)]
    monthly: dict[tuple[int, int], int] = {}
    for ts, amount in items:
        try:
            dt = datetime.fromtimestamp(ts, KST)
        except (OverflowError, OSError, ValueError):
            continue
        key = (dt.year, dt.month)
        monthly[key] = monthly.get(key, 0) + amount
    if not monthly:
        return []
    keys = sorted(monthly)
    year, month = keys[0]
    end_y, end_m = keys[-1]
    out = []
    while (year, month) <= (end_y, end_m):
        out.append({"label": f"{year % 100:02d}.{month:02d}", "sales": monthly.get((year, month), 0)})
        month += 1
        if month > 12:
            month = 1
            year += 1
    return out[-24:]


def color_to_hex(value: Any) -> str:
    try:
        return f"#{int(value):06X}"
    except Exception:
        return "#f4f3f1"


def hex_to_int(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("#"):
            return int(raw[1:], 16)
        return int(raw, 0)
    except Exception:
        return None


def clean_int(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def request_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return str(request.remote or "")


def auth_token(request: web.Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return str(request.cookies.get("vm_jwt") or "").strip()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_jwt(username: str, ttl: int) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": username,
                "name": username,
                "iat": now,
                "exp": now + int(ttl),
                "jti": secrets.token_urlsafe(12),
            },
            separators=(",", ":"),
        ).encode()
    )
    sig = _b64url(hmac.new(JWT_SECRET.encode("utf-8"), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def read_jwt(token: str) -> dict[str, Any] | None:
    try:
        header, payload, sig = str(token or "").split(".")
        expect = _b64url(hmac.new(JWT_SECRET.encode("utf-8"), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not secrets.compare_digest(sig, expect):
            return None
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
        if int(data.get("exp") or 0) <= int(time.time()):
            return None
        if str(data.get("jti") or "") in JWT_REVOKED:
            return None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def attach_auth_cookies(resp: web.Response, token: str, username: str, max_age: int | None) -> None:
    age = int(max_age if max_age is not None else SESSION_TTL_SEC)
    common = {"path": "/", "samesite": "Lax", "secure": False, "max_age": age}
    resp.set_cookie("vm_jwt", token, httponly=True, **common)
    resp.set_cookie("vm_user", quote(json.dumps({"username": username, "displayName": username}, separators=(",", ":"))), httponly=False, **common)


def clear_auth_cookies(resp: web.Response) -> None:
    resp.del_cookie("vm_jwt", path="/")
    resp.del_cookie("vm_user", path="/")


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def credentials_match(username: str, password: str) -> bool:
    user_ok = secrets.compare_digest(_digest(username), _digest(WEB_ADMIN_ID))
    pass_ok = secrets.compare_digest(_digest(password), _digest(WEB_ADMIN_PASSWORD))
    return user_ok and pass_ok


def require_auth(request: web.Request) -> dict[str, Any]:
    payload = read_jwt(auth_token(request))
    if not payload:
        raise web.HTTPUnauthorized(text="unauthorized")
    return payload


def login_rate_limited(ip: str) -> bool:
    now = time.time()
    recent = [stamp for stamp in LOGIN_FAILS.get(ip, []) if now - stamp < LOGIN_WINDOW_SEC]
    LOGIN_FAILS[ip] = recent
    return len(recent) >= LOGIN_MAX_FAILS


def record_login_fail(ip: str) -> None:
    LOGIN_FAILS.setdefault(ip, []).append(time.time())


@web.middleware
async def security_middleware(request: web.Request, handler):
    try:
        resp = await handler(request)
    except web.HTTPException as exc:
        for key, value in SECURITY_HEADERS.items():
            exc.headers.setdefault(key, value)
        raise
    for key, value in SECURITY_HEADERS.items():
        resp.headers.setdefault(key, value)
    if request.path != "/api/auth/login":
        apply_nocache(resp)
    return resp


def server_id_from_request(request: web.Request) -> int:
    sid = str(request.query.get("serverId") or "").strip()
    if not sid:
        sid = primary_server_id()
    if not sid or not str(sid).isdigit():
        raise web.HTTPBadRequest(text="serverId is required")
    return int(sid)


def server_db_path(server_id: int) -> Path:
    return SERVER_ROOT / str(int(server_id)) / "server.db"


def server_ids() -> list[str]:
    if not SERVER_ROOT.exists():
        return []
    return [
        item.name
        for item in sorted(SERVER_ROOT.iterdir(), key=lambda p: p.name)
        if item.is_dir() and item.name.isdigit() and (item / "server.db").exists()
    ]


def primary_server_id() -> str:
    configured = __import__("os").getenv("WEB_PRIMARY_SERVER_ID", "").strip()
    if configured:
        return configured
    ids = server_ids()
    if not ids and DISCORD_BOT is not None:
        guilds = getattr(DISCORD_BOT, "guilds", []) or []
        ids = [str(getattr(g, "id", "")) for g in guilds if getattr(g, "id", None)]
    return ids[0] if ids else ""


def discord_guild(server_id: int):
    if DISCORD_BOT is None:
        return None
    try:
        return DISCORD_BOT.get_guild(int(server_id))
    except Exception:
        return None


def discord_auth_header() -> str:
    if not DISCORD_TOKEN:
        return ""
    return DISCORD_TOKEN if DISCORD_TOKEN.lower().startswith("bot ") else f"Bot {DISCORD_TOKEN}"


async def discord_api_get(path: str):
    auth = discord_auth_header()
    if not auth:
        return None
    ck = ("get", path)
    ok, cached = DISCORD.peek(ck)
    if ok:
        return cached
    try:
        session = await http_pool.session()
        async with session.get(
            f"{DISCORD_API_BASE}{path}",
            headers={"Authorization": auth},
        ) as resp:
            if 200 <= resp.status < 300:
                data = await resp.json()
                DISCORD.set(ck, data)
                return data
    except Exception:
        return None
    return None


async def discord_guild_name_from_api(server_id: str) -> str | None:
    data = await discord_api_get(f"/guilds/{int(server_id)}")
    if isinstance(data, dict) and data.get("name"):
        return str(data["name"])
    return None


async def discord_channels_from_api(server_id: int) -> list[dict[str, str]]:
    data = await discord_api_get(f"/guilds/{int(server_id)}/channels")
    if not isinstance(data, list):
        return []
    def channel_type(ch: dict[str, Any]) -> int:
        raw = ch.get("type")
        return int(raw) if raw is not None else -1

    categories = {str(ch.get("id")): str(ch.get("name") or "") for ch in data if channel_type(ch) == 4}
    out = []
    for ch in data:
        if channel_type(ch) not in (0, 5):
            continue
        name = str(ch.get("name") or ch.get("id") or "")
        parent = categories.get(str(ch.get("parent_id") or ""), "")
        label = f"{parent} / {name}" if parent else name
        out.append({"id": str(ch.get("id")), "name": label})
    return sorted(out, key=lambda item: item["name"].lower())


async def discord_roles_from_api(server_id: int) -> list[dict[str, str]]:
    data = await discord_api_get(f"/guilds/{int(server_id)}/roles")
    if not isinstance(data, list):
        return []
    out = []
    for role in data:
        if str(role.get("name") or "") == "@everyone":
            continue
        out.append({
            "id": str(role.get("id")),
            "name": str(role.get("name") or role.get("id") or ""),
            "position": int(role.get("position") or 0),
        })
    out.sort(key=lambda item: (-item["position"], item["name"].lower()))
    for role in out:
        role.pop("position", None)
    return out


async def ensure_server_db(server_id: int) -> Path:
    path = server_db_path(server_id)
    await server_repo.init(path)
    await ensure_web_columns(path)
    return path


_WEB_COLS_DONE: set[str] = set()


async def ensure_web_columns(path: Path) -> None:
    key = str(path.resolve())
    if key in _WEB_COLS_DONE:
        return
    panel_cols = await db.fetchall(path, "PRAGMA table_info(panel_settings)")
    panel_names = {c["name"] for c in panel_cols or []}
    if "purchase_grant_role_id" not in panel_names:
        await db.execute(path, "ALTER TABLE panel_settings ADD COLUMN purchase_grant_role_id INTEGER")

    charge_cols = await db.fetchall(path, "PRAGMA table_info(charge_settings)")
    charge_names = {c["name"] for c in charge_cols or []}
    if "manual_charge_notice_enabled" not in charge_names:
        await db.execute(path, "ALTER TABLE charge_settings ADD COLUMN manual_charge_notice_enabled INTEGER NOT NULL DEFAULT 1")
    if "min_charge_amount" not in charge_names:
        await db.execute(path, "ALTER TABLE charge_settings ADD COLUMN min_charge_amount INTEGER NOT NULL DEFAULT 1")

    cols = await db.fetchall(path, "PRAGMA table_info(log_settings)")
    names = {c["name"] for c in cols or []}
    if "stock_channel_id" not in names:
        await db.execute(path, "ALTER TABLE log_settings ADD COLUMN stock_channel_id INTEGER")
    if "stock_desc_template" not in names:
        await db.execute(path, "ALTER TABLE log_settings ADD COLUMN stock_desc_template TEXT")
    if "charge_desc_template" not in names:
        await db.execute(path, "ALTER TABLE log_settings ADD COLUMN charge_desc_template TEXT")
    if "review_desc_template" not in names:
        await db.execute(path, "ALTER TABLE log_settings ADD COLUMN review_desc_template TEXT")
    if "manual_charge_channel_id" not in names:
        await db.execute(path, "ALTER TABLE log_settings ADD COLUMN manual_charge_channel_id INTEGER")
    extra = [
        ("buy_embed_color", "INTEGER"),
        ("buy_image_url", "TEXT"),
        ("stock_embed_color", "INTEGER"),
        ("stock_image_url", "TEXT"),
        ("dm_title", "TEXT"),
        ("dm_desc_template", "TEXT"),
        ("dm_embed_color", "INTEGER"),
        ("dm_image_url", "TEXT"),
        ("restock_dm_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ("restock_dm_template", "TEXT"),
        ("login_log_channel_id", "INTEGER"),
        ("stock_title_template", "TEXT"),
        ("stock_everyone", "INTEGER NOT NULL DEFAULT 1"),
    ]
    for name, decl in extra:
        if name not in names:
            await db.execute(path, f"ALTER TABLE log_settings ADD COLUMN {name} {decl}")
            names.add(name)

    product_cols = await db.fetchall(path, "PRAGMA table_info(products)")
    product_names = {c["name"] for c in product_cols or []}
    if "grant_role_id" not in product_names:
        await db.execute(path, "ALTER TABLE products ADD COLUMN grant_role_id INTEGER")

    await server_repo._ensure_vip(path)
    _WEB_COLS_DONE.add(key)


async def selected_db(request: web.Request) -> Path:
    return await ensure_server_db(server_id_from_request(request))


def category_row(row: dict[str, Any], product_count: int = 0) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"] or "",
        "productCount": int(product_count),
    }


async def list_categories_payload(path: Path) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        path,
        """
        SELECT c.id, c.name, COUNT(p.id) AS product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        GROUP BY c.id, c.name, c.position
        ORDER BY c.position ASC, c.id ASC
        """,
    )
    return [category_row(r, r.get("product_count") or 0) for r in rows or []]


async def product_payload(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    stock_items = await server_repo.stock_lines(path, int(row["id"]))
    return {
        "id": str(row["id"]),
        "categoryId": str(row["category_id"]),
        "name": row["name"] or "",
        "price": int(row["price"] or 0),
        "stock": len(stock_items),
        "stockItems": stock_items,
        "active": True,
        "description": row.get("description") or "",
        "imageUrl": row.get("description") or "",
        "grantRoleId": str(row.get("grant_role_id") or ""),
    }


async def list_products_payload(path: Path) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        path,
        """
        SELECT id, category_id, name, price, description, grant_role_id
        FROM products
        ORDER BY position ASC, id ASC
        """,
    )
    counts = await db.fetchall(
        path,
        "SELECT product_id, COUNT(*) AS cnt FROM stocks WHERE consumed_at IS NULL GROUP BY product_id",
    )
    cmap = {int(r["product_id"]): int(r["cnt"]) for r in counts or []}
    out = []
    for row in rows or []:
        payload = {
            "id": str(row["id"]),
            "categoryId": str(row["category_id"]),
            "name": row["name"] or "",
            "price": int(row["price"] or 0),
            "stock": cmap.get(int(row["id"]), 0),
            "active": True,
            "description": row.get("description") or "",
            "imageUrl": row.get("description") or "",
            "grantRoleId": str(row.get("grant_role_id") or ""),
        }
        out.append(payload)
    return out


def charge_id(platform: str, pid: Any) -> str:
    return f"{platform.upper()}:{int(pid)}"


def split_charge_id(value: str) -> tuple[str, int]:
    platform, pid = unquote(str(value)).split(":", 1)
    platform = platform.upper()
    if platform not in ("AOS", "IOS"):
        raise ValueError("invalid platform")
    return platform, int(pid)


def ui_charge_status(status: str) -> str:
    if status == "done":
        return "approved"
    return status or "pending"


async def list_charges_payload(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for platform, table in (("AOS", "aos_pending_charges"), ("IOS", "ios_pending_charges")):
        rows = await db.fetchall(
            path,
            f"SELECT * FROM {table} ORDER BY id DESC LIMIT 300",
        )
        for row in rows or []:
            out.append(
                {
                    "id": charge_id(platform, row["id"]),
                    "platform": platform,
                    "userId": str(row["user_id"]),
                    "depositor": row["depositor_name"] or "",
                    "amount": int(row["amount"] or 0),
                    "createdAt": ts_to_iso(row["created_at"]),
                    "status": ui_charge_status(str(row["status"] or "pending")),
                    "approvedBy": row.get("approved_by_name") or "",
                    "approvedById": str(row.get("approved_by") or ""),
                    "approvedAt": ts_to_iso(row.get("approved_at")),
                }
            )
    out.sort(key=lambda x: x["createdAt"], reverse=True)
    return out


async def list_orders_payload(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT o.id, o.user_id, o.qty, o.total, o.created_at, o.status, o.delivered_text,
               p.name AS product_name
        FROM orders o
        JOIN products p ON p.id = o.product_id
        ORDER BY o.id DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = await db.fetchall(path, sql)
    return [
        {
            "id": str(r["id"]),
            "userId": str(r["user_id"]),
            "productName": r["product_name"] or "",
            "qty": int(r["qty"] or 0),
            "total": int(r["total"] or 0),
            "createdAt": ts_to_iso(r["created_at"]),
            "status": r["status"] or "completed",
            "delivered": r.get("delivered_text") or "",
        }
        for r in rows or []
    ]


async def list_users_payload(path: Path) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        path,
        """
        SELECT
          u.user_id AS user_id,
          COALESCE(b.balance, 0) AS balance,
          COALESCE(o.spent, 0) AS spent,
          COALESCE(o.cnt, 0) AS orders,
          t.id AS vip_id,
          t.name AS vip_name,
          t.discount_pct AS vip_discount,
          t.purchase_discount_pct AS vip_buy,
          t.charge_bonus_pct AS vip_charge,
          t.unlock_spent AS vip_unlock,
          t.color AS vip_color,
          t.emoji AS vip_emoji,
          t.icon_url AS vip_icon
        FROM (
          SELECT user_id FROM balances
          UNION
          SELECT user_id FROM orders
          UNION
          SELECT user_id FROM user_vip
        ) u
        LEFT JOIN balances b ON b.user_id = u.user_id
        LEFT JOIN (
          SELECT user_id,
                 COUNT(*) AS cnt,
                 COALESCE(SUM(CASE WHEN status='completed' THEN total ELSE 0 END), 0) AS spent
          FROM orders
          GROUP BY user_id
        ) o ON o.user_id = u.user_id
        LEFT JOIN user_vip uv ON uv.user_id = u.user_id
        LEFT JOIN vip_tiers t ON t.id = uv.tier_id
        ORDER BY u.user_id ASC
        """,
    )
    return [
        {
            "id": str(int(row["user_id"])),
            "balance": int(row["balance"] or 0),
            "totalSpent": int(row["spent"] or 0),
            "orderCount": int(row["orders"] or 0),
            "vip": _vip_user_payload(row),
        }
        for row in rows or []
    ]


def _vip_user_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row or not row.get("vip_id"):
        return None
    return {
        "id": str(int(row["vip_id"])),
        "name": row.get("vip_name") or "",
        "discountPct": int(row.get("vip_buy") if row.get("vip_buy") is not None else row.get("vip_discount") or 0),
        "purchaseDiscountPct": int(row.get("vip_buy") if row.get("vip_buy") is not None else row.get("vip_discount") or 0),
        "chargeBonusPct": int(row.get("vip_charge") or 0),
        "unlockSpent": int(row.get("vip_unlock") or 0),
        "color": color_to_hex(row.get("vip_color")) if row.get("vip_color") is not None else "#CD7F32",
        "emoji": row.get("vip_emoji") or "",
        "iconUrl": row.get("vip_icon") or "",
    }


async def get_user_payload(path: Path, uid: int) -> dict[str, Any]:
    bal = await db.fetchone(path, "SELECT balance FROM balances WHERE user_id=?", (uid,))
    stats = await db.fetchone(
        path,
        """
        SELECT COUNT(*) AS orders,
               COALESCE(SUM(CASE WHEN status='completed' THEN total ELSE 0 END), 0) AS spent,
               MAX(created_at) AS last_at
        FROM orders
        WHERE user_id=?
        """,
        (uid,),
    )
    order_rows = await db.fetchall(
        path,
        """
        SELECT o.id, o.qty, o.total, o.created_at, o.status, p.name AS product_name
        FROM orders o
        JOIN products p ON p.id = o.product_id
        WHERE o.user_id=?
        ORDER BY o.id DESC
        LIMIT 20
        """,
        (uid,),
    )
    charge_rows = []
    for platform, table in (("AOS", "aos_pending_charges"), ("IOS", "ios_pending_charges")):
        rows = await db.fetchall(
            path,
            f"SELECT id, amount, depositor_name, created_at, status FROM {table} WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (uid,),
        )
        for row in rows or []:
            charge_rows.append(
                {
                    "id": charge_id(platform, row["id"]),
                    "platform": platform,
                    "amount": int(row["amount"] or 0),
                    "depositor": row["depositor_name"] or "",
                    "createdAt": ts_to_iso(row["created_at"]),
                    "status": ui_charge_status(str(row.get("status") or "pending")),
                }
            )
    charge_rows.sort(key=lambda x: x["createdAt"], reverse=True)
    vip = await server_repo.get_user_vip(path, uid)
    return {
        "id": str(uid),
        "balance": int(bal["balance"] if bal else 0),
        "totalSpent": int(stats["spent"] if stats else 0),
        "orderCount": int(stats["orders"] if stats else 0),
        "lastAt": ts_to_iso(stats["last_at"]) if stats and stats.get("last_at") else "",
        "vip": {
            "id": str(vip["id"]),
            "name": vip.get("name") or "",
            "discountPct": int(vip.get("purchaseDiscountPct") or vip.get("discountPct") or 0),
            "purchaseDiscountPct": int(vip.get("purchaseDiscountPct") or vip.get("discountPct") or 0),
            "chargeBonusPct": int(vip.get("chargeBonusPct") or 0),
            "unlockSpent": int(vip.get("unlockSpent") or 0),
            "color": color_to_hex(vip.get("color")) if vip.get("color") is not None else "#CD7F32",
            "emoji": vip.get("emoji") or "",
            "iconUrl": vip.get("iconUrl") or "",
            "source": vip.get("source") or "auto",
        } if vip else None,
        "orders": [
            {
                "id": str(r["id"]),
                "productName": r["product_name"] or "",
                "qty": int(r["qty"] or 0),
                "total": int(r["total"] or 0),
                "createdAt": ts_to_iso(r["created_at"]),
                "status": r["status"] or "completed",
            }
            for r in order_rows or []
        ],
        "charges": charge_rows[:12],
    }


async def handle_index(request: web.Request) -> web.StreamResponse:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    html = _ASSET_V_RE.sub(f"?v={asset_version()}", html)
    payload = read_jwt(str(request.cookies.get("vm_jwt") or "").strip())
    user = None
    if payload:
        name = str(payload.get("name") or payload.get("sub") or "").strip()
        if name:
            user = {"username": name, "displayName": name}
    boot = json.dumps({"user": user}, ensure_ascii=True, separators=(",", ":"))
    html = html.replace("</head>", f"<script>window.__BOOT__={boot};</script>\n</head>", 1)
    if user:
        html = html.replace('<div id="login-screen">', '<div id="login-screen" class="hidden">', 1)
        html = html.replace('<div id="app" class="hidden">', '<div id="app">', 1)
    resp = web.Response(text=html, content_type="text/html", charset="utf-8")
    apply_nocache(resp)
    return resp


async def handle_static(request: web.Request) -> web.StreamResponse:
    raw = unquote(str(request.match_info.get("path") or ""))
    rel = raw.replace("\\", "/").lstrip("/")
    parts = [part for part in rel.split("/") if part]
    if not parts or any(part == ".." for part in parts):
        raise web.HTTPForbidden()
    root = WEB_DIR.resolve()
    target = (root.joinpath(*parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise web.HTTPForbidden()
    suffix = target.suffix.lower()
    if suffix not in STATIC_TYPES or not target.is_file():
        raise web.HTTPNotFound()
    ctype = STATIC_TYPES[suffix].split(";", 1)[0].strip()
    resp = web.Response(body=target.read_bytes(), content_type=ctype, charset="utf-8")
    apply_nocache(resp)
    return resp


async def handle_login(request: web.Request) -> web.Response:
    ip = request_ip(request)
    if login_rate_limited(ip):
        return json_response({"ok": False, "error": "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."}, 429)
    try:
        body = await request.json()
    except Exception:
        return json_response({"ok": False, "error": "잘못된 요청입니다."}, 400)
    if not isinstance(body, dict):
        return json_response({"ok": False, "error": "잘못된 요청입니다."}, 400)
    username = str(body.get("username") or "").strip()[:64]
    password = str(body.get("password") or "")[:256]
    if not WEB_ADMIN_ID or not WEB_ADMIN_PASSWORD:
        return json_response({"ok": False, "error": "WEB_ADMIN_ID/WEB_ADMIN_PASSWORD가 설정되지 않았습니다."}, 500)
    ok = credentials_match(username, password)
    try:
        await web_repo.add_login(username, ip, ok)
    except Exception:
        pass
    try:
        from services import notify
        notify.spawn(notify.send_login_logs(username, ip, ok))
    except Exception:
        pass
    if ok:
        LOGIN_FAILS.pop(ip, None)
        ttl = SESSION_TTL_SEC
        token = make_jwt(username, ttl)
        user = {"username": username, "displayName": username}
        resp = json_response({"ok": True, "token": token, "user": user})
        attach_auth_cookies(resp, token, username, ttl)
        return resp
    record_login_fail(ip)
    return json_response({"ok": False, "error": "아이디 또는 비밀번호가 올바르지 않습니다."})


async def handle_logout(request: web.Request) -> web.Response:
    payload = read_jwt(auth_token(request))
    if payload and payload.get("jti"):
        JWT_REVOKED.add(str(payload["jti"]))
    resp = json_response({"ok": True})
    clear_auth_cookies(resp)
    return resp


async def handle_me(request: web.Request) -> web.Response:
    payload = require_auth(request)
    name = str(payload.get("name") or payload.get("sub") or "")
    return json_response({"ok": True, "user": {"username": name, "displayName": name}})


async def handle_servers(request: web.Request) -> web.Response:
    require_auth(request)
    known: dict[str, str] = {}
    if DISCORD_BOT is not None:
        for guild in getattr(DISCORD_BOT, "guilds", []) or []:
            gid = str(getattr(guild, "id", "") or "")
            if gid:
                known[gid] = str(getattr(guild, "name", "") or f"서버 {gid}")
    for sid in server_ids():
        known.setdefault(str(sid), f"서버 {sid}")
    api_name_targets = [sid for sid, name in known.items() if name == f"서버 {sid}"]
    if api_name_targets:
        names = await asyncio.gather(*(discord_guild_name_from_api(sid) for sid in api_name_targets))
        for sid, name in zip(api_name_targets, names):
            if name:
                known[sid] = name
    servers = [{"id": sid, "name": name} for sid, name in sorted(known.items(), key=lambda item: item[1].lower())]
    return json_response(servers)


async def handle_dashboard(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    days = parse_dash_days(request)
    t0, now = dashboard_range(days)
    today_start = kst_midnight(now.date())
    today = await db.fetchone(
        path,
        "SELECT COALESCE(SUM(total),0) AS total FROM orders WHERE status='completed' AND created_at>=?",
        (today_start,),
    )
    total_orders = await db.fetchone(path, "SELECT COUNT(*) AS cnt FROM orders")
    products = await list_products_payload(path)
    charges = await list_charges_payload(path)
    orders = await list_orders_payload(path, 5)
    low_stock = [p for p in products if int(p["stock"]) <= 5]
    pending = [c for c in charges if c["status"] == "pending"]
    if t0:
        sale_rows = await db.fetchall(
            path,
            "SELECT created_at, total FROM orders WHERE status='completed' AND created_at>=?",
            (t0,),
        )
        top_sql = """
            SELECT p.name AS name, COUNT(*) AS cnt, COALESCE(SUM(o.total),0) AS sales
            FROM orders o
            JOIN products p ON p.id = o.product_id
            WHERE o.status='completed' AND o.created_at>=?
            GROUP BY o.product_id
            ORDER BY sales DESC
            LIMIT 5
        """
        top_rows = await db.fetchall(path, top_sql, (t0,))
        aos_row = await db.fetchone(path, "SELECT COUNT(*) AS cnt FROM aos_pending_charges WHERE created_at>=?", (t0,))
        ios_row = await db.fetchone(path, "SELECT COUNT(*) AS cnt FROM ios_pending_charges WHERE created_at>=?", (t0,))
    else:
        sale_rows = await db.fetchall(path, "SELECT created_at, total FROM orders WHERE status='completed'")
        top_rows = await db.fetchall(
            path,
            """
            SELECT p.name AS name, COUNT(*) AS cnt, COALESCE(SUM(o.total),0) AS sales
            FROM orders o
            JOIN products p ON p.id = o.product_id
            WHERE o.status='completed'
            GROUP BY o.product_id
            ORDER BY sales DESC
            LIMIT 5
            """,
        )
        aos_row = await db.fetchone(path, "SELECT COUNT(*) AS cnt FROM aos_pending_charges")
        ios_row = await db.fetchone(path, "SELECT COUNT(*) AS cnt FROM ios_pending_charges")
    series = bucket_sales(sale_rows or [], days, now)
    top_products = [{"name": r["name"] or "", "count": int(r["cnt"] or 0), "sales": int(r["sales"] or 0)} for r in top_rows or []]
    aos_cnt = int(aos_row["cnt"] if aos_row else 0)
    ios_cnt = int(ios_row["cnt"] if ios_row else 0)
    return json_response(
        {
            "todaySales": int(today["total"] if today else 0),
            "totalOrders": int(total_orders["cnt"] if total_orders else 0),
            "pendingCharges": len(pending),
            "lowStock": len(low_stock),
            "recentOrders": orders,
            "pendingChargeList": pending[:8],
            "lowStockProducts": low_stock[:8],
            "days": days,
            "series": series,
            "topProducts": top_products,
            "chargeCount": aos_cnt + ios_cnt,
            "chargeSplit": {"aos": aos_cnt, "ios": ios_cnt},
        }
    )


async def handle_categories(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    if request.method == "GET":
        return json_response(await list_categories_payload(path))
    body = await request.json()
    name = str(body.get("name") or "").strip()
    if not name:
        return json_response({"ok": False, "error": "name required"}, 400)
    await server_repo.add_category(path, name)
    return json_response({"ok": True})


async def handle_category(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    cid = int(request.match_info["id"])
    if request.method == "PUT":
        body = await request.json()
        await db.execute(path, "UPDATE categories SET name=? WHERE id=?", (str(body.get("name") or "").strip(), cid))
        server_repo.bust_catalog(path)
        return json_response({"ok": True})
    await server_repo.delete_category(path, cid)
    return json_response({"ok": True})


async def handle_category_reorder(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    body = await request.json()
    ordered = [int(x) for x in body.get("order") or []]

    async def tx(conn):
        for pos, cid in enumerate(ordered):
            await conn.execute("UPDATE categories SET position=? WHERE id=?", (pos, cid))
        return True

    await db.tx(path, tx)
    server_repo.bust_catalog(path)
    return json_response({"ok": True})


async def handle_products(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    if request.method == "GET":
        return json_response(await list_products_payload(path))
    body = await request.json()
    await server_repo.add_product(
        path,
        int(body.get("categoryId")),
        str(body.get("name") or "").strip(),
        int(body.get("price") or 0),
        str(body.get("description") or body.get("imageUrl") or "").strip() or None,
        grant_role_id=clean_int(body.get("grantRoleId")),
    )
    return json_response({"ok": True})


async def handle_product(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    pid = int(request.match_info["id"])
    if request.method == "GET":
        row = await server_repo.product_by_id(path, pid)
        if not row:
            return json_response({"error": "not found"}, status=404)
        return json_response(await product_payload(path, row))
    if request.method == "PUT":
        body = await request.json()
        await db.execute(
            path,
            "UPDATE products SET category_id=?, name=?, price=?, description=?, grant_role_id=? WHERE id=?",
            (
                int(body.get("categoryId")),
                str(body.get("name") or "").strip(),
                int(body.get("price") or 0),
                str(body.get("description") or body.get("imageUrl") or "").strip() or None,
                clean_int(body.get("grantRoleId")),
                pid,
            ),
        )
        server_repo.bust_catalog(path)
        row = await server_repo.product_by_id(path, pid)
        return json_response(await product_payload(path, row) if row else {"ok": False})
    if request.method != "DELETE":
        return json_response({"error": "method not allowed"}, status=405)
    await server_repo.delete_product(path, pid)
    return json_response({"ok": True})


async def handle_product_stock(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    pid = int(request.match_info["id"])
    body = await request.json()
    items = [str(x).strip() for x in body.get("items") or [] if str(x).strip()]
    before = await server_repo.stock_count(path, pid)
    await server_repo.set_stock_lines(path, pid, items)
    after = await server_repo.stock_count(path, pid)
    info = await server_repo.add_stock_log(
        path,
        pid,
        action="set",
        qty=len(items),
        before_count=before,
        after_count=after,
        actor_id=None,
        source="web",
    )
    try:
        from services import notify
        guild_id = server_id_from_request(request)
        details = dict(info or {})
        details.setdefault("product_id", int(pid))
        notify.schedule_stock_notify(
            guild_id,
            details,
            actor_name="웹패널",
            notify_buyers=bool(body.get("notifyBuyers") or body.get("restockDm")),
        )
    except Exception:
        pass
    row = await server_repo.product_by_id(path, pid)
    if not row:
        return json_response({"ok": True, "id": str(pid), "stock": after, "stockItems": items})
    return json_response({
        "id": str(row["id"]),
        "categoryId": str(row["category_id"]),
        "name": row["name"] or "",
        "price": int(row["price"] or 0),
        "stock": after,
        "stockItems": items,
        "active": True,
        "description": row.get("description") or "",
        "imageUrl": row.get("description") or "",
        "grantRoleId": str(row.get("grant_role_id") or ""),
    })


async def handle_stock_logs(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    rows = await server_repo.list_stock_logs(path)
    return json_response(
        [
            {
                "id": str(row["id"]),
                "productId": str(row.get("product_id") or ""),
                "productName": row.get("product_name") or "",
                "categoryName": row.get("category_name") or "",
                "action": row.get("action") or "",
                "added": int(row.get("qty") or 0),
                "before": int(row.get("before_count") or 0),
                "resulting": int(row.get("after_count") or 0),
                "by": str(row.get("actor_id") or row.get("source") or ""),
                "createdAt": ts_to_iso(row.get("created_at")),
            }
            for row in rows or []
        ]
    )


async def handle_product_reorder(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    body = await request.json()
    ordered = [int(x) for x in body.get("order") or []]

    async def tx(conn):
        for pos, pid in enumerate(ordered):
            await conn.execute("UPDATE products SET position=? WHERE id=?", (pos, pid))
        return True

    await db.tx(path, tx)
    server_repo.bust_catalog(path)
    return json_response({"ok": True})


async def handle_purchase_role_settings(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    if request.method == "GET":
        role_id = await server_repo.get_purchase_grant_role(path)
        return json_response({"roleId": str(role_id or "")})
    body = await request.json()
    await server_repo.set_purchase_grant_role(path, clean_int(body.get("roleId")))
    return json_response({"ok": True})


async def handle_orders(request: web.Request) -> web.Response:
    require_auth(request)
    return json_response(await list_orders_payload(await selected_db(request)))


async def handle_order(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    oid = int(str(request.match_info["id"]).replace("ORD-", ""))
    row = await db.fetchone(
        path,
        """
        SELECT o.id, o.user_id, o.qty, o.total, o.created_at, o.status, o.delivered_text,
               p.name AS product_name
        FROM orders o
        JOIN products p ON p.id = o.product_id
        WHERE o.id=?
        """,
        (oid,),
    )
    if not row:
        return json_response({"ok": False, "error": "not found"}, 404)
    return json_response(
        {
            "id": str(row["id"]),
            "userId": str(row["user_id"]),
            "productName": row["product_name"] or "",
            "qty": int(row["qty"] or 0),
            "total": int(row["total"] or 0),
            "createdAt": ts_to_iso(row["created_at"]),
            "status": row["status"] or "completed",
            "delivered": row.get("delivered_text") or "",
        }
    )


async def handle_users(request: web.Request) -> web.Response:
    require_auth(request)
    return json_response(await list_users_payload(await selected_db(request)))


async def handle_user(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    uid = int(request.match_info["id"])
    if request.method == "GET":
        return json_response(await get_user_payload(path, uid))
    body = await request.json()
    if "delta" in body:
        result = await server_repo.add_balance(path, uid, int(body.get("delta") or 0))
        if isinstance(result, dict) and result.get("ok") is False:
            payload = await get_user_payload(path, uid)
            payload["ok"] = False
            payload["error"] = "잔액이 부족합니다"
            return json_response(payload, 400)
    elif "balance" in body:
        value = max(0, int(body.get("balance") or 0))
        await db.execute(
            path,
            "INSERT INTO balances(user_id, balance, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at",
            (uid, value, int(time.time())),
        )
    elif "vipTierId" in body:
        await server_repo.set_user_vip(path, uid, clean_int(body.get("vipTierId")))
    return json_response(await get_user_payload(path, uid))


async def handle_charges(request: web.Request) -> web.Response:
    require_auth(request)
    return json_response(await list_charges_payload(await selected_db(request)))


async def handle_charge_action(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    platform, pid = split_charge_id(request.match_info["id"])
    action = request.match_info["action"]
    pending = await server_repo.get_pending_by_id(path, platform, pid)
    if not pending:
        return json_response({"ok": False, "error": "not found"}, 404)
    if action == "approve":
        if str(pending.get("status")) != "done":
            applied = await server_repo.apply_charge_once(
                path,
                int(pending["user_id"]),
                f"web:{platform}:{pid}",
                int(pending["amount"]),
            )
            if applied:
                await server_repo.credit_charge(path, int(pending["user_id"]), int(pending["amount"]))
            actor_name = f"웹패널 ({WEB_ADMIN_ID})"
            now = int(time.time())
            await server_repo.set_charge_approval(path, platform, pid, actor_id=None, actor_name=actor_name, approved_at=now)
            pending["approved_by"] = None
            pending["approved_by_name"] = actor_name
            pending["approved_at"] = now
            if platform == "AOS":
                await server_repo.aos_mark_done(path, pid)
            else:
                await db.execute(path, "UPDATE ios_pending_charges SET status='done' WHERE id=?", (pid,))
            try:
                from services import notify
                await notify.refresh_charge_log_message(server_id_from_request(request), platform, pending, "done")
            except Exception:
                pass
    elif action == "reject":
        if platform == "AOS":
            await server_repo.aos_mark_rejected(path, pid)
        else:
            await server_repo.ios_mark_rejected(path, pid)
    else:
        return json_response({"ok": False, "error": "bad action"}, 400)
    charges = [c for c in await list_charges_payload(path) if c["id"] == charge_id(platform, pid)]
    return json_response(charges[0] if charges else {"ok": True})


async def handle_charge_settings(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    if request.method == "GET":
        row = await server_repo.get_charge_settings(path)
        row = row or {}
        return json_response(
            {
                "aosBank": row.get("aos_bank_name") or "",
                "aosAccount": row.get("aos_bank_account") or "",
                "aosHolder": row.get("aos_bank_owner") or "",
                "aosPushbullet": row.get("pushbullet_token") or "",
                "iosBank": row.get("ios_bank_name") or "",
                "iosAccount": row.get("ios_bank_account") or "",
                "iosHolder": row.get("ios_bank_owner") or "",
                "iosLogChannel": str(row.get("ios_log_channel_id") or ""),
                "approveRole": str(row.get("charge_manager_role_id") or ""),
                "manualChargeRole": str(row.get("charge_manager_role_id") or ""),
                "manualChargeNotice": int(row.get("manual_charge_notice_enabled") if row.get("manual_charge_notice_enabled") is not None else 1) == 1,
                "minChargeAmount": int(row.get("min_charge_amount") or 1),
            }
        )
    body = await request.json()
    await server_repo.set_aos_charge_settings(
        path,
        str(body.get("aosBank") or "").strip(),
        str(body.get("aosAccount") or "").strip(),
        str(body.get("aosHolder") or "").strip(),
        str(body.get("aosPushbullet") or "").strip() or None,
    )
    ios_channel = clean_int(body.get("iosLogChannel"))
    await server_repo.set_ios_charge_settings(
        path,
        str(body.get("iosBank") or "").strip(),
        str(body.get("iosAccount") or "").strip(),
        str(body.get("iosHolder") or "").strip(),
        ios_channel or 0,
    )
    await server_repo.set_charge_manager_role(path, clean_int(body.get("approveRole")))
    await server_repo.set_manual_charge_notice_enabled(path, bool(body.get("manualChargeNotice")))
    await server_repo.set_min_charge_amount(path, clean_int(body.get("minChargeAmount")) or 1)
    return json_response({"ok": True})


async def handle_panel_settings(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    if request.method == "GET":
        row = await server_repo.get_panel(path)
        row = row or {}
        return json_response(
            {
                "title": row.get("title") or "",
                "description": row.get("description") or "",
                "imageUrl": row.get("image_url") or "",
                "color": color_to_hex(row.get("color")),
            }
        )
    body = await request.json()
    await server_repo.set_panel(
        path,
        str(body.get("title") or "").strip() or None,
        str(body.get("description") or "").strip() or None,
        hex_to_int(body.get("color")),
        str(body.get("imageUrl") or "").strip() or None,
    )
    return json_response({"ok": True})


def _log_settings_payload(row: dict[str, Any]) -> dict[str, Any]:
    row = row or {}
    return {
        "buyChannel": str(row.get("buy_channel_id") or ""),
        "chargeChannel": str(row.get("charge_channel_id") or ""),
        "manualChargeChannel": str(row.get("manual_charge_channel_id") or ""),
        "reviewChannel": str(row.get("review_channel_id") or ""),
        "stockChannel": str(row.get("stock_channel_id") or ""),
        "loginLogChannel": str(row.get("login_log_channel_id") or ""),
        "buyTitle": row.get("buy_title_template") or "{카테고리}•{제품}",
        "buyTemplate": row.get("buy_desc_template") or "{유저}님 {카테고리} • {제품} 구매 감사합니다",
        "chargeTemplate": row.get("charge_desc_template") or "[충전] {user} 님의 잔액이 {amount}원 충전되었습니다.",
        "reviewTemplate": row.get("review_desc_template") or "[후기] {user} 님이 {category} • {product} 후기를 남겼습니다: {content}",
        "stockTitle": row.get("stock_title_template") or "입고",
        "stockTemplate": row.get("stock_desc_template") or "{제품} >> {수량}개 추가",
        "stockEveryone": int(row.get("stock_everyone") if row.get("stock_everyone") is not None else 1) == 1,
        "buyColor": color_to_hex(row.get("buy_embed_color") or 0x5865F2),
        "buyImageUrl": row.get("buy_image_url") or "",
        "stockColor": color_to_hex(row.get("stock_embed_color") or 0x57F287),
        "stockImageUrl": row.get("stock_image_url") or "",
        "dmTitle": row.get("dm_title") or "구매 완료",
        "dmTemplate": row.get("dm_desc_template") or "",
        "dmColor": color_to_hex(row.get("dm_embed_color") or 0x57F287),
        "dmImageUrl": row.get("dm_image_url") or "",
        "restockDmEnabled": int(row.get("restock_dm_enabled") or 0) == 1,
        "restockDmTemplate": row.get("restock_dm_template") or "{서버} 입고되었습니다",
    }


async def handle_log_settings(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    if request.method == "GET":
        row = await server_repo.get_log_settings(path)
        return json_response(_log_settings_payload(dict(row) if row else {}))
    body = await request.json()
    await server_repo.set_log_settings(
        path,
        buy_channel_id=clean_int(body.get("buyChannel")),
        buy_title_template=str(body.get("buyTitle") or "").strip() or None,
        buy_desc_template=str(body.get("buyTemplate") or "").strip() or None,
        charge_channel_id=clean_int(body.get("chargeChannel")),
        manual_charge_channel_id=clean_int(body.get("manualChargeChannel")),
        review_channel_id=clean_int(body.get("reviewChannel")),
        stock_channel_id=clean_int(body.get("stockChannel")),
        charge_desc_template=str(body.get("chargeTemplate") or "").strip() or None,
        review_desc_template=str(body.get("reviewTemplate") or "").strip() or None,
        stock_title_template=str(body.get("stockTitle") or "").strip() or None,
        stock_desc_template=str(body.get("stockTemplate") or "").strip() or None,
        stock_everyone=1 if body.get("stockEveryone") else 0,
        buy_embed_color=hex_to_int(body.get("buyColor")),
        buy_image_url=str(body.get("buyImageUrl") or "").strip() or None,
        stock_embed_color=hex_to_int(body.get("stockColor")),
        stock_image_url=str(body.get("stockImageUrl") or "").strip() or None,
        dm_title=str(body.get("dmTitle") or "").strip() or None,
        dm_desc_template=str(body.get("dmTemplate") or "").strip() or None,
        dm_embed_color=hex_to_int(body.get("dmColor")),
        dm_image_url=str(body.get("dmImageUrl") or "").strip() or None,
        restock_dm_enabled=1 if body.get("restockDmEnabled") else 0,
        restock_dm_template=str(body.get("restockDmTemplate") or "").strip() or None,
        login_log_channel_id=clean_int(body.get("loginLogChannel")),
    )
    return json_response({"ok": True})


async def handle_login_logs(request: web.Request) -> web.Response:
    require_auth(request)
    rows = await web_repo.list_logins()
    return json_response(
        [
            {
                "id": str(r.get("id")),
                "username": r.get("username") or "",
                "ip": r.get("ip") or "",
                "ok": int(r.get("ok") or 0) == 1,
                "createdAt": ts_to_iso(r.get("created_at")),
            }
            for r in rows
        ]
    )


async def handle_announce(request: web.Request) -> web.Response:
    require_auth(request)
    try:
        body = await request.json()
    except Exception:
        return json_response({"ok": False, "error": "잘못된 요청입니다."}, 400)
    if not isinstance(body, dict):
        return json_response({"ok": False, "error": "잘못된 요청입니다."}, 400)
    title = str(body.get("title") or "").strip()[:256]
    description = str(body.get("description") or "").strip()[:4000]
    if not title and not description:
        return json_response({"ok": False, "error": "제목이나 내용을 입력하세요."}, 400)
    from services import notify
    user_ids = notify.parse_snowflakes(body.get("userIds") or body.get("users") or "")
    extra_ids = notify.parse_snowflakes(body.get("extraUserIds") or "")
    user_ids = list(dict.fromkeys(user_ids + extra_ids))
    role_ids = notify.parse_snowflakes(body.get("roleIds") or body.get("roles") or "")
    channel_id = clean_int(body.get("channelId")) if body.get("postChannel") else None
    buyers = bool(body.get("buyers"))
    if not channel_id and not user_ids and not role_ids and not buyers:
        return json_response({"ok": False, "error": "채널, 역할, 유저 중 하나 이상 선택하세요."}, 400)
    result = await notify.send_announce(
        server_id_from_request(request),
        title=title or "공지",
        description=description,
        color=hex_to_int(body.get("color")) or 0x5865F2,
        image_url=str(body.get("imageUrl") or "").strip() or None,
        channel_id=channel_id,
        user_ids=user_ids,
        role_ids=role_ids,
        buyers=buyers,
    )
    if not result.get("ok"):
        err = result.get("channelError") or result.get("roleWarning") or "공지를 보내지 못했습니다."
        return json_response({"ok": False, "error": err, **result}, 400)
    return json_response({"ok": True, **result})


async def handle_discord_categories(request: web.Request) -> web.Response:
    require_auth(request)
    server_id = server_id_from_request(request)
    guild = discord_guild(server_id)
    if guild is not None:
        cats = [{"id": str(c.id), "name": str(c.name)} for c in getattr(guild, "categories", []) or []]
        return json_response(sorted(cats, key=lambda item: item["name"].lower()))
    data = await discord_api_get(f"/guilds/{int(server_id)}/channels")
    if not isinstance(data, list):
        return json_response([])
    cats = [{"id": str(ch.get("id")), "name": str(ch.get("name") or ch.get("id"))} for ch in data if int(ch.get("type") or -1) == 4]
    return json_response(sorted(cats, key=lambda item: item["name"].lower()))


async def handle_channels(request: web.Request) -> web.Response:
    require_auth(request)
    server_id = server_id_from_request(request)
    guild = discord_guild(server_id)
    if guild is not None:
        channels = []
        for channel in getattr(guild, "text_channels", []) or []:
            parent = getattr(getattr(channel, "category", None), "name", "")
            name = str(getattr(channel, "name", "") or getattr(channel, "id", ""))
            label = f"{parent} / {name}" if parent else name
            channels.append({"id": str(channel.id), "name": label})
        return json_response(sorted(channels, key=lambda item: item["name"].lower()))
    api_channels = await discord_channels_from_api(server_id)
    if api_channels:
        return json_response(api_channels)

    path = await selected_db(request)
    ids: set[str] = set()
    row = await server_repo.get_log_settings(path)
    if row:
        ids.update(str(row.get(k)) for k in ("buy_channel_id", "charge_channel_id", "manual_charge_channel_id", "review_channel_id", "stock_channel_id", "login_log_channel_id") if row.get(k))
    charge = await server_repo.get_charge_settings(path)
    if charge and charge.get("ios_log_channel_id"):
        ids.add(str(charge["ios_log_channel_id"]))
    return json_response([{"id": x, "name": x} for x in sorted(ids)])


async def handle_roles(request: web.Request) -> web.Response:
    require_auth(request)
    server_id = server_id_from_request(request)
    guild = discord_guild(server_id)
    if guild is not None:
        roles = []
        default_role = getattr(guild, "default_role", None)
        for role in getattr(guild, "roles", []) or []:
            if default_role is not None and getattr(role, "id", None) == getattr(default_role, "id", None):
                continue
            roles.append({
                "id": str(role.id),
                "name": str(getattr(role, "name", "") or role.id),
                "position": int(getattr(role, "position", 0) or 0),
            })
        roles.sort(key=lambda item: (-item["position"], item["name"].lower()))
        for role in roles:
            role.pop("position", None)
        return json_response(roles)
    api_roles = await discord_roles_from_api(server_id)
    if api_roles:
        return json_response(api_roles)

    path = await selected_db(request)
    row = await server_repo.get_charge_settings(path)
    role_id = str(row.get("charge_manager_role_id") or "") if row else ""
    return json_response(([{"id": role_id, "name": role_id}] if role_id else []))


def _vip_tier_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id")),
        "name": row.get("name") or "",
        "discountPct": int(row.get("purchaseDiscountPct") or row.get("discountPct") or 0),
        "purchaseDiscountPct": int(row.get("purchaseDiscountPct") or row.get("discountPct") or 0),
        "chargeBonusPct": int(row.get("chargeBonusPct") or 0),
        "unlockSpent": int(row.get("unlockSpent") or 0),
        "color": color_to_hex(row.get("color")) if row.get("color") is not None else "#CD7F32",
        "emoji": row.get("emoji") or "",
        "iconUrl": row.get("iconUrl") or "",
        "position": int(row.get("position") or 0),
    }


async def handle_vip_tiers(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    if request.method == "GET":
        return json_response([_vip_tier_api(t) for t in await server_repo.list_vip_tiers(path)])
    body = await request.json()
    name = str(body.get("name") or "").strip()
    if not name:
        return json_response({"ok": False, "error": "티어 이름을 입력하세요."}, 400)
    try:
        await server_repo.add_vip_tier(
            path,
            name,
            int(body.get("purchaseDiscountPct") or body.get("discountPct") or 0),
            color=hex_to_int(body.get("color")),
            emoji=str(body.get("emoji") or "").strip() or None,
            unlock_spent=int(body.get("unlockSpent") or 0),
            purchase_discount_pct=int(body.get("purchaseDiscountPct") or body.get("discountPct") or 0),
            charge_bonus_pct=int(body.get("chargeBonusPct") or 0),
            icon_url=str(body.get("iconUrl") or "").strip() or None,
        )
    except Exception:
        return json_response({"ok": False, "error": "같은 이름의 티어가 있습니다."}, 400)
    return json_response({"ok": True})


async def handle_vip_tier(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    tid = int(request.match_info["id"])
    if request.method == "DELETE":
        await server_repo.delete_vip_tier(path, tid)
        return json_response({"ok": True})
    body = await request.json()
    fields = {}
    if "name" in body:
        fields["name"] = str(body.get("name") or "").strip()
    if "discountPct" in body or "purchaseDiscountPct" in body:
        fields["purchase_discount_pct"] = int(body.get("purchaseDiscountPct") or body.get("discountPct") or 0)
    if "chargeBonusPct" in body:
        fields["charge_bonus_pct"] = int(body.get("chargeBonusPct") or 0)
    if "unlockSpent" in body:
        fields["unlock_spent"] = int(body.get("unlockSpent") or 0)
    if "color" in body:
        fields["color"] = hex_to_int(body.get("color"))
    if "emoji" in body:
        fields["emoji"] = str(body.get("emoji") or "").strip()
    if "iconUrl" in body:
        fields["icon_url"] = str(body.get("iconUrl") or "").strip()
    try:
        await server_repo.update_vip_tier(path, tid, **fields)
    except Exception:
        return json_response({"ok": False, "error": "티어를 저장하지 못했습니다."}, 400)
    return json_response({"ok": True})


async def handle_vip_reorder(request: web.Request) -> web.Response:
    require_auth(request)
    path = await selected_db(request)
    body = await request.json()
    await server_repo.reorder_vip_tiers(path, [int(x) for x in body.get("order") or []])
    return json_response({"ok": True})


def app() -> web.Application:
    application = web.Application(client_max_size=CLIENT_MAX_SIZE, middlewares=[security_middleware])
    application.router.add_get("/", handle_index)
    application.router.add_get("/assets/{path:.*}", handle_static)
    application.router.add_post("/api/auth/login", handle_login)
    application.router.add_post("/api/auth/logout", handle_logout)
    application.router.add_get("/api/auth/me", handle_me)
    for view in SPA_VIEWS:
        application.router.add_get(f"/{view}", handle_index)
    application.router.add_get("/api/servers", handle_servers)
    application.router.add_get("/api/dashboard", handle_dashboard)
    application.router.add_route("*", "/api/categories", handle_categories)
    application.router.add_put("/api/categories/reorder", handle_category_reorder)
    application.router.add_route("*", "/api/categories/{id}", handle_category)
    application.router.add_route("*", "/api/products", handle_products)
    application.router.add_put("/api/products/reorder", handle_product_reorder)
    application.router.add_route("*", "/api/products/purchase-role", handle_purchase_role_settings)
    application.router.add_route("*", "/api/products/{id}", handle_product)
    application.router.add_put("/api/products/{id}/stock", handle_product_stock)
    application.router.add_get("/api/stock-logs", handle_stock_logs)
    application.router.add_get("/api/orders", handle_orders)
    application.router.add_get("/api/orders/{id}", handle_order)
    application.router.add_get("/api/users", handle_users)
    application.router.add_route("*", "/api/users/{id}", handle_user)
    application.router.add_get("/users/{id}", handle_index)
    application.router.add_route("*", "/api/vip-tiers", handle_vip_tiers)
    application.router.add_put("/api/vip-tiers/reorder", handle_vip_reorder)
    application.router.add_route("*", "/api/vip-tiers/{id}", handle_vip_tier)
    application.router.add_get("/api/charges", handle_charges)
    application.router.add_post("/api/charges/{id}/{action}", handle_charge_action)
    application.router.add_route("*", "/api/settings/charge", handle_charge_settings)
    application.router.add_route("*", "/api/settings/panel", handle_panel_settings)
    application.router.add_route("*", "/api/settings/logs", handle_log_settings)
    application.router.add_get("/api/login-logs", handle_login_logs)
    application.router.add_post("/api/announce", handle_announce)
    application.router.add_get("/api/discord-categories", handle_discord_categories)
    application.router.add_get("/api/channels", handle_channels)
    application.router.add_get("/api/roles", handle_roles)
    return application


if __name__ == "__main__":
    print(f"web panel: http://{WEB_PANEL_HOST}:{WEB_PANEL_PORT}")
    web.run_app(app(), host=WEB_PANEL_HOST, port=WEB_PANEL_PORT)
