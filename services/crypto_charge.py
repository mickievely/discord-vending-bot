from __future__ import annotations

import time
from typing import Any, Optional

from config import DISCORD_GUILD_ID
from services import notify, nowpayments, vending_service
from services.nowpayments import FAIL_STATUSES, SUCCESS_STATUSES
async def fulfill_crypto_payment(
    guild_id: int,
    pending_id: int,
    *,
    payment_key: str,
    actor_name: str = "NOWPayments",
) -> bool:
    platform = "CRYPTO"
    pending = await vending_service.get_pending_by_id(guild_id, platform, pending_id)
    if not pending:
        return False
    status = str(pending.get("status") or "").lower()
    if status in ("done", "rejected"):
        return True
    if not await vending_service.claim_pending_charge(guild_id, platform, pending_id):
        pending = await vending_service.get_pending_by_id(guild_id, platform, pending_id)
        return str((pending or {}).get("status") or "").lower() == "done"

    key = str(payment_key or "").strip() or f"np:{guild_id}:{pending_id}"
    if not await vending_service.apply_charge_once(
        guild_id, int(pending["user_id"]), key, int(pending["amount"])
    ):
        await vending_service.release_pending_charge(guild_id, platform, pending_id)
        pending = await vending_service.get_pending_by_id(guild_id, platform, pending_id)
        return str((pending or {}).get("status") or "").lower() == "done"

    credited = await vending_service.credit_charge(guild_id, int(pending["user_id"]), int(pending["amount"]))
    if not credited or not credited.get("ok"):
        await vending_service.release_pending_charge(guild_id, platform, pending_id)
        await vending_service.forget_charge_once(
            guild_id, int(pending["user_id"]), key, int(pending["amount"])
        )
        return False

    now = int(time.time())
    await vending_service.set_charge_approval(
        guild_id,
        platform,
        pending_id,
        actor_id=None,
        actor_name=actor_name,
        approved_at=now,
    )
    await vending_service.crypto_mark_done(guild_id, pending_id)
    pending = dict(pending)
    pending["approved_by_name"] = actor_name
    pending["approved_at"] = now
    try:
        from bot import _edit_request_message

        await _edit_request_message(guild_id, platform, pending, "done")
    except Exception:
        pass
    try:
        await notify.refresh_charge_log_message(guild_id, platform, pending, "done")
    except Exception:
        pass
    return True


async def mark_crypto_failed(guild_id: int, pending_id: int) -> None:
    pending = await vending_service.get_pending_by_id(guild_id, "CRYPTO", pending_id)
    if not pending:
        return
    if str(pending.get("status") or "").lower() in ("done", "rejected"):
        return
    await vending_service.crypto_mark_rejected(guild_id, pending_id)
    try:
        await notify.refresh_charge_log_message(guild_id, "CRYPTO", dict(pending), "rejected")
    except Exception:
        pass


async def handle_ipn_payload(payload: dict[str, Any]) -> dict[str, Any]:
    order_id = str(payload.get("order_id") or payload.get("orderId") or "").strip()
    parsed = nowpayments.parse_order_id(order_id)
    if not parsed:
        return {"ok": True, "ignored": "order_id"}
    guild_id, pending_id = parsed
    if DISCORD_GUILD_ID and int(guild_id) != int(DISCORD_GUILD_ID):
        return {"ok": True, "ignored": "guild"}

    status = nowpayments.payment_status(payload)
    payment_id = str(
        payload.get("payment_id") or payload.get("invoice_id") or payload.get("id") or order_id
    )

    if status in SUCCESS_STATUSES:
        ok = await fulfill_crypto_payment(
            guild_id,
            pending_id,
            payment_key=f"np:{payment_id}",
        )
        return {"ok": True, "fulfilled": ok}
    if status in FAIL_STATUSES:
        await mark_crypto_failed(guild_id, pending_id)
        return {"ok": True, "failed": True}
    return {"ok": True, "status": status or "pending"}
