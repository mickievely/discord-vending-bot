from __future__ import annotations
from typing import Optional
from utils.paths import server_db_path
from db import server_repo

_UNSET = object()

async def bootstrap_guild(guild_id: int):
    dbp = server_db_path(guild_id)
    await server_repo.init(dbp)
    return dbp

async def panel(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.get_panel(dbp)

async def set_panel(guild_id: int, title, description, color, image_url):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_panel(dbp, title, description, color, image_url)

async def get_purchase_grant_role(guild_id: int) -> int | None:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.get_purchase_grant_role(dbp)

async def set_purchase_grant_role(guild_id: int, role_id: int | None):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_purchase_grant_role(dbp, role_id)

async def add_category(guild_id: int, name: str):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.add_category(dbp, name)

async def delete_category(guild_id: int, category_id: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.delete_category(dbp, category_id)

async def list_categories(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.list_categories(dbp)

async def add_product(guild_id: int, category_id: int, name: str, price: int, description: Optional[str], grant_role_id: int | None = None):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.add_product(dbp, category_id, name, price, description, grant_role_id=grant_role_id)

async def delete_product(guild_id: int, product_id: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.delete_product(dbp, product_id)

async def list_products(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.list_products(dbp)

async def products_in_category(guild_id: int, category_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.products_in_category(dbp, category_id)

async def product(guild_id: int, product_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.product_by_id(dbp, product_id)

async def product_with_category(guild_id: int, product_id: int):
    dbp = await bootstrap_guild(guild_id)
    row = await server_repo.product_with_category(dbp, product_id)
    return dict(row) if row else None

async def stock_count(guild_id: int, product_id: int) -> int:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.stock_count(dbp, product_id)


async def stock_counts(guild_id: int, product_ids: list[int]) -> dict[int, int]:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.stock_counts(dbp, product_ids)

async def add_stock_lines(guild_id: int, product_id: int, lines: list[str], *, actor_id: int | None = None, source: str | None = "discord"):
    dbp = await bootstrap_guild(guild_id)
    clean = [x for x in lines if str(x).strip()]
    before = await server_repo.stock_count(dbp, product_id)
    await server_repo.add_stock_lines(dbp, product_id, lines)
    after = await server_repo.stock_count(dbp, product_id)
    if clean:
        return await server_repo.add_stock_log(
            dbp,
            product_id,
            action="add",
            qty=len(clean),
            before_count=before,
            after_count=after,
            actor_id=actor_id,
            source=source,
        )
    return {"product_id": int(product_id), "action": "add", "qty": 0, "before_count": before, "after_count": after}

async def reset_stock(guild_id: int, product_id: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.reset_stock(dbp, product_id)

async def stock_lines(guild_id: int, product_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.stock_lines(dbp, product_id)

async def set_stock_lines(guild_id: int, product_id: int, lines: list[str], *, actor_id: int | None = None, source: str | None = "discord"):
    dbp = await bootstrap_guild(guild_id)
    clean = [x for x in lines if str(x).strip()]
    before = await server_repo.stock_count(dbp, product_id)
    await server_repo.set_stock_lines(dbp, product_id, lines)
    after = await server_repo.stock_count(dbp, product_id)
    return await server_repo.add_stock_log(
        dbp,
        product_id,
        action="set",
        qty=len(clean),
        before_count=before,
        after_count=after,
        actor_id=actor_id,
        source=source,
    )

async def get_balance(guild_id: int, user_id: int) -> int:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.get_balance(dbp, user_id)

async def user_stats(guild_id: int, user_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.user_stats(dbp, user_id)


async def list_vip_tiers(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.list_vip_tiers(dbp)


async def user_vip(guild_id: int, user_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.get_user_vip(dbp, user_id)


async def set_user_vip(guild_id: int, user_id: int, tier_id: int | None):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_user_vip(dbp, user_id, tier_id)


def _buy_pct(vip: dict | None) -> int:
    return int((vip or {}).get("purchaseDiscountPct") or (vip or {}).get("discountPct") or 0)


def price_label(unit_price: int, vip: dict | None, qty: int = 1) -> str:
    pct = _buy_pct(vip)
    total, saved = server_repo.sale_total(int(unit_price), qty, pct)
    if pct > 0 and saved > 0:
        name = (vip or {}).get("name") or "VIP"
        return f"{total:,}원 ({name} -{pct}%)"
    return f"{total:,}원"


def with_vip_prices(products: list, vip: dict | None) -> list:
    out = []
    pct = _buy_pct(vip)
    for p in products or []:
        item = dict(p)
        unit = int(item.get("price") or 0)
        sale, _ = server_repo.sale_total(unit, 1, pct)
        item["sale_price"] = sale
        item["price_label"] = price_label(unit, vip)
        out.append(item)
    return out

async def add_balance(guild_id: int, user_id: int, delta: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.add_balance(dbp, user_id, delta)


async def credit_charge(guild_id: int, user_id: int, amount: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.credit_charge(dbp, user_id, amount)

async def apply_charge_once(guild_id: int, user_id: int, processed_at: str, amount: int) -> bool:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.apply_charge_once(dbp, user_id, processed_at, amount)

async def purchase(guild_id: int, user_id: int, product_id: int, qty: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.purchase(dbp, user_id, product_id, qty)

async def order(guild_id: int, order_id: int):
    dbp = await bootstrap_guild(guild_id)
    row = await server_repo.order_by_id(dbp, order_id)
    return dict(row) if row else None


async def list_user_charges(guild_id: int, user_id: int, limit: int = 12):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.list_user_charges(dbp, user_id, limit)


async def add_vending_machine(guild_id: int, name: str, category_id: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.add_vending_machine(dbp, name, category_id)

async def list_vending_machines(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.list_vending_machines(dbp)

async def vending_machine(guild_id: int, vm_id: int):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.vending_machine_by_id(dbp, vm_id)

async def get_charge_settings(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    row = await server_repo.get_charge_settings(dbp)
    return row or {}

async def set_charge_manager_role(guild_id: int, role_id: int | None):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_charge_manager_role(dbp, role_id)

async def set_manual_charge_notice_enabled(guild_id: int, enabled: bool):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_manual_charge_notice_enabled(dbp, enabled)

async def set_min_charge_amount(guild_id: int, amount: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_min_charge_amount(dbp, amount)

async def set_charge_settings(
    guild_id: int,
    platform: Optional[str],
    pushbullet_token: Optional[str],
    ios_log_channel_id: Optional[int] = None,
    aos_bank_name: Optional[str] = None,
    aos_bank_account: Optional[str] = None,
    aos_bank_owner: Optional[str] = None,
    ios_bank_name: Optional[str] = None,
    ios_bank_account: Optional[str] = None,
    ios_bank_owner: Optional[str] = None,
):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_charge_settings(
        dbp,
        platform,
        pushbullet_token,
        ios_log_channel_id,
        aos_bank_name=aos_bank_name,
        aos_bank_account=aos_bank_account,
        aos_bank_owner=aos_bank_owner,
        ios_bank_name=ios_bank_name,
        ios_bank_account=ios_bank_account,
        ios_bank_owner=ios_bank_owner,
    )


async def get_log_settings(guild_id: int) -> dict:
    dbp = await bootstrap_guild(guild_id)
    row = await server_repo.get_log_settings(dbp)
    return dict(row) if row else {}

async def set_log_settings(
    guild_id: int,
    buy_channel_id: int | None,
    buy_desc_template: str | None,
    charge_channel_id: int | None,
    review_channel_id=_UNSET,
    stock_channel_id=_UNSET,
    stock_desc_template=_UNSET,
    charge_desc_template=_UNSET,
    review_desc_template=_UNSET,
    manual_charge_channel_id=_UNSET,
    **extra,
):
    dbp = await bootstrap_guild(guild_id)
    cur = await server_repo.get_log_settings(dbp)
    cur = dict(cur) if cur else {}
    fields = {
        "buy_channel_id": buy_channel_id,
        "buy_desc_template": buy_desc_template,
        "charge_channel_id": charge_channel_id,
    }
    if review_channel_id is _UNSET:
        review_channel_id = cur.get("review_channel_id")
    if stock_channel_id is _UNSET:
        stock_channel_id = cur.get("stock_channel_id")
    if stock_desc_template is _UNSET:
        stock_desc_template = cur.get("stock_desc_template")
    if charge_desc_template is _UNSET:
        charge_desc_template = cur.get("charge_desc_template")
    if review_desc_template is _UNSET:
        review_desc_template = cur.get("review_desc_template")
    if manual_charge_channel_id is _UNSET:
        manual_charge_channel_id = cur.get("manual_charge_channel_id")
    fields.update(
        {
            "review_channel_id": review_channel_id,
            "stock_channel_id": stock_channel_id,
            "stock_desc_template": stock_desc_template,
            "charge_desc_template": charge_desc_template,
            "review_desc_template": review_desc_template,
            "manual_charge_channel_id": manual_charge_channel_id,
        }
    )
    for key, value in extra.items():
        if value is not _UNSET:
            fields[key] = value
    await server_repo.set_log_settings(dbp, **fields)

async def list_buyer_ids(guild_id: int) -> list[int]:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.list_buyer_ids(dbp)

async def list_user_purchases(guild_id: int, user_id: int, limit: int = 30):
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.list_user_purchases(dbp, user_id, limit)

async def set_charge_approval(
    guild_id: int,
    platform: str,
    pid: int,
    *,
    actor_id: int | None,
    actor_name: str | None,
    approved_at: int | None = None,
):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_charge_approval(
        dbp, platform, pid, actor_id=actor_id, actor_name=actor_name, approved_at=approved_at
    )

async def total_spent(guild_id: int, user_id: int) -> int:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.total_spent(dbp, user_id)


async def ios_create_pending(guild_id: int, user_id: int, amount: int, depositor_name: str) -> int:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.ios_create_pending(dbp, user_id, amount, depositor_name)


async def aos_create_pending(guild_id: int, user_id: int, amount: int, depositor_name: str) -> int:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.aos_create_pending(dbp, user_id, amount, depositor_name)


async def set_crypto_charge_settings(guild_id: int, enabled: bool, pay_currency: str):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_crypto_charge_settings(dbp, enabled, pay_currency)


async def crypto_create_pending(guild_id: int, user_id: int, amount: int, label: str) -> int:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.crypto_create_pending(dbp, user_id, amount, label)


async def crypto_attach_invoice(
    guild_id: int,
    pid: int,
    *,
    invoice_id: str,
    invoice_url: str,
    order_id: str,
    pay_currency: str,
) -> None:
    dbp = await bootstrap_guild(guild_id)
    await server_repo.crypto_attach_invoice(
        dbp,
        pid,
        invoice_id=invoice_id,
        invoice_url=invoice_url,
        order_id=order_id,
        pay_currency=pay_currency,
    )


async def crypto_mark_done(guild_id: int, pid: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.crypto_mark_done(dbp, pid)


async def crypto_mark_rejected(guild_id: int, pid: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.crypto_mark_rejected(dbp, pid)


async def set_pending_request_message(guild_id: int, platform: str, pid: int, channel_id: int, message_id: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_pending_request_message(dbp, platform, pid, channel_id, message_id)

async def get_pending_by_id(guild_id: int, platform: str, pid: int):
    dbp = await bootstrap_guild(guild_id)
    row = await server_repo.get_pending_by_id(dbp, platform, pid)
    return dict(row) if row else None

async def aos_find_match_pending(guild_id: int, amount: int, depositor_name: str | None):
    dbp = await bootstrap_guild(guild_id)
    row = await server_repo.aos_find_match_pending(dbp, amount, depositor_name)
    return dict(row) if row else None

async def aos_mark_done(guild_id: int, pid: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.aos_mark_done(dbp, pid)

async def claim_pending_charge(guild_id: int, platform: str, pid: int) -> bool:
    dbp = await bootstrap_guild(guild_id)
    return await server_repo.claim_pending_charge(dbp, platform, int(pid))

async def release_pending_charge(guild_id: int, platform: str, pid: int) -> None:
    dbp = await bootstrap_guild(guild_id)
    await server_repo.release_pending_charge(dbp, platform, int(pid))

async def forget_charge_once(guild_id: int, user_id: int, processed_at: str, amount: int) -> None:
    dbp = await bootstrap_guild(guild_id)
    await server_repo.forget_charge_once(dbp, int(user_id), processed_at, int(amount))

async def aos_mark_rejected(guild_id: int, pid: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.aos_mark_rejected(dbp, pid)


async def ios_mark_rejected(guild_id: int, pid: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.ios_mark_rejected(dbp, pid)

async def ios_process_webhook(guild_id: int, message_id: int, amount: int, depositor_name: Optional[str]):
    dbp = await bootstrap_guild(guild_id)
    if await server_repo.ios_is_deduped(dbp, message_id):
        return None
    pending = await server_repo.ios_find_match_pending(dbp, amount, depositor_name)
    if not pending:
        return None
    ok = await server_repo.credit_charge(dbp, int(pending["user_id"]), int(pending["amount"]))
    if not ok or not ok.get("ok"):
        return None
    await server_repo.apply_charge_once(dbp, int(pending["user_id"]), str(message_id), int(pending["amount"]))
    await server_repo.ios_mark_done(dbp, int(pending["id"]), message_id)
    return dict(pending)


async def set_aos_charge_settings(
    guild_id: int,
    bank_name: str,
    bank_account: str,
    bank_owner: str,
    pushbullet_token: Optional[str],
):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_aos_charge_settings(dbp, bank_name, bank_account, bank_owner, pushbullet_token)

async def set_ios_charge_settings(
    guild_id: int,
    bank_name: str,
    bank_account: str,
    bank_owner: str,
    ios_log_channel_id: int,
):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.set_ios_charge_settings(dbp, bank_name, bank_account, bank_owner, ios_log_channel_id)

async def disable_aos_charge(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.disable_aos_charge(dbp)

async def disable_ios_charge(guild_id: int):
    dbp = await bootstrap_guild(guild_id)
    await server_repo.disable_ios_charge(dbp)
