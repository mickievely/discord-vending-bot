from __future__ import annotations
from typing import Optional
import asyncio
import re
import time
from pathlib import Path
from db import sqlite as s
from db.cache import SETTINGS

_INIT_DONE: set[str] = set()
_INIT_LOCKS: dict[str, asyncio.Lock] = {}


def _dbk(db_path: Path) -> str:
    return str(db_path.resolve())


def _bust(db_path: Path, *kinds: str) -> None:
    key = _dbk(db_path)
    if not kinds:
        SETTINGS.bust(key)
        return
    want = set(kinds)
    for ck in list(SETTINGS._d):
        if isinstance(ck, tuple) and ck and ck[0] == key and len(ck) > 1 and ck[1] in want:
            SETTINGS.delete(ck)


def bust_catalog(db_path: Path) -> None:
    _bust(db_path, "cats", "products", "pcat")


async def init(db_path: Path):
    key = _dbk(db_path)
    if key in _INIT_DONE:
        return
    lock = _INIT_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        if key in _INIT_DONE:
            return
        await _init_schema(db_path)
        _INIT_DONE.add(key)


async def _init_schema(db_path: Path):
    schema = (Path(__file__).parent / "schema_server.sql").read_text(encoding="utf-8")
    for stmt in [x.strip() for x in schema.split(";") if x.strip()]:
        await s.execute(db_path, stmt)
    row = await s.fetchone(db_path, "SELECT id FROM panel_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO panel_settings(id, title, description, color, image_url) VALUES(1, NULL, NULL, NULL, NULL)")
    cols = await s.fetchall(db_path, "PRAGMA table_info(panel_settings)")
    col_names = {c["name"] for c in cols} if cols else set()
    if "purchase_grant_role_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE panel_settings ADD COLUMN purchase_grant_role_id INTEGER")

    row = await s.fetchone(db_path, "SELECT id FROM charge_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO charge_settings(id, aos_enabled, ios_enabled, pushbullet_token, ios_log_channel_id, aos_bank_name, aos_bank_account, aos_bank_owner, ios_bank_name, ios_bank_account, ios_bank_owner) VALUES(1, 0, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)")

    cols = await s.fetchall(db_path, "PRAGMA table_info(charge_settings)")
    col_names = {c["name"] for c in cols} if cols else set()
    if "aos_enabled" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN aos_enabled INTEGER NOT NULL DEFAULT 0")
    if "ios_enabled" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN ios_enabled INTEGER NOT NULL DEFAULT 0")
    if "ios_log_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN ios_log_channel_id INTEGER")

    if "aos_bank_name" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN aos_bank_name TEXT")
    if "aos_bank_account" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN aos_bank_account TEXT")
    if "aos_bank_owner" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN aos_bank_owner TEXT")

    if "ios_bank_name" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN ios_bank_name TEXT")
    if "ios_bank_account" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN ios_bank_account TEXT")
    if "ios_bank_owner" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN ios_bank_owner TEXT")
    if "charge_manager_role_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN charge_manager_role_id INTEGER")
    if "manual_charge_notice_enabled" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN manual_charge_notice_enabled INTEGER NOT NULL DEFAULT 1")
    if "min_charge_amount" not in col_names:
        await s.execute(db_path, "ALTER TABLE charge_settings ADD COLUMN min_charge_amount INTEGER NOT NULL DEFAULT 1")

    await s.execute(db_path, "CREATE TABLE IF NOT EXISTS ios_pending_charges (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, depositor_name TEXT NOT NULL, created_at INTEGER NOT NULL, status TEXT NOT NULL)")
    await s.execute(db_path, "CREATE TABLE IF NOT EXISTS ios_webhook_dedupe (message_id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL)")

    await s.execute(db_path, "CREATE TABLE IF NOT EXISTS aos_pending_charges (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, depositor_name TEXT NOT NULL, created_at INTEGER NOT NULL, status TEXT NOT NULL)")

    cols = await s.fetchall(db_path, "PRAGMA table_info(ios_pending_charges)")
    col_names = {c["name"] for c in cols} if cols else set()
    if "request_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE ios_pending_charges ADD COLUMN request_channel_id INTEGER")
    if "request_message_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE ios_pending_charges ADD COLUMN request_message_id INTEGER")

    cols = await s.fetchall(db_path, "PRAGMA table_info(aos_pending_charges)")
    col_names = {c["name"] for c in cols} if cols else set()
    if "request_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE aos_pending_charges ADD COLUMN request_channel_id INTEGER")
    if "request_message_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE aos_pending_charges ADD COLUMN request_message_id INTEGER")

    await s.execute(db_path, "CREATE TABLE IF NOT EXISTS log_settings (id INTEGER PRIMARY KEY CHECK(id=1), buy_channel_id INTEGER, buy_desc_template TEXT, charge_channel_id INTEGER, review_channel_id INTEGER, stock_channel_id INTEGER, stock_desc_template TEXT, charge_desc_template TEXT, review_desc_template TEXT)")
    cols = await s.fetchall(db_path, "PRAGMA table_info(log_settings)")
    col_names = {c["name"] for c in cols} if cols else set()
    if "buy_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN buy_channel_id INTEGER")
    if "buy_webhook_url" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN buy_webhook_url TEXT")
    if "buy_title_template" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN buy_title_template TEXT")
    if "buy_desc_template" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN buy_desc_template TEXT")
    if "charge_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN charge_channel_id INTEGER")
    if "charge_webhook_url" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN charge_webhook_url TEXT")
    if "review_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN review_channel_id INTEGER")
    if "stock_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN stock_channel_id INTEGER")
    if "stock_desc_template" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN stock_desc_template TEXT")
    if "charge_desc_template" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN charge_desc_template TEXT")
    if "review_desc_template" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN review_desc_template TEXT")
    if "manual_charge_channel_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE log_settings ADD COLUMN manual_charge_channel_id INTEGER")
    extra_log_cols = [
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
    for name, decl in extra_log_cols:
        if name not in col_names:
            await s.execute(db_path, f"ALTER TABLE log_settings ADD COLUMN {name} {decl}")
            col_names.add(name)
    row = await s.fetchone(db_path, "SELECT id FROM log_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO log_settings(id, buy_channel_id, buy_desc_template, charge_channel_id, review_channel_id, stock_channel_id, stock_desc_template, restock_dm_enabled) VALUES(1, NULL, '{유저}님 {카테고리} • {제품} 구매 감사합니다', NULL, NULL, NULL, '{제품} >> {수량}개 추가', 0)")

    for table in ("ios_pending_charges", "aos_pending_charges"):
        cols = await s.fetchall(db_path, f"PRAGMA table_info({table})")
        names = {c["name"] for c in cols} if cols else set()
        if "approved_by" not in names:
            await s.execute(db_path, f"ALTER TABLE {table} ADD COLUMN approved_by INTEGER")
        if "approved_at" not in names:
            await s.execute(db_path, f"ALTER TABLE {table} ADD COLUMN approved_at INTEGER")
        if "approved_by_name" not in names:
            await s.execute(db_path, f"ALTER TABLE {table} ADD COLUMN approved_by_name TEXT")

    cols = await s.fetchall(db_path, "PRAGMA table_info(products)")
    col_names = {c["name"] for c in cols} if cols else set()
    if "grant_role_id" not in col_names:
        await s.execute(db_path, "ALTER TABLE products ADD COLUMN grant_role_id INTEGER")

    await s.execute(
        db_path,
        """
        CREATE TABLE IF NOT EXISTS stock_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          product_id INTEGER,
          product_name TEXT,
          category_name TEXT,
          action TEXT NOT NULL,
          qty INTEGER NOT NULL,
          before_count INTEGER NOT NULL DEFAULT 0,
          after_count INTEGER NOT NULL DEFAULT 0,
          actor_id INTEGER,
          source TEXT,
          created_at INTEGER NOT NULL,
          FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
        )
        """,
    )
    for sql in (
        "CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_orders_status_created ON orders(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_stocks_product_free ON stocks(product_id, consumed_at)",
        "CREATE INDEX IF NOT EXISTS idx_aos_user ON aos_pending_charges(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_ios_user ON ios_pending_charges(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_aos_status ON aos_pending_charges(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_ios_status ON ios_pending_charges(status, created_at)",
    ):
        await s.execute(db_path, sql)
    await _ensure_vip(db_path)

async def get_panel(db_path: Path):
    ck = (_dbk(db_path), "panel")
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    row = await s.fetchone(db_path, "SELECT title, description, color, image_url FROM panel_settings WHERE id=1")
    SETTINGS.set(ck, row)
    return row

async def set_panel(db_path: Path, title: Optional[str], description: Optional[str], color: Optional[int], image_url: Optional[str]):
    await s.execute(db_path, "UPDATE panel_settings SET title=?, description=?, color=?, image_url=? WHERE id=1", (title, description, color, image_url))
    _bust(db_path, "panel")

async def get_purchase_grant_role(db_path: Path):
    ck = (_dbk(db_path), "grant_role")
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    row = await s.fetchone(db_path, "SELECT purchase_grant_role_id FROM panel_settings WHERE id=1")
    val = int(row["purchase_grant_role_id"]) if row and row["purchase_grant_role_id"] else None
    SETTINGS.set(ck, val)
    return val

async def set_purchase_grant_role(db_path: Path, role_id: Optional[int]):
    await s.execute(
        db_path,
        "UPDATE panel_settings SET purchase_grant_role_id=? WHERE id=1",
        (int(role_id) if role_id else None,),
    )
    _bust(db_path, "panel", "grant_role")

async def add_category(db_path: Path, name: str, position: int = 0):
    await s.execute(db_path, "INSERT INTO categories(name, position) VALUES(?,?)", (name, position))
    _bust(db_path, "cats", "products")

async def delete_category(db_path: Path, category_id: int):
    async def _fn(conn):
        cur = await conn.execute("SELECT id FROM products WHERE category_id=?", (int(category_id),))
        rows = await cur.fetchall()
        pids = [int(r["id"]) for r in (rows or [])]
        if pids:
            q = ",".join(["?"] * len(pids))
            await conn.execute(f"DELETE FROM orders WHERE product_id IN ({q})", tuple(pids))
        await conn.execute("DELETE FROM categories WHERE id=?", (int(category_id),))
        return True

    await s.tx(db_path, _fn)
    _bust(db_path, "cats", "products", "pcat")

async def list_categories(db_path: Path):
    ck = (_dbk(db_path), "cats")
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    rows = await s.fetchall(db_path, "SELECT id, name FROM categories ORDER BY position ASC, id ASC")
    SETTINGS.set(ck, rows)
    return rows

async def add_product(db_path: Path, category_id: int, name: str, price: int, description: Optional[str], position: int = 0, grant_role_id: Optional[int] = None):
    now = int(time.time())
    await s.execute(db_path, "INSERT INTO products(category_id, name, price, description, grant_role_id, position, created_at) VALUES(?,?,?,?,?,?,?)",
                    (category_id, name, price, description, int(grant_role_id) if grant_role_id else None, position, now))
    _bust(db_path, "products", "pcat")

async def delete_product(db_path: Path, product_id: int):
    async def _fn(conn):
        await conn.execute("DELETE FROM orders WHERE product_id=?", (int(product_id),))
        await conn.execute("DELETE FROM products WHERE id=?", (int(product_id),))
        return True

    await s.tx(db_path, _fn)
    _bust(db_path, "products", "pcat")

async def list_products(db_path: Path):
    ck = (_dbk(db_path), "products")
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    sql = (
        "SELECT p.id, c.name as category, p.name, p.price, p.grant_role_id "
        "FROM products p JOIN categories c ON c.id=p.category_id "
        "ORDER BY c.position ASC, p.position ASC, p.id ASC"
    )
    rows = await s.fetchall(db_path, sql)
    SETTINGS.set(ck, rows)
    return rows

async def products_in_category(db_path: Path, category_id: int):
    ck = (_dbk(db_path), "pcat", int(category_id))
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    rows = await s.fetchall(db_path, "SELECT id, name, price, description, grant_role_id FROM products WHERE category_id=? ORDER BY position ASC, id ASC", (category_id,))
    SETTINGS.set(ck, rows)
    return rows

async def product_by_id(db_path: Path, product_id: int):
    return await s.fetchone(db_path, "SELECT id, category_id, name, price, description, grant_role_id FROM products WHERE id=?", (product_id,))

async def product_with_category(db_path: Path, product_id: int):
    return await s.fetchone(
        db_path,
        """
        SELECT p.id, p.category_id, p.name, p.price, p.description, p.grant_role_id, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON c.id=p.category_id
        WHERE p.id=?
        """,
        (int(product_id),),
    )

async def stock_count(db_path: Path, product_id: int):
    row = await s.fetchone(db_path, "SELECT COUNT(*) as cnt FROM stocks WHERE product_id=? AND consumed_at IS NULL", (product_id,))
    return int(row["cnt"]) if row else 0


async def stock_counts(db_path: Path, product_ids: list[int]) -> dict[int, int]:
    ids = [int(x) for x in product_ids]
    out = {pid: 0 for pid in ids}
    if not ids:
        return out
    q = ",".join(["?"] * len(ids))
    rows = await s.fetchall(
        db_path,
        f"SELECT product_id, COUNT(*) as cnt FROM stocks WHERE consumed_at IS NULL AND product_id IN ({q}) GROUP BY product_id",
        tuple(ids),
    )
    for row in rows or []:
        out[int(row["product_id"])] = int(row["cnt"] or 0)
    return out

async def add_stock_lines(db_path: Path, product_id: int, lines: list[str]):
    now = int(time.time())
    seq = [(product_id, line, now) for line in lines if line.strip()]
    await s.executemany(db_path, "INSERT INTO stocks(product_id, value, created_at) VALUES(?,?,?)", seq)

async def stock_lines(db_path: Path, product_id: int):
    rows = await s.fetchall(db_path, "SELECT value FROM stocks WHERE product_id=? AND consumed_at IS NULL ORDER BY id ASC", (product_id,))
    return [str(r["value"]) for r in (rows or [])]

async def set_stock_lines(db_path: Path, product_id: int, lines: list[str]):
    now = int(time.time())
    seq = [(product_id, line, now) for line in lines if line.strip()]

    async def _fn(conn):
        await conn.execute("DELETE FROM stocks WHERE product_id=? AND consumed_at IS NULL", (product_id,))
        if seq:
            await conn.executemany("INSERT INTO stocks(product_id, value, created_at) VALUES(?,?,?)", seq)
        return True

    await s.tx(db_path, _fn)

async def reset_stock(db_path: Path, product_id: int):
    await s.execute(db_path, "DELETE FROM stocks WHERE product_id=?", (product_id,))

async def add_stock_log(
    db_path: Path,
    product_id: int,
    *,
    action: str,
    qty: int,
    before_count: int,
    after_count: int,
    actor_id: Optional[int] = None,
    source: Optional[str] = None,
):
    product = await product_with_category(db_path, int(product_id))
    now = int(time.time())
    await s.execute(
        db_path,
        """
        INSERT INTO stock_logs(product_id, product_name, category_name, action, qty, before_count, after_count, actor_id, source, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(product_id),
            str(product.get("name") or "") if product else None,
            str(product.get("category_name") or "") if product else None,
            str(action or "add"),
            int(qty),
            int(before_count),
            int(after_count),
            int(actor_id) if actor_id else None,
            str(source or "") or None,
            now,
        ),
    )
    return {
        "product_id": int(product_id),
        "product_name": str(product.get("name") or "") if product else "",
        "category_name": str(product.get("category_name") or "") if product else "",
        "action": str(action or "add"),
        "qty": int(qty),
        "before_count": int(before_count),
        "after_count": int(after_count),
        "actor_id": int(actor_id) if actor_id else None,
        "source": str(source or "") or None,
        "created_at": now,
    }

async def list_stock_logs(db_path: Path, limit: int = 200):
    return await s.fetchall(
        db_path,
        """
        SELECT id, product_id, product_name, category_name, action, qty, before_count, after_count, actor_id, source, created_at
        FROM stock_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit),),
    )

