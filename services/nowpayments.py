from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Optional

from config import NOWPAYMENTS_API_KEY, NOWPAYMENTS_IPN_SECRET, WEB_PUBLIC_URL
from services import http as http_pool

API_BASE = "https://api.nowpayments.io/v1"

SUCCESS_STATUSES = frozenset({"finished", "confirmed"})
FAIL_STATUSES = frozenset({"failed", "expired", "refunded"})


def configured() -> bool:
    return bool(
        (NOWPAYMENTS_API_KEY or "").strip()
        and (NOWPAYMENTS_IPN_SECRET or "").strip()
        and (WEB_PUBLIC_URL or "").strip()
    )


def ipn_callback_url() -> str:
    base = (WEB_PUBLIC_URL or "").strip().rstrip("/")
    return f"{base}/api/webhooks/nowpayments"


def _sort_object(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sort_object(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_sort_object(x) for x in obj]
    return obj


def verify_ipn_signature(payload: dict[str, Any], signature: str) -> bool:
    secret = (NOWPAYMENTS_IPN_SECRET or "").strip()
    sig = (signature or "").strip().lower()
    if not secret or not sig or not isinstance(payload, dict):
        return False
    try:
        body = json.dumps(_sort_object(payload), separators=(",", ":"), ensure_ascii=False)
        expected = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected.lower(), sig)
    except Exception:
        return False


def order_id_for(guild_id: int, pending_id: int) -> str:
    return f"g{int(guild_id)}c{int(pending_id)}"


def parse_order_id(order_id: str) -> tuple[int, int] | None:
    raw = str(order_id or "").strip()
    if raw.startswith("g") and "c" in raw:
        try:
            g_part, c_part = raw[1:].split("c", 1)
            return int(g_part), int(c_part)
        except Exception:
            return None
    return None


def payment_status(payload: dict[str, Any]) -> str:
    for key in ("payment_status", "status"):
        val = payload.get(key)
        if val is not None and str(val).strip():
            return str(val).strip().lower()
    return ""


async def create_invoice(
    *,
    price_amount: int,
    order_id: str,
    order_description: str,
    pay_currency: Optional[str] = None,
) -> dict[str, Any]:
    key = (NOWPAYMENTS_API_KEY or "").strip()
    if not key:
        return {"ok": False, "error": "NOWPAYMENTS_API_KEY missing"}
    if not configured():
        return {"ok": False, "error": "NOWPayments or WEB_PUBLIC_URL not configured"}

    body: dict[str, Any] = {
        "price_amount": float(max(1, int(price_amount))),
        "price_currency": "krw",
        "order_id": str(order_id),
        "order_description": (order_description or "Discord balance")[:300],
        "ipn_callback_url": ipn_callback_url(),
    }
    pc = (pay_currency or "").strip().lower()
    if pc:
        body["pay_currency"] = pc

    try:
        session = await http_pool.session()
        async with session.post(
            f"{API_BASE}/invoice",
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json=body,
            timeout=45,
        ) as resp:
            text = await resp.text()
            data: Any = None
            if text:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {"raw": text[:500]}
            if resp.status < 200 or resp.status >= 300:
                msg = ""
                if isinstance(data, dict):
                    msg = str(data.get("message") or data.get("error") or data.get("code") or "")
                return {"ok": False, "error": msg or f"HTTP {resp.status}", "data": data}
            if not isinstance(data, dict):
                return {"ok": False, "error": "invalid response"}
            url = str(data.get("invoice_url") or data.get("invoiceUrl") or "").strip()
            inv_id = str(data.get("id") or data.get("invoice_id") or "").strip()
            if not url:
                return {"ok": False, "error": "invoice_url missing", "data": data}
            return {"ok": True, "invoice_url": url, "invoice_id": inv_id, "data": data}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