async def get_balance(db_path: Path, user_id: int) -> int:
    row = await s.fetchone(db_path, "SELECT balance FROM balances WHERE user_id=?", (user_id,))
    return int(row["balance"]) if row else 0

async def user_stats(db_path: Path, user_id: int):
    bal = await get_balance(db_path, user_id)
    row = await s.fetchone(
        db_path,
        "SELECT COUNT(*) as orders, COALESCE(SUM(qty),0) as items, COALESCE(SUM(total),0) as spent, MAX(created_at) as last_at FROM orders WHERE user_id=?",
        (user_id,),
    )
    vip = await get_user_vip(db_path, user_id)
    return {
        "balance": int(bal),
        "orders": int(row["orders"] if row else 0),
        "items": int(row["items"] if row else 0),
        "spent": int(row["spent"] if row else 0),
        "last_at": int(row["last_at"]) if row and row["last_at"] is not None else None,
        "vip": vip,
    }

async def add_balance(db_path: Path, user_id: int, delta: int):
    now = int(time.time())
    async def _fn(conn):
        cur = await conn.execute("SELECT balance FROM balances WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        cur_bal = int(row["balance"]) if row else 0
        new_bal = cur_bal + int(delta)
        if new_bal < 0:
            return {"ok": False, "balance": cur_bal}
        await conn.execute(
            "INSERT INTO balances(user_id, balance, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at",
            (user_id, new_bal, now)
        )
        return {"ok": True, "balance": new_bal}
    return await s.tx(db_path, _fn)

async def apply_charge_once(db_path: Path, user_id: int, processed_at: str, amount: int) -> bool:
    async def _fn(conn):
        try:
            await conn.execute("INSERT INTO applied_charges(user_id, processed_at, amount) VALUES(?,?,?)", (user_id, processed_at, amount))
            return True
        except Exception:
            return False
    return await s.tx(db_path, _fn)

class _StockConflict(Exception):
    pass


async def purchase(db_path: Path, user_id: int, product_id: int, qty: int):
    now = int(time.time())
    qty = int(qty)
    vip = await get_user_vip(db_path, user_id)
    pct = int((vip or {}).get("purchaseDiscountPct") or 0)

    async def _fn(conn):
        curp = await conn.execute("SELECT p.id, p.name, p.price, p.description, p.grant_role_id, p.category_id, c.name as category_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.id=?", (product_id,))
        p = await curp.fetchone()
        if not p:
            return {"ok": False, "error": "product_not_found"}

        curbal = await conn.execute("SELECT balance FROM balances WHERE user_id=?", (user_id,))
        b = await curbal.fetchone()
        bal = int(b["balance"]) if b else 0

        original = int(p["price"]) * qty
        total, saved = sale_total(int(p["price"]), qty, pct)
        if bal < total:
            return {"ok": False, "error": "no_money", "balance": bal, "total": total, "original": original, "discount_pct": pct}

        curst = await conn.execute(
            "SELECT id, value FROM stocks WHERE product_id=? AND consumed_at IS NULL ORDER BY id ASC LIMIT ?",
            (product_id, qty)
        )
        rows = await curst.fetchall()
        if len(rows) < qty:
            return {"ok": False, "error": "no_stock", "stock": len(rows)}

        await conn.execute(
            "INSERT INTO orders(user_id, product_id, qty, total, created_at, status, delivered_text, original_total, discount_pct) VALUES(?,?,?,?,?,?,?,?,?)",
            (user_id, product_id, qty, total, now, "completed", None, original, pct)
        )
        curid = await conn.execute("SELECT last_insert_rowid() as oid")
        oid = int((await curid.fetchone())["oid"])

        ids = [int(r["id"]) for r in rows]
        values = [str(r["value"]) for r in rows]
        delivered = "\n".join(values)

        updated = 0
        for sid in ids:
            await conn.execute(
                "UPDATE stocks SET consumed_at=?, consumed_by=?, order_id=? WHERE id=? AND consumed_at IS NULL",
                (now, user_id, oid, sid),
            )
            changed = await conn.execute("SELECT changes() AS n")
            row = await changed.fetchone()
            count = row["n"] if isinstance(row, dict) else row[0]
            updated += int(count or 0)
        if updated != len(ids):
            raise _StockConflict()

        new_bal = bal - total
        await conn.execute(
            "INSERT INTO balances(user_id, balance, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at",
            (user_id, new_bal, now)
        )
        await conn.execute("UPDATE orders SET delivered_text=? WHERE id=?", (delivered, oid))
        return {
            "ok": True,
            "order_id": oid,
            "delivered": delivered,
            "balance": new_bal,
            "total": total,
            "original": original,
            "discount_pct": pct,
            "saved": saved,
            "vip_name": str(vip["name"]) if vip and vip.get("name") else None,
            "category_name": str(p["category_name"]),
            "product_name": p["name"],
            "qty": qty,
            "grant_role_id": int(p["grant_role_id"]) if p["grant_role_id"] else None,
        }

    try:
        out = await s.tx(db_path, _fn)
    except _StockConflict:
        return {"ok": False, "error": "no_stock", "stock": 0}
    if isinstance(out, dict) and out.get("ok"):
        await refresh_auto_vip(db_path, user_id)
    return out


async def list_user_charges(db_path: Path, user_id: int, limit: int = 12) -> list[dict]:
    rows = []
    for platform, table in (("AOS", "aos_pending_charges"), ("IOS", "ios_pending_charges")):
        found = await s.fetchall(
            db_path,
            f"SELECT id, amount, depositor_name, created_at, status FROM {table} WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (int(user_id), max(1, min(30, int(limit)))),
        )
        for row in found or []:
            item = dict(row)
            item["platform"] = platform
            rows.append(item)
    rows.sort(key=lambda r: int(r.get("created_at") or 0), reverse=True)
    return rows[: max(1, min(30, int(limit)))]


async def order_by_id(db_path: Path, order_id: int):
    sql = (
        "SELECT o.id, o.user_id, o.product_id, o.qty, o.total, o.created_at, o.status, "
        "p.name as product_name, c.name as category_name "
        "FROM orders o "
        "JOIN products p ON p.id=o.product_id "
        "JOIN categories c ON c.id=p.category_id "
        "WHERE o.id=?"
    )
    return await s.fetchone(db_path, sql, (int(order_id),))


async def add_vending_machine(db_path: Path, name: str, category_id: int):
    now = int(time.time())
    await s.execute(db_path, "INSERT INTO vending_machines(name, category_id, created_at) VALUES(?,?,?)", (name, category_id, now))

async def list_vending_machines(db_path: Path):
    sql = "SELECT vm.id, vm.name, vm.category_id, c.name as category FROM vending_machines vm JOIN categories c ON c.id=vm.category_id ORDER BY vm.id ASC"
    return await s.fetchall(db_path, sql)

async def vending_machine_by_id(db_path: Path, vm_id: int):
    sql = "SELECT vm.id, vm.name, vm.category_id, c.name as category FROM vending_machines vm JOIN categories c ON c.id=vm.category_id WHERE vm.id=?"
    return await s.fetchone(db_path, sql, (vm_id,))


async def get_charge_settings(db_path: Path):
    ck = (_dbk(db_path), "charge")
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    row = await s.fetchone(
        db_path,
        "SELECT aos_enabled, ios_enabled, pushbullet_token, ios_log_channel_id, aos_bank_name, aos_bank_account, aos_bank_owner, ios_bank_name, ios_bank_account, ios_bank_owner, charge_manager_role_id, manual_charge_notice_enabled, min_charge_amount "
        "FROM charge_settings WHERE id=1",
    )
    SETTINGS.set(ck, row)
    return row

async def set_charge_manager_role(db_path: Path, role_id: Optional[int]):
    row = await s.fetchone(db_path, "SELECT id FROM charge_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO charge_settings(id, aos_enabled, ios_enabled) VALUES(1, 0, 0)")
    await s.execute(
        db_path,
        "UPDATE charge_settings SET charge_manager_role_id=? WHERE id=1",
        (int(role_id) if role_id else None,),
    )
    _bust(db_path, "charge")

async def set_aos_charge_settings(
    db_path: Path,
    bank_name: str,
    bank_account: str,
    bank_owner: str,
    pushbullet_token: Optional[str],
):
    row = await s.fetchone(db_path, "SELECT id FROM charge_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO charge_settings(id, aos_enabled, ios_enabled) VALUES(1, 0, 0)")
    enabled = 1 if all(str(x or "").strip() for x in (bank_name, bank_account, bank_owner, pushbullet_token)) else 0
    await s.execute(
        db_path,
        "UPDATE charge_settings SET aos_enabled=?, aos_bank_name=?, aos_bank_account=?, aos_bank_owner=?, pushbullet_token=? WHERE id=1",
        (enabled, bank_name, bank_account, bank_owner, pushbullet_token),
    )
    _bust(db_path, "charge")

async def set_ios_charge_settings(
    db_path: Path,
    bank_name: str,
    bank_account: str,
    bank_owner: str,
    ios_log_channel_id: int,
):
    row = await s.fetchone(db_path, "SELECT id FROM charge_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO charge_settings(id, aos_enabled, ios_enabled) VALUES(1, 0, 0)")
    enabled = 1 if all(str(x or "").strip() for x in (bank_name, bank_account, bank_owner)) and int(ios_log_channel_id or 0) > 0 else 0
    await s.execute(
        db_path,
        "UPDATE charge_settings SET ios_enabled=?, ios_bank_name=?, ios_bank_account=?, ios_bank_owner=?, ios_log_channel_id=? WHERE id=1",
        (enabled, bank_name, bank_account, bank_owner, int(ios_log_channel_id) if ios_log_channel_id else None),
    )
    _bust(db_path, "charge")

async def set_manual_charge_notice_enabled(db_path: Path, enabled: bool):
    row = await s.fetchone(db_path, "SELECT id FROM charge_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO charge_settings(id, aos_enabled, ios_enabled) VALUES(1, 0, 0)")
    await s.execute(
        db_path,
        "UPDATE charge_settings SET manual_charge_notice_enabled=? WHERE id=1",
        (1 if enabled else 0,),
    )
    _bust(db_path, "charge")

async def set_min_charge_amount(db_path: Path, amount: int):
    row = await s.fetchone(db_path, "SELECT id FROM charge_settings WHERE id=1")
    if not row:
        await s.execute(db_path, "INSERT INTO charge_settings(id, aos_enabled, ios_enabled) VALUES(1, 0, 0)")
    minimum = max(1, int(amount or 1))
    await s.execute(
        db_path,
        "UPDATE charge_settings SET min_charge_amount=? WHERE id=1",
        (minimum,),
    )
    _bust(db_path, "charge")

async def disable_aos_charge(db_path: Path):
    await s.execute(db_path, "UPDATE charge_settings SET aos_enabled=0 WHERE id=1")
    _bust(db_path, "charge")


async def get_log_settings(db_path: Path):
    ck = (_dbk(db_path), "log")
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    row = await s.fetchone(db_path, "SELECT * FROM log_settings WHERE id=1")
    SETTINGS.set(ck, row)
    return row

async def set_log_settings(db_path: Path, **fields):
    _bust(db_path, "log")
    cur = await get_log_settings(db_path)
    cur = dict(cur) if cur else {}
    if not cur:
        await s.execute(db_path, "INSERT INTO log_settings(id) VALUES(1)")
        _bust(db_path, "log")
        cur = dict(await get_log_settings(db_path) or {"id": 1})
    cur.update(fields)
    cur.pop("id", None)
    if not cur:
        return
    sets = ", ".join(f"{k}=?" for k in cur)
    await s.execute(db_path, f"UPDATE log_settings SET {sets} WHERE id=1", tuple(cur.values()))
    _bust(db_path, "log")

async def list_buyer_ids(db_path: Path) -> list[int]:
    rows = await s.fetchall(
        db_path,
        "SELECT DISTINCT user_id FROM orders WHERE status='completed' ORDER BY user_id ASC",
    )
    return [int(r["user_id"]) for r in (rows or []) if r.get("user_id")]

async def list_user_purchases(db_path: Path, user_id: int, limit: int = 30):
    return await s.fetchall(
        db_path,
        """
        SELECT o.id, o.product_id, o.qty, o.total, o.created_at, p.name AS product_name, p.price
        FROM orders o
        JOIN products p ON p.id=o.product_id
        WHERE o.user_id=? AND o.status='completed'
        ORDER BY o.id DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    )

async def set_charge_approval(
    db_path: Path,
    platform: str,
    pid: int,
    *,
    actor_id: Optional[int],
    actor_name: Optional[str],
    approved_at: Optional[int] = None,
):
    tbl = "ios_pending_charges" if str(platform).upper() == "IOS" else "aos_pending_charges"
    await s.execute(
        db_path,
        f"UPDATE {tbl} SET approved_by=?, approved_by_name=?, approved_at=? WHERE id=?",
        (
            int(actor_id) if actor_id else None,
            str(actor_name) if actor_name else None,
            int(approved_at if approved_at is not None else time.time()),
            int(pid),
        ),
    )

async def set_pending_request_message(db_path: Path, platform: str, pid: int, channel_id: int, message_id: int):
    tbl = "ios_pending_charges" if platform.upper() == "IOS" else "aos_pending_charges"
    await s.execute(db_path, f"UPDATE {tbl} SET request_channel_id=?, request_message_id=? WHERE id=?", (int(channel_id), int(message_id), int(pid)))

async def get_pending_by_id(db_path: Path, platform: str, pid: int):
    tbl = "ios_pending_charges" if platform.upper() == "IOS" else "aos_pending_charges"
    return await s.fetchone(db_path, f"SELECT * FROM {tbl} WHERE id=?", (int(pid),))

async def aos_find_match_pending(db_path: Path, amount: int, depositor_name: Optional[str]):
    now = int(time.time())
    rows = await s.fetchall(
        db_path,
        "SELECT * FROM aos_pending_charges WHERE status='pending' AND amount=? AND created_at>=? ORDER BY id ASC",
        (int(amount), now-300),
    )
    if not depositor_name:
        if not rows or len(rows) != 1:
            return None
        return rows[0]
    target = re.sub(r"[^0-9A-Za-z가-힣]", "", str(depositor_name).replace("님", "").replace(" ", "")).lower()
    matches = []
    for row in rows or []:
        name = re.sub(r"[^0-9A-Za-z가-힣]", "", str((row or {}).get("depositor_name") or "").replace("님", "").replace(" ", "")).lower()
        if not name or not target:
            continue
        if name == target or name in target or target in name:
            matches.append(row)
    if len(matches) != 1:
        return None
    return matches[0]

async def aos_mark_done(db_path: Path, pid: int):
    await s.execute(db_path, "UPDATE aos_pending_charges SET status='done' WHERE id=?", (int(pid),))


def _pending_table(platform: str) -> str:
    if str(platform or "").upper() == "IOS":
        return "ios_pending_charges"
    return "aos_pending_charges"


async def claim_pending_charge(db_path: Path, platform: str, pid: int) -> bool:
    table = _pending_table(platform)

    async def _fn(conn):
        await conn.execute(
            f"UPDATE {table} SET status='processing' WHERE id=? AND status='pending'",
            (int(pid),),
        )
        cur = await conn.execute("SELECT changes() AS n")
        row = await cur.fetchone()
        count = row["n"] if isinstance(row, dict) else row[0]
        return int(count or 0) == 1

    return bool(await s.tx(db_path, _fn))


async def release_pending_charge(db_path: Path, platform: str, pid: int) -> None:
    table = _pending_table(platform)
    await s.execute(
        db_path,
        f"UPDATE {table} SET status='pending' WHERE id=? AND status='processing'",
        (int(pid),),
    )


async def forget_charge_once(db_path: Path, user_id: int, processed_at: str, amount: int) -> None:
    await s.execute(
        db_path,
        "DELETE FROM applied_charges WHERE user_id=? AND processed_at=? AND amount=?",
        (int(user_id), str(processed_at), int(amount)),
    )

async def aos_mark_rejected(db_path: Path, pid: int):
    await s.execute(db_path, "UPDATE aos_pending_charges SET status='rejected' WHERE id=?", (int(pid),))

async def disable_ios_charge(db_path: Path):
    await s.execute(db_path, "UPDATE charge_settings SET ios_enabled=0 WHERE id=1")
    _bust(db_path, "charge")



async def ios_create_pending(db_path: Path, user_id: int, amount: int, depositor_name: str) -> int:
    now = int(time.time())
    async def _tx(conn):
        cur = await conn.execute("INSERT INTO ios_pending_charges(user_id, amount, depositor_name, created_at, status) VALUES(?,?,?,?,?)", (int(user_id), int(amount), str(depositor_name), now, "pending"))
        return int(cur.lastrowid or 0)
    return await s.tx(db_path, _tx)

async def ios_find_match_pending(db_path: Path, amount: int, depositor_name: Optional[str]):
    now = int(time.time())
    rows = await s.fetchall(
        db_path,
        "SELECT * FROM ios_pending_charges WHERE status='pending' AND amount=? AND created_at>=? ORDER BY id ASC",
        (int(amount), now-300),
    )
    if not depositor_name:
        if not rows or len(rows) != 1:
            return None
        return rows[0]
    target = re.sub(r"[^0-9A-Za-z가-힣]", "", str(depositor_name).replace("님", "").replace(" ", "")).lower()
    matches = []
    for row in rows or []:
        name = re.sub(r"[^0-9A-Za-z가-힣]", "", str((row or {}).get("depositor_name") or "").replace("님", "").replace(" ", "")).lower()
        if not name or not target:
            continue
        if name == target or name in target or target in name:
            matches.append(row)
    if len(matches) != 1:
        return None
    return matches[0]

async def ios_mark_done(db_path: Path, pid: int, message_id: int):
    await s.execute(db_path, "UPDATE ios_pending_charges SET status='done' WHERE id=?", (int(pid),))
    await s.execute(db_path, "INSERT OR IGNORE INTO ios_webhook_dedupe(message_id, created_at) VALUES(?,?)", (int(message_id), int(time.time())))
async def ios_mark_rejected(db_path: Path, pid: int):
    await s.execute(db_path, "UPDATE ios_pending_charges SET status='rejected' WHERE id=?", (int(pid),))



async def ios_is_deduped(db_path: Path, message_id: int) -> bool:
    row = await s.fetchone(db_path, "SELECT message_id FROM ios_webhook_dedupe WHERE message_id=?", (int(message_id),))
    return bool(row)


async def aos_create_pending(db_path: Path, user_id: int, amount: int, depositor_name: str) -> int:
    now = int(time.time())
    async def _tx(conn):
        cur = await conn.execute("INSERT INTO aos_pending_charges(user_id, amount, depositor_name, created_at, status) VALUES(?,?,?,?,?)", (int(user_id), int(amount), str(depositor_name), now, "pending"))
        return int(cur.lastrowid or 0)
    return await s.tx(db_path, _tx)

async def total_spent(db_path: Path, user_id: int) -> int:
    row = await s.fetchone(db_path, "SELECT COALESCE(SUM(total),0) as s FROM orders WHERE user_id=? AND status='completed'", (user_id,))
    return int(row["s"]) if row else 0


_VAL_CDN = "https://media.valorant-api.com/competitivetiers/03621f52-342b-cf4e-4f86-9350a49c6d04"
ICON_BY_NAME = {
    "아이언": f"{_VAL_CDN}/3/largeicon.png",
    "브론즈": f"{_VAL_CDN}/6/largeicon.png",
    "실버": f"{_VAL_CDN}/9/largeicon.png",
    "골드": f"{_VAL_CDN}/12/largeicon.png",
    "플래티넘": f"{_VAL_CDN}/15/largeicon.png",
    "다이아": f"{_VAL_CDN}/18/largeicon.png",
    "초월": f"{_VAL_CDN}/21/largeicon.png",
    "불멸": f"{_VAL_CDN}/24/largeicon.png",
    "레디언트": f"{_VAL_CDN}/27/largeicon.png",
}
DEFAULT_VIP_TIERS = (
    ("브론즈", 5, 3, 0xCD7F32, "🥉", 10, 30000),
    ("실버", 8, 5, 0xC0C4CC, "🥈", 20, 80000),
    ("골드", 12, 7, 0xFFD166, "🥇", 30, 150000),
    ("플래티넘", 16, 8, 0x7FFFD4, "💠", 40, 300000),
    ("다이아", 20, 10, 0x6ECBFF, "💎", 50, 500000),
    ("불멸", 25, 12, 0xE84A5F, "🔥", 60, 800000),
    ("레디언트", 30, 15, 0xF4E285, "👑", 70, 1500000),
)
UNLOCK_BY_NAME = {row[0]: row[6] for row in DEFAULT_VIP_TIERS}
CHARGE_BY_NAME = {row[0]: row[2] for row in DEFAULT_VIP_TIERS}


def sale_total(unit_price: int, qty: int, discount_pct: int) -> tuple[int, int]:
    subtotal = max(0, int(unit_price)) * max(0, int(qty))
    pct = max(0, min(100, int(discount_pct or 0)))
    if pct <= 0:
        return subtotal, 0
    total = (subtotal * (100 - pct)) // 100
    return total, subtotal - total


async def _ensure_vip(db_path: Path):
    await s.execute(
        db_path,
        """
        CREATE TABLE IF NOT EXISTS vip_tiers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          discount_pct INTEGER NOT NULL DEFAULT 0,
          color INTEGER,
          emoji TEXT,
          position INTEGER NOT NULL DEFAULT 0
        )
        """,
    )
    await s.execute(
        db_path,
        """
        CREATE TABLE IF NOT EXISTS user_vip (
          user_id INTEGER PRIMARY KEY,
          tier_id INTEGER NOT NULL,
          FOREIGN KEY (tier_id) REFERENCES vip_tiers(id) ON DELETE CASCADE
        )
        """,
    )
    await s.execute(db_path, "CREATE INDEX IF NOT EXISTS idx_user_vip_tier ON user_vip(tier_id)")
    tier_cols = {c["name"] for c in await s.fetchall(db_path, "PRAGMA table_info(vip_tiers)") or []}
    if "unlock_spent" not in tier_cols:
        await s.execute(db_path, "ALTER TABLE vip_tiers ADD COLUMN unlock_spent INTEGER NOT NULL DEFAULT 0")
        for name, spent in UNLOCK_BY_NAME.items():
            await s.execute(db_path, "UPDATE vip_tiers SET unlock_spent=? WHERE name=? AND unlock_spent=0", (int(spent), name))
        tier_cols.add("unlock_spent")
    if "purchase_discount_pct" not in tier_cols:
        await s.execute(db_path, "ALTER TABLE vip_tiers ADD COLUMN purchase_discount_pct INTEGER NOT NULL DEFAULT 0")
        await s.execute(db_path, "UPDATE vip_tiers SET purchase_discount_pct = COALESCE(discount_pct, 0) WHERE purchase_discount_pct = 0")
        tier_cols.add("purchase_discount_pct")
    if "charge_bonus_pct" not in tier_cols:
        await s.execute(db_path, "ALTER TABLE vip_tiers ADD COLUMN charge_bonus_pct INTEGER NOT NULL DEFAULT 0")
        for name, pct in CHARGE_BY_NAME.items():
            await s.execute(db_path, "UPDATE vip_tiers SET charge_bonus_pct=? WHERE name=? AND charge_bonus_pct=0", (int(pct), name))
        tier_cols.add("charge_bonus_pct")
    if "icon_url" not in tier_cols:
        await s.execute(db_path, "ALTER TABLE vip_tiers ADD COLUMN icon_url TEXT")
        tier_cols.add("icon_url")
    for name, url in ICON_BY_NAME.items():
        await s.execute(
            db_path,
            "UPDATE vip_tiers SET icon_url=? WHERE name=? AND (icon_url IS NULL OR icon_url='')",
            (url, name),
        )
    uv_cols = {c["name"] for c in await s.fetchall(db_path, "PRAGMA table_info(user_vip)") or []}
    if "manual" not in uv_cols:
        await s.execute(db_path, "ALTER TABLE user_vip ADD COLUMN manual INTEGER NOT NULL DEFAULT 1")
    order_cols = {c["name"] for c in await s.fetchall(db_path, "PRAGMA table_info(orders)") or []}
    if "original_total" not in order_cols:
        await s.execute(db_path, "ALTER TABLE orders ADD COLUMN original_total INTEGER")
    if "discount_pct" not in order_cols:
        await s.execute(db_path, "ALTER TABLE orders ADD COLUMN discount_pct INTEGER NOT NULL DEFAULT 0")
    row = await s.fetchone(db_path, "SELECT COUNT(*) AS n FROM vip_tiers")
    if int((row or {}).get("n") or 0) == 0:
        await s.executemany(
            db_path,
            "INSERT INTO vip_tiers(name, discount_pct, purchase_discount_pct, charge_bonus_pct, color, emoji, position, unlock_spent, icon_url) VALUES(?,?,?,?,?,?,?,?,?)",
            [(n, p, p, c, color, emoji, pos, unlock, ICON_BY_NAME.get(n)) for n, p, c, color, emoji, pos, unlock in DEFAULT_VIP_TIERS],
        )


def _vip_payload(row) -> dict:
    if not row:
        return {}
    buy = int(row.get("purchase_discount_pct") if row.get("purchase_discount_pct") is not None else row.get("discount_pct") or 0)
    charge = int(row.get("charge_bonus_pct") or 0)
    return {
        "id": int(row["id"]),
        "name": str(row.get("name") or ""),
        "discountPct": buy,
        "purchaseDiscountPct": buy,
        "chargeBonusPct": charge,
        "unlockSpent": int(row.get("unlock_spent") or 0),
        "color": int(row["color"]) if row.get("color") is not None else None,
        "emoji": str(row.get("emoji") or ""),
        "iconUrl": str(row.get("icon_url") or ""),
        "position": int(row.get("position") or 0),
        "manual": bool(int(row.get("manual") or 0)) if row.get("manual") is not None else False,
        "source": "manual" if row.get("manual") else "auto",
    }


_VIP_COLS = "id, name, discount_pct, purchase_discount_pct, charge_bonus_pct, color, emoji, icon_url, position, unlock_spent"


async def list_vip_tiers(db_path: Path) -> list[dict]:
    ck = (_dbk(db_path), "vip")
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    rows = await s.fetchall(db_path, f"SELECT {_VIP_COLS} FROM vip_tiers ORDER BY unlock_spent ASC, position ASC, id ASC")
    val = [_vip_payload(r) for r in (rows or [])]
    SETTINGS.set(ck, val)
    return val


def _clip_pct(value) -> int:
    return max(0, min(100, int(value or 0)))


def _clip_icon(url) -> Optional[str]:
    value = str(url or "").strip()[:240]
    if not value:
        return None
    if not value.startswith("https://"):
        raise ValueError("icon")
    return value


async def add_vip_tier(
    db_path: Path,
    name: str,
    discount_pct: int = 0,
    color: Optional[int] = None,
    emoji: Optional[str] = None,
    position: Optional[int] = None,
    unlock_spent: int = 0,
    purchase_discount_pct: Optional[int] = None,
    charge_bonus_pct: int = 0,
    icon_url: Optional[str] = None,
):
    name = str(name or "").strip()[:32]
    if not name:
        raise ValueError("name")
    buy = _clip_pct(purchase_discount_pct if purchase_discount_pct is not None else discount_pct)
    charge = _clip_pct(charge_bonus_pct)
    unlock = max(0, int(unlock_spent or 0))
    icon = _clip_icon(icon_url) or ICON_BY_NAME.get(name)
    if position is None:
        row = await s.fetchone(db_path, "SELECT COALESCE(MAX(position),0) AS p FROM vip_tiers")
        position = int((row or {}).get("p") or 0) + 10
    await s.execute(
        db_path,
        "INSERT INTO vip_tiers(name, discount_pct, purchase_discount_pct, charge_bonus_pct, color, emoji, position, unlock_spent, icon_url) VALUES(?,?,?,?,?,?,?,?,?)",
        (name, buy, buy, charge, int(color) if color is not None else None, (emoji or "").strip()[:8] or None, int(position), unlock, icon),
    )
    _bust(db_path, "vip")


async def update_vip_tier(db_path: Path, tier_id: int, **fields):
    allowed = {"name", "discount_pct", "purchase_discount_pct", "charge_bonus_pct", "color", "emoji", "position", "unlock_spent", "icon_url"}
    data = {k: v for k, v in fields.items() if k in allowed}
    if "name" in data:
        data["name"] = str(data["name"] or "").strip()[:32]
        if not data["name"]:
            raise ValueError("name")
    for key in ("discount_pct", "purchase_discount_pct", "charge_bonus_pct"):
        if key in data:
            data[key] = _clip_pct(data[key])
    if "purchase_discount_pct" in data:
        data["discount_pct"] = data["purchase_discount_pct"]
    if "unlock_spent" in data:
        data["unlock_spent"] = max(0, int(data["unlock_spent"] or 0))
    if "emoji" in data:
        data["emoji"] = (str(data["emoji"] or "").strip()[:8] or None)
    if "icon_url" in data:
        data["icon_url"] = _clip_icon(data["icon_url"]) or ICON_BY_NAME.get(data.get("name") or "")
    if "position" in data and data["position"] is not None:
        data["position"] = int(data["position"])
    if not data:
        return
    sets = ", ".join(f"{k}=?" for k in data)
    await s.execute(db_path, f"UPDATE vip_tiers SET {sets} WHERE id=?", (*data.values(), int(tier_id)))
    _bust(db_path, "vip", "uvip")


async def delete_vip_tier(db_path: Path, tier_id: int):
    await s.execute(db_path, "DELETE FROM vip_tiers WHERE id=?", (int(tier_id),))
    _bust(db_path, "vip", "uvip")


async def reorder_vip_tiers(db_path: Path, ordered_ids: list[int]):
    async def _fn(conn):
        for pos, tid in enumerate(ordered_ids):
            await conn.execute("UPDATE vip_tiers SET position=? WHERE id=?", ((pos + 1) * 10, int(tid)))
        return True
    await s.tx(db_path, _fn)
    _bust(db_path, "vip")


async def _auto_vip_row(db_path: Path, spent: int):
    return await s.fetchone(
        db_path,
        f"SELECT {_VIP_COLS} FROM vip_tiers WHERE unlock_spent > 0 AND unlock_spent <= ? ORDER BY unlock_spent DESC, position DESC, id DESC LIMIT 1",
        (max(0, int(spent)),),
    )


async def get_user_vip(db_path: Path, user_id: int) -> Optional[dict]:
    ck = (_dbk(db_path), "uvip", int(user_id))
    ok, val = SETTINGS.peek(ck)
    if ok:
        return val
    row = await s.fetchone(
        db_path,
        f"""
        SELECT t.id, t.name, t.discount_pct, t.purchase_discount_pct, t.charge_bonus_pct, t.color, t.emoji, t.icon_url, t.position, t.unlock_spent, uv.manual
        FROM user_vip uv
        JOIN vip_tiers t ON t.id = uv.tier_id
        WHERE uv.user_id=?
        """,
        (int(user_id),),
    )
    if row and int(row.get("manual") or 0):
        val = _vip_payload(row)
        SETTINGS.set(ck, val)
        return val
    spent = await total_spent(db_path, user_id)
    auto = await _auto_vip_row(db_path, spent)
    val = _vip_payload(auto) if auto else (_vip_payload(row) if row else None)
    if val:
        val["manual"] = False
        val["source"] = "auto"
    SETTINGS.set(ck, val)
    return val


async def set_user_vip(db_path: Path, user_id: int, tier_id: Optional[int], manual: bool = True):
    if not tier_id:
        await s.execute(db_path, "DELETE FROM user_vip WHERE user_id=?", (int(user_id),))
    else:
        await s.execute(
            db_path,
            "INSERT INTO user_vip(user_id, tier_id, manual) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET tier_id=excluded.tier_id, manual=excluded.manual",
            (int(user_id), int(tier_id), 1 if manual else 0),
        )
    SETTINGS.delete((_dbk(db_path), "uvip", int(user_id)))


async def refresh_auto_vip(db_path: Path, user_id: int) -> Optional[dict]:
    assigned = await s.fetchone(db_path, "SELECT tier_id, manual FROM user_vip WHERE user_id=?", (int(user_id),))
    if assigned and int(assigned.get("manual") or 0):
        SETTINGS.delete((_dbk(db_path), "uvip", int(user_id)))
        return await get_user_vip(db_path, user_id)
    spent = await total_spent(db_path, user_id)
    auto = await _auto_vip_row(db_path, spent)
    if auto:
        await set_user_vip(db_path, user_id, int(auto["id"]), manual=False)
    elif assigned:
        await s.execute(db_path, "DELETE FROM user_vip WHERE user_id=? AND manual=0", (int(user_id),))
        SETTINGS.delete((_dbk(db_path), "uvip", int(user_id)))
    return await get_user_vip(db_path, user_id)


def charge_with_bonus(amount: int, vip: Optional[dict]) -> tuple[int, int]:
    raw = max(0, int(amount))
    pct = int((vip or {}).get("chargeBonusPct") or 0)
    bonus = raw * _clip_pct(pct) // 100
    return raw + bonus, bonus


async def credit_charge(db_path: Path, user_id: int, amount: int):
    vip = await get_user_vip(db_path, user_id)
    credited, bonus = charge_with_bonus(amount, vip)
    res = await add_balance(db_path, user_id, credited)
    if isinstance(res, dict):
        res["credited"] = credited
        res["bonus"] = bonus
        res["vip"] = vip
    await refresh_auto_vip(db_path, user_id)
    return res
