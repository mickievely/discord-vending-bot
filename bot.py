from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time

import aiohttp
import discord
from aiohttp import web as aiohttp_web
from discord.ext import commands

from config import DISCORD_TOKEN, WEB_PANEL_AUTO_START
from db import server_repo
from services import notify, vending_service
from ui.admin_modals import (
    AdminCategoryAddModal,
    AdminPanelModal,
    AdminProductAddModal,
    AdminStockEditModal,
    AdminVendingMachineAddModal,
)
from ui.admin_views import select_view
from ui.embeds import error_embed, ok_embed, product_embed, purchase_embed
from ui.modals import QtyModal
from ui.root_modals import RootServerIdModal
from ui.v2_layouts import VendingPanelLayout, vending_machine_message
from ui.views import buy_view, product_view, purchase_dual_select_view

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

_WEB_PANEL_RUNNER: aiohttp_web.AppRunner | None = None
_WEB_PANEL_SITE: aiohttp_web.TCPSite | None = None


async def _vip_of(interaction: discord.Interaction):
    if not interaction.guild:
        return None
    try:
        return await vending_service.user_vip(interaction.guild.id, interaction.user.id)
    except Exception:
        return None


async def _vip_prods(interaction: discord.Interaction, products):
    return vending_service.with_vip_prices(products, await _vip_of(interaction))


def _info_uid(interaction: discord.Interaction, raw: str | None = None) -> int | None:
    uid = int(interaction.user.id)
    if raw and str(raw).isdigit():
        want = int(raw)
        if want == uid or _is_admin(interaction):
            return want
        return None
    return uid


async def _my_info_view(guild_id: int, user: discord.abc.User):
    from ui.v2_layouts import my_info_layout
    st = await vending_service.user_stats(guild_id, user.id)
    spent = int(st.get("spent") or 0)
    tiers = await vending_service.list_vip_tiers(guild_id)
    vip = st.get("vip")
    return my_info_layout(
        mention=getattr(user, "mention", str(user.id)),
        balance=int(st.get("balance") or 0),
        spent=int(spent),
        orders=int(st.get("orders") or 0),
        vip=vip,
        tiers=tiers,
        user_id=int(user.id),
        accent_color=int(vip["color"]) if vip and vip.get("color") is not None else None,
    )


async def _my_orders_view(guild_id: int, user_id: int):
    from services.notify import kst_from_ts
    from ui.v2_layouts import my_info_history_layout
    rows = await vending_service.list_user_purchases(guild_id, user_id, 12)
    lines = []
    for r in rows or []:
        lines.append(
            f"**{r.get('product_name') or '상품'}** · {int(r.get('qty') or 0)}개 · {int(r.get('total') or 0):,}원\n- {kst_from_ts(r.get('created_at'))}"
        )
    return my_info_history_layout(title="구매 내역", lines=lines, user_id=int(user_id))


async def _my_charges_view(guild_id: int, user_id: int):
    from services.notify import kst_from_ts
    from ui.v2_layouts import my_info_history_layout
    labels = {"pending": "대기", "done": "완료", "approved": "완료", "rejected": "거절"}
    rows = await vending_service.list_user_charges(guild_id, user_id, 12)
    lines = []
    for r in rows or []:
        st = labels.get(str(r.get("status") or ""), str(r.get("status") or "-"))
        who = (r.get("depositor_name") or "").strip()
        extra = f" · {who}" if who else ""
        lines.append(
            f"**{int(r.get('amount') or 0):,}원** · {r.get('platform') or '-'}\n- {st}{extra} · {kst_from_ts(r.get('created_at'))}"
        )
    return my_info_history_layout(title="충전 내역", lines=lines, user_id=int(user_id))


async def _reply_info(interaction: discord.Interaction, view, *, edit: bool):
    if edit and not interaction.response.is_done():
        return await _edit(interaction, view=view)
    if interaction.response.is_done():
        return await interaction.followup.send(view=view, ephemeral=True)
    return await _reply(interaction, view=view, ephemeral=True)


async def _send_embed_channel(
    *,
    channel: discord.abc.Messageable | None,
    embed: discord.Embed,
    view: discord.ui.View | None = None,
):
    if not channel:
        return None
    try:
        return await channel.send(embed=embed, view=view)
    except Exception:
        return None


async def _start_web_panel_with_bot():
    global _WEB_PANEL_RUNNER, _WEB_PANEL_SITE
    if _WEB_PANEL_RUNNER is not None:
        return
    try:
        import web_panel
        web_panel.set_discord_bot(bot)

        if not WEB_PANEL_AUTO_START:
            print("web panel auto-start disabled")
            return

        runner = aiohttp_web.AppRunner(web_panel.app())
        await runner.setup()
        site = aiohttp_web.TCPSite(runner, web_panel.WEB_PANEL_HOST, web_panel.WEB_PANEL_PORT)
        try:
            await site.start()
        except OSError as e:
            await runner.cleanup()
            print(f"web panel already running or port unavailable: {web_panel.WEB_PANEL_HOST}:{web_panel.WEB_PANEL_PORT} ({e})")
            return

        _WEB_PANEL_RUNNER = runner
        _WEB_PANEL_SITE = site
        print(f"web panel: http://{web_panel.WEB_PANEL_HOST}:{web_panel.WEB_PANEL_PORT}")
    except Exception as e:
        print(f"web panel start failed: {type(e).__name__}: {e}")

_AMOUNT_PATTERNS = [
    re.compile(r"(?:금액|입금|송금|입금액)\s*[:：]?\s*([0-9][0-9,]*)\s*원"),
    re.compile(r"([0-9][0-9,]*)\s*원"),
    re.compile(r"₩\s*([0-9][0-9,]*)"),
]

_NAME_PATTERNS = [
    re.compile(r"(?:입금자명|입금자|보낸사람|보낸 분|보낸분|보낸이|송금인|송금자)\s*[:：]?\s*([가-힣A-Za-z0-9_\-\. ]{2,30})"),
]


async def _resolve_log_channel(guild: discord.Guild | None, channel_id: int | None):
    return await notify.resolve_channel(guild, channel_id)


async def _resolve_charge_log_channel(guild: discord.Guild | None):
    if not guild:
        return None
    try:
        logs = await vending_service.get_log_settings(guild.id)
        logs = dict(logs) if logs else {}
    except Exception:
        logs = {}
    cid = logs.get('charge_channel_id') or logs.get('buy_channel_id')
    if cid:
        ch = await _resolve_log_channel(guild, int(cid))
        if ch:
            return ch
    try:
        cfg = await vending_service.get_charge_settings(guild.id)
        cfg = dict(cfg) if cfg else {}
    except Exception:
        cfg = {}
    cid = cfg.get('ios_log_channel_id')
    if cid:
        ch = await _resolve_log_channel(guild, int(cid))
        if ch:
            return ch
    return None

def _normalize_depositor_name(value: str | None) -> str:
    s = str(value or "").strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("님", "")
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
    return s.lower()

def _parse_bank_amount_depositor(title: str, body: str):
    txt = f"{title}\n{body}"
    amt = None
    for p in _AMOUNT_PATTERNS:
        m = p.search(txt)
        if m:
            try:
                amt = int(m.group(1).replace(",", ""))
                break
            except Exception:
                amt = None
    name = None
    for p in _NAME_PATTERNS:
        m = p.search(txt)
        if m:
            name = m.group(1).strip()
            break
    if not name:
        arrow = re.search(r"([가-힣A-Za-z0-9 ]{2,30})\s*(?:→|->)", body or txt)
        if arrow:
            name = arrow.group(1).strip()
    if name:
        name = re.sub(r"\s+", "", name)
    return amt, name

async def _try_apply_aos_charge_from_push(guild_id: int, amount: int, depositor: str | None):
    pending = await vending_service.aos_find_match_pending(guild_id, int(amount), depositor or None)
    if not pending:
        return False
    pid = int(pending["id"])
    if not await vending_service.claim_pending_charge(guild_id, "AOS", pid):
        return False
    dbp = await vending_service.bootstrap_guild(guild_id)
    ok = await server_repo.credit_charge(dbp, int(pending["user_id"]), int(pending["amount"]))
    if not ok or not ok.get("ok"):
        await vending_service.release_pending_charge(guild_id, "AOS", pid)
        return False
    await vending_service.aos_mark_done(guild_id, pid)
    await _edit_request_message(guild_id, "AOS", dict(pending), "done")
    try:
        g = bot.get_guild(int(guild_id))
        charge_ch = await _resolve_charge_log_channel(g)
        embed = await _build_charge_log_embed(
            guild_id,
            "AOS",
            user_id=int(pending["user_id"]),
            amount=int(pending["amount"]),
            depositor=str(pending.get("depositor_name") or ""),
            pid=int(pending["id"]),
            status="done",
        )
        if charge_ch:
            await _send_embed_channel(channel=charge_ch, embed=embed)
    except Exception:
        pass
    return True

def _fmt_template(
    tmpl: str,
    *,
    user: discord.abc.User,
    category: str = "",
    product: str = "",
    qty: int | None = None,
    total: int | None = None,
    amount: int | None = None,
    content: str = "",
):
    out = str(tmpl or "")
    total_value = "" if total is None else f"{int(total):,}"
    amount_value = "" if amount is None else f"{int(amount):,}"
    qty_value = "" if qty is None else str(int(qty))
    replacements = {
        "{유저}": user.mention,
        "{사용자}": user.mention,
        "{user}": user.mention,
        "{username}": str(user),
        "{카테고리}": str(category),
        "{카테고리이름}": str(category),
        "{category}": str(category),
        "{categoryName}": str(category),
        "{제품}": str(product),
        "{상품}": str(product),
        "{product}": str(product),
        "{productName}": str(product),
        "{수량}": qty_value,
        "{qty}": qty_value,
        "{quantity}": qty_value,
        "{총액}": total_value,
        "{total}": total_value,
        "{금액}": amount_value or total_value,
        "{amount}": amount_value or total_value,
        "{내용}": str(content),
        "{content}": str(content),
    }
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out

def _stock_action_label(action: str) -> str:
    return "입고" if str(action or "").lower() == "add" else "설정"

def _fmt_stock_template(
    tmpl: str,
    *,
    user: discord.abc.User,
    category: str,
    product: str,
    qty: int,
    before_count: int,
    after_count: int,
    action: str,
) -> str:
    label = _stock_action_label(action)
    out = str(tmpl or "")
    replacements = {
        "{유저}": user.mention,
        "{user}": user.mention,
        "{카테고리}": str(category),
        "{카테고리이름}": str(category),
        "{category}": str(category),
        "{categoryName}": str(category),
        "{제품}": str(product),
        "{product}": str(product),
        "{수량}": str(int(qty)),
        "{qty}": str(int(qty)),
        "{이전재고}": str(int(before_count)),
        "{before}": str(int(before_count)),
        "{현재재고}": str(int(after_count)),
        "{after}": str(int(after_count)),
        "{방식}": label,
        "{action}": label,
    }
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out

def _schedule_stock_log(interaction: discord.Interaction, product_id: int, info: dict | None):
    if not interaction.guild:
        return
    try:
        details = dict(info or {})
        details.setdefault("product_id", int(product_id))
        notify.schedule_stock_notify(
            interaction.guild.id,
            details,
            actor_mention=interaction.user.mention,
            actor_name=str(interaction.user),
            actor_id=interaction.user.id,
        )
    except Exception:
        return

def charge_log_view(platform: str, pid: int):
    view = discord.ui.View(timeout=300)
    view.add_item(discord.ui.Button(label="승인", style=discord.ButtonStyle.success, custom_id=f"c:appr:{platform}:{pid}"))
    view.add_item(discord.ui.Button(label="거절", style=discord.ButtonStyle.danger, custom_id=f"c:rej:{platform}:{pid}"))
    return view


def _charge_account_label(platform: str) -> str:
    return "계좌 2" if str(platform).upper() == "IOS" else "계좌 1"


def _enabled_charge_platforms(cfg: dict) -> list[str]:
    platforms: list[str] = []
    aos_ready = (
        int(cfg.get("aos_enabled") or 0) == 1
        and all(str(cfg.get(k) or "").strip() for k in ("aos_bank_name", "aos_bank_account", "aos_bank_owner", "pushbullet_token"))
    )
    ios_ready = (
        int(cfg.get("ios_enabled") or 0) == 1
        and all(str(cfg.get(k) or "").strip() for k in ("ios_bank_name", "ios_bank_account", "ios_bank_owner"))
        and int(cfg.get("ios_log_channel_id") or 0) > 0
    )
    if aos_ready:
        platforms.append("AOS")
    if ios_ready:
        platforms.append("IOS")
    return platforms


def _charge_account_options(platforms=("AOS", "IOS"), cfg: dict | None = None):
    cfg = cfg or {}
    opts = []
    for platform in platforms:
        p = str(platform).lower()
        bank = (cfg.get(f"{p}_bank_name") or "").strip()
        owner = (cfg.get(f"{p}_bank_owner") or "").strip()
        desc = " / ".join(x for x in (bank, owner) if x) or "충전 계좌"
        opts.append(discord.SelectOption(label=_charge_account_label(platform), value=str(platform).upper(), description=desc[:100]))
    return opts


def _charge_status_meta(status: str):
    s = str(status or "pending").lower()
    if s == "done":
        return "✅ 충전 완료", 0x57F287, "충전이 정상적으로 완료되었습니다."
    if s == "rejected":
        return "❌ 충전 거절", 0xED4245, "관리자가 충전 요청을 거절했습니다."
    if s == "expired":
        return "⌛ 충전 요청 만료", 0xFEE75C, "유효시간이 지나 자동으로 만료되었습니다."
    return "💳 충전 요청", 0x5865F2, "아래 계좌로 입금 후 자동 확인을 기다려주세요."


async def _build_charge_notice_embed(guild_id: int, platform: str, *, amount: int, depositor: str, status: str):
    cfg = await vending_service.get_charge_settings(int(guild_id))
    cfg = dict(cfg) if cfg else {}
    p = str(platform).lower()
    bn = (cfg.get(f"{p}_bank_name") or "").strip()
    ba = (cfg.get(f"{p}_bank_account") or "").strip()
    bo = (cfg.get(f"{p}_bank_owner") or "").strip()
    title, color, desc = _charge_status_meta(status)
    emb = discord.Embed(title=title, description=desc, color=color)
    emb.add_field(name="은행", value=bn or "미설정", inline=True)
    emb.add_field(name="계좌번호", value=f"`{ba}`" if ba else "미설정", inline=True)
    emb.add_field(name="예금주", value=bo or "미설정", inline=True)
    emb.add_field(name="입금자명", value=f"`{(depositor or '').strip() or '-'}`", inline=True)
    emb.add_field(name="금액", value=f"`{int(amount):,}원`", inline=True)
    emb.add_field(name="계좌", value=f"`{_charge_account_label(platform)}`", inline=True)
    if str(status).lower() == "pending":
        emb.set_footer(text="입금자명/금액이 일치해야 자동 승인됩니다 • 유효시간 5분")
    return emb


async def _build_charge_log_embed(
    guild_id: int,
    platform: str,
    *,
    user_id: int,
    amount: int,
    depositor: str,
    pid: int,
    status: str,
    staff_id: int | None = None,
    staff_name: str | None = None,
    staff_at: int | None = None,
):
    from services.notify import kst_from_ts
    title, color, desc = _charge_status_meta(status)
    emb = discord.Embed(title=title, description=desc, color=color)
    mention = f"<@{int(user_id)}>" if int(user_id or 0) else "-"
    emb.add_field(name="유저", value=mention, inline=True)
    emb.add_field(name="입금자명", value=f"`{(depositor or '').strip() or '-'}`", inline=True)
    emb.add_field(name="금액", value=f"`{int(amount):,}원`", inline=True)
    emb.add_field(name="계좌", value=f"`{_charge_account_label(platform)}`", inline=True)
    emb.add_field(name="상태", value=("`대기중(5분)`" if str(status).lower() == "pending" else f"`{title.replace('✅ ','').replace('❌ ','').replace('⌛ ','')}`"), inline=True)
    emb.add_field(name="요청번호", value=f"`{int(pid)}`", inline=True)
    if staff_id or staff_name:
        who = staff_name or "스태프"
        mention_staff = f"<@{int(staff_id)}>" if staff_id else who
        emb.add_field(name="처리 스태프", value=f"{mention_staff}\n`{who}` · ID `{staff_id or '-'}`", inline=False)
        emb.add_field(name="처리 시각", value=f"`{kst_from_ts(staff_at)}`", inline=True)
    emb.timestamp = discord.utils.utcnow()
    return emb

class _PBWatcher:
    def __init__(self, guild_id: int, expire_at: int, pid: int | None):
        self.guild_id = guild_id
        self.expire_at = expire_at
        self.pid = pid

class PushbulletWSManager:
    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._watchers: dict[str, list[_PBWatcher]] = {}
        self._seen_idens: set[str] = set()

    def _mask(self, token: str) -> str:
        return token[:6] + "..." + token[-4:] if len(token) > 12 else token

    def watch(self, token: str, guild_id: int, pid: int | None = None, seconds: int = 300):
        token = str(token).strip()
        if not token:
            return
        now = int(time.time())
        expire_at = now + int(seconds)
        pid = int(pid) if pid is not None else None
        rows = [w for w in self._watchers.get(token, []) if w.expire_at > now]
        same = [w for w in rows if int(w.guild_id) == int(guild_id)]
        for w in same:
            w.expire_at = max(int(w.expire_at), expire_at)
        if not any(int(w.guild_id) == int(guild_id) and w.pid == pid for w in rows):
            rows.append(_PBWatcher(guild_id, expire_at, pid))
        self._watchers[token] = rows
        mask = self._mask(token)
        if same:
            print(f"[PB] watch_extend token={mask} guild={int(guild_id)} pid={pid} ttl={int(seconds)}s watchers={len(rows)}")
        else:
            print(f"[PB] watch token={mask} guild={int(guild_id)} pid={pid} ttl={int(seconds)}s watchers={len(rows)}")
        if token not in self._tasks or self._tasks[token].done():
            self._tasks[token] = asyncio.create_task(self._run(token))

    def unwatch(self, token: str, guild_id: int, pid: int | None = None):
        token = str(token).strip()
        if not token:
            return
        rows = list(self._watchers.get(token, []))
        kept = []
        removed = 0
        for w in rows:
            if int(w.guild_id) != int(guild_id):
                kept.append(w)
                continue
            if pid is not None and w.pid != int(pid):
                kept.append(w)
                continue
            removed += 1
        self._watchers[token] = kept
        print(f"[PB] unwatch token={self._mask(token)} guild={int(guild_id)} pid={int(pid) if pid is not None else None} removed={removed} watchers={len(kept)}")

    async def _run(self, token: str):
        url = f"wss://stream.pushbullet.com/websocket/{token}"
        mask = self._mask(token)
        while True:
            now = int(time.time())
            ws_watchers = [w for w in self._watchers.get(token, []) if w.expire_at > now]
            self._watchers[token] = ws_watchers
            if not ws_watchers:
                print(f"[PB] ws_close token={mask} reason=no_watchers")
                return
            try:
                async with aiohttp.ClientSession() as session:
                    print(f"[PB] ws_connect token={mask} watchers={len(ws_watchers)}")
                    async with session.ws_connect(url, heartbeat=30) as ws:
                        print(f"[PB] ws_open token={mask}")
                        while True:
                            now = int(time.time())
                            ws_watchers = [w for w in self._watchers.get(token, []) if w.expire_at > now]
                            self._watchers[token] = ws_watchers
                            if not ws_watchers:
                                print(f"[PB] ws_close token={mask} reason=watchers_expired")
                                await ws.close()
                                return
                            try:
                                msg = await ws.receive(timeout=5)
                            except asyncio.TimeoutError:
                                continue
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_push(token, msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except Exception as e:
                print(f"[PB] ws_error token={mask} err={e}")
                await asyncio.sleep(1)

    async def _handle_push(self, token: str, data: str):
        mask = self._mask(token)
        print(f"[PB] raw token={mask} data={data}")
        try:
            j = json.loads(data)
        except Exception as e:
            print(f"[PB] raw_json_fail token={mask} err={e}")
            return
        print(f"[PB] event token={mask} type={j.get('type')} payload={j}")
        if j.get("type") != "push":
            return
        push = j.get("push") or {}
        iden = str(push.get("iden") or "").strip()
        if not iden:
            fallback = [
                "mirror",
                str(push.get("notification_id") or "").strip(),
                str(push.get("source_device_iden") or "").strip(),
                str(push.get("package_name") or "").strip(),
                str(push.get("title") or "").strip(),
                str(push.get("body") or "").strip(),
            ]
            iden = ":".join(x for x in fallback if x)
            print(f"[PB] push_no_iden token={mask} fallback_iden={iden!r} push={push}")
        if not iden:
            return
        if iden in self._seen_idens:
            print(f"[PB] push_dup token={mask} iden={iden}")
            return
        self._seen_idens.add(iden)
        body = str(push.get("body") or "")
        title = str(push.get("title") or "")
        sender = push.get("sender_email") or push.get("sender_name")
        source = push.get("source_device_iden")
        target = push.get("target_device_iden")
        print(f"[PB] push iden={iden} token={mask} title={title!r} body={body!r} sender={sender!r} source={source!r} target={target!r}")
        text = (title + "\n" + body).strip()
        print(f"[PB] parsed_text token={mask} text={text!r}")
        try:
            amount, depositor = _parse_bank_amount_depositor(title, body)
        except Exception as e:
            print(f"[PB] parser_exception token={mask} err={e} title={title!r} body={body!r}")
            return
        print(f"[PB] parser_result token={mask} amount={amount} depositor={depositor!r}")
        if not amount:
            print(f"[PB] parse_fail token={mask} text={text!r}")
            return
        depositor = re.sub(r"\s+", "", str(depositor or "")).strip() or None
        print(f"[PB] normalized token={mask} amount={amount} depositor={depositor!r}")
        now = int(time.time())
        watchers = [w for w in self._watchers.get(token, []) if w.expire_at > now]
        self._watchers[token] = watchers
        print(f"[PB] active_watchers token={mask} watchers={[{'guild_id': int(w.guild_id), 'pid': w.pid, 'expire_at': int(w.expire_at)} for w in watchers]}")
        if not watchers:
            return
        matches = []
        for w in watchers:
            pending = None
            try:
                if w.pid is not None:
                    p = await vending_service.get_pending_by_id(w.guild_id, "AOS", int(w.pid))
                    print(f"[PB] watcher_check token={mask} guild={int(w.guild_id)} pid={w.pid} direct_pending={p}")
                    if p and str(p.get("status")) == "pending" and int(p.get("amount") or 0) == int(amount):
                        if depositor:
                            a = _normalize_depositor_name(str(p.get("depositor_name") or ""))
                            b = _normalize_depositor_name(depositor)
                            if a and b and a != b and a not in b and b not in a:
                                p = None
                        if p:
                            pending = p
                if not pending:
                    pending = await vending_service.aos_find_match_pending(w.guild_id, amount, depositor or None)
                    print(f"[PB] watcher_lookup token={mask} guild={int(w.guild_id)} pid={w.pid} pending={pending}")
            except Exception as e:
                print(f"[PB] watcher_error token={mask} guild={int(w.guild_id)} pid={w.pid} err={e}")
                pending = None
            if pending:
                matches.append((w, pending))
        if len(matches) != 1:
            print(f"[PB] match_skip token={mask} amount={amount} depositor={depositor!r} matches={len(matches)}")
            return
        watcher, pending = matches[0]
        print(f"[PB] match_ok token={mask} guild={int(watcher.guild_id)} pending_id={int(pending['id'])} user_id={int(pending['user_id'])} amount={int(pending['amount'])} depositor={pending.get('depositor_name')!r}")
        ok = await _auto_approve_charge(int(watcher.guild_id), "AOS", int(pending["id"]), processed_key=f"pb:{iden}")
        if ok:
            self.unwatch(token, int(watcher.guild_id), int(pending["id"]))

PB_MANAGER = PushbulletWSManager()

EPHEMERAL_CHARGE_MSGS: dict[str, discord.Message] = {}


def _pending_key(guild_id: int, platform: str, pid: int) -> str:
    return f"{int(guild_id)}:{str(platform).upper()}:{int(pid)}"


async def _charge_ephemeral_embed(guild_id: int, platform: str, *, amount: int, depositor: str, status: str):
    return await _build_charge_notice_embed(guild_id, platform, amount=amount, depositor=depositor, status=status)



def _is_admin(i: discord.Interaction) -> bool:
    if not i.guild or not i.user:
        return False
    if isinstance(i.user, discord.Member):
        return i.user.guild_permissions.administrator
    return False


async def _grant_purchase_role(interaction: discord.Interaction, res: dict) -> str | None:
    role_id = 0
    if interaction.guild:
        try:
            role_id = int(await vending_service.get_purchase_grant_role(interaction.guild.id) or 0)
        except Exception:
            role_id = 0
    if not role_id or not interaction.guild:
        return None

    role = interaction.guild.get_role(role_id)
    if not role:
        return "구매 역할을 찾을 수 없어 지급하지 못했습니다."

    member = interaction.user if isinstance(interaction.user, discord.Member) else None
    if member is None:
        try:
            member = await interaction.guild.fetch_member(int(interaction.user.id))
        except Exception:
            member = None
    if member is None:
        return "구매자 정보를 찾을 수 없어 역할을 지급하지 못했습니다."

    if any(int(r.id) == role_id for r in getattr(member, "roles", []) or []):
        return None

    try:
        await member.add_roles(role, reason=f"상품 구매 자동 지급: {res.get('product_name') or ''}".strip())
        return None
    except discord.Forbidden:
        return "봇 권한 또는 역할 순서 때문에 구매 역할을 지급하지 못했습니다."
    except Exception:
        return "구매 역할을 지급하는 중 오류가 발생했습니다."


async def _can_manage_charge(interaction: discord.Interaction) -> bool:
    return _is_admin(interaction)


def _get_modal_value(interaction: discord.Interaction, field_id: str) -> str:
    for row in (interaction.data or {}).get("components", []):
        for c in row.get("components", []):
            if c.get("custom_id") == field_id:
                return str(c.get("value", ""))
    return ""


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.core")
    try:
        notify.set_bot(bot)
    except Exception as e:
        print(f"notify init failed: {type(e).__name__}: {e}")
    await _start_web_panel_with_bot()
    asyncio.create_task(_sync_commands())


async def _sync_commands():
    try:
        synced = await bot.tree.sync()
        print(f"commands synced: {len(synced)}")
    except discord.HTTPException as e:
        print(f"command sync skipped: {e.status}")
    except Exception as e:
        print(f"command sync failed: {type(e).__name__}: {e}")


def _component_meta(components):
    ids: set[str] = set()
    labels: set[str] = set()

    def walk(node):
        if node is None:
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        cid = getattr(node, "custom_id", None)
        if cid:
            ids.add(str(cid))
        label = getattr(node, "label", None)
        if label:
            labels.add(str(label))
        walk(getattr(node, "children", None))
        walk(getattr(node, "components", None))

    walk(components)
    return ids, labels


def _message_is_components_v2(msg: discord.Message) -> bool:
    flags = getattr(msg, "flags", None)
    if flags is None:
        return False
    if getattr(flags, "is_components_v2", False):
        return True
    try:
        return bool(int(flags.value) & (1 << 15))
    except Exception:
        return False


async def _replace_panel_message(msg: discord.Message, view_factory):
    try:
        if _message_is_components_v2(msg):
            await msg.edit(view=view_factory())
            return
        kwargs = {"view": view_factory()}
        if msg.content or msg.embeds or msg.attachments:
            kwargs["content"] = None
            kwargs["embed"] = None
            kwargs["attachments"] = []
        await msg.edit(**kwargs)
        return
    except Exception as e:
        detail = getattr(e, "text", "") or e
        print(f"panel edit failed {msg.channel.id}/{msg.id}: {type(e).__name__}: {detail}")
    try:
        await msg.channel.send(view=view_factory())
        await msg.delete()
    except Exception as e:
        print(f"panel replace failed {msg.channel.id}/{msg.id}: {type(e).__name__}: {e}")


async def _refresh_posted_panels():
    await asyncio.sleep(3)
    from ui.v2_layouts import vending_machine_message

    shop_ids = {"k:buy", "k:products", "k:charge", "k:info"}
    shop_labels = {"구매", "제품", "충전", "정보"}
    updated = 0
    for guild in list(bot.guilds):
        try:
            panel = dict(await vending_service.panel(guild.id) or {})
        except Exception:
            panel = {}
        title = (panel.get("title") or "").strip()
        desc = (panel.get("description") or "").strip()
        image_url = panel.get("image_url") or None
        color = int(panel.get("color") or 0x5865F2)

        def shop_view(title=title, desc=desc, image_url=image_url, color=color):
            return vending_machine_message(title=title, description=desc, image_url=image_url, color=color)

        me = guild.me
        if me is None:
            continue
        for channel in list(guild.text_channels):
            perms = channel.permissions_for(me)
            if not perms.read_message_history:
                continue
            try:
                async for msg in channel.history(limit=80):
                    if not bot.user or msg.author.id != bot.user.id:
                        continue
                    ids, labels = _component_meta(msg.components)
                    if shop_ids & ids or shop_labels <= labels:
                        await _replace_panel_message(msg, shop_view)
                        updated += 1
                        await asyncio.sleep(0.4)
                        continue
                    embed_title = (msg.embeds[0].title or "").strip() if msg.embeds else ""
                    if title and embed_title == title and not ids:
                        await _replace_panel_message(msg, shop_view)
                        updated += 1
                        await asyncio.sleep(0.4)
            except discord.Forbidden:
                continue
            except Exception as e:
                print(f"panel scan failed {guild.id}/{getattr(channel, 'id', 0)}: {type(e).__name__}: {e}")
    print(f"posted panels refreshed: {updated}")


@bot.event
async def on_ready():
    print(f"ready: {bot.user}")
    if not getattr(bot, "_panel_refresh_started", False):
        bot._panel_refresh_started = True
        asyncio.create_task(_refresh_posted_panels())


def _expired_interaction(err: Exception) -> bool:
    code = getattr(err, "code", None)
    return code in (10062, 40060, 10003) or "Unknown interaction" in str(err) or "Unknown Channel" in str(err) or "already been acknowledged" in str(err).lower()


def _fast_component(cid: str) -> bool:
    if cid.startswith("i:"):
        return True
    return cid in {"k:buy", "k:products", "k:info", "k:plist_cat", "k:buy_cat", "v:prod"}


def _needs_modal_response(cid: str) -> bool:
    if cid in {
        "k:buy_prod", "k:charge", "k:charge_pick", "a:charge_platform",
        "a:prod_add_cat", "a:vm_add_cat", "r:menu", "v:admin",
    }:
        return True
    return cid.startswith(("v:buy:", "rv:write:", "a:stock_method:", "a:log_pick:"))


async def _ack(interaction: discord.Interaction, *, ephemeral: bool = True, thinking: bool = True) -> bool:
    if interaction.response.is_done():
        return True
    try:
        await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException as e:
        return _expired_interaction(e) and interaction.response.is_done()


async def _reply(interaction: discord.Interaction, **kwargs):
    ephemeral = kwargs.pop("ephemeral", True)
    try:
        if not interaction.response.is_done():
            return await interaction.response.send_message(ephemeral=ephemeral, **kwargs)
        try:
            return await interaction.edit_original_response(**kwargs)
        except discord.HTTPException:
            return await interaction.followup.send(ephemeral=ephemeral, **kwargs)
    except discord.NotFound:
        return
    except discord.HTTPException as e:
        if _expired_interaction(e):
            if interaction.response.is_done():
                try:
                    return await interaction.followup.send(ephemeral=ephemeral, **kwargs)
                except Exception:
                    return
            return
        raise


async def _edit(interaction: discord.Interaction, **kwargs):
    try:
        if interaction.response.is_done():
            return await interaction.edit_original_response(**kwargs)
        return await interaction.response.edit_message(**kwargs)
    except discord.NotFound:
        return
    except discord.HTTPException as e:
        if _expired_interaction(e):
            return
        raise


async def _modal(interaction: discord.Interaction, modal: discord.ui.Modal):
    if interaction.response.is_done():
        return
    try:
        await interaction.response.send_modal(modal)
    except discord.NotFound:
        return
    except discord.HTTPException as e:
        if _expired_interaction(e):
            return
        raise


@bot.listen("on_interaction")
async def interaction_router(interaction: discord.Interaction):
    try:
        await _route_interaction(interaction)
    except discord.NotFound as e:
        if not _expired_interaction(e):
            print(f"interaction missing: {e}")
    except discord.HTTPException as e:
        if not _expired_interaction(e):
            print(f"interaction http: {type(e).__name__}: {e}")
    except Exception as e:
        print(f"interaction failed: {type(e).__name__}: {e}")
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message("처리하지 못했습니다. 잠시 후 다시 눌러주세요.", ephemeral=True)
            except Exception:
                pass


async def _route_interaction(interaction: discord.Interaction):
    if interaction.type not in (discord.InteractionType.component, discord.InteractionType.modal_submit):
        return

    cid = (interaction.data or {}).get("custom_id")
    if not cid:
        return

    if str(cid).startswith("t:"):
        return

    if str(cid).startswith("rv:"):
        if interaction.type == discord.InteractionType.component and str(cid).startswith("rv:write:"):
            return await _handle_review_write(interaction, str(cid))
        if interaction.type == discord.InteractionType.modal_submit and str(cid).startswith("rv:submit:"):
            return await _handle_review_submit(interaction, str(cid))
        return

    if not interaction.guild:
        return

    if (
        interaction.type == discord.InteractionType.component
        and not _needs_modal_response(str(cid))
        and not _fast_component(str(cid))
    ):
        if not await _ack(interaction, ephemeral=True, thinking=True):
            return
    elif interaction.type == discord.InteractionType.modal_submit:
        if not await _ack(interaction, ephemeral=True, thinking=True):
            return

    if interaction.type == discord.InteractionType.component:
        if cid == "v:prod":
            return await _handle_product_select(interaction)
        if str(cid).startswith("v:buy:"):
            return await _handle_buy(interaction, str(cid).split(":")[-1])

        if cid == "v:admin":
            return await _handle_admin_menu(interaction)
        if str(cid).startswith("c:appr:"):
            parts = str(cid).split(":")
            if len(parts) >= 4:
                return await _handle_charge_approve(interaction, parts[2], int(parts[3]))
        if str(cid).startswith("c:rej:"):
            parts = str(cid).split(":")
            if len(parts) >= 4:
                return await _handle_charge_reject(interaction, parts[2], int(parts[3]))


        if cid == "v:admin":
            return await _handle_admin_menu(interaction)

        if cid == "k:buy":
            return await _handle_k_buy(interaction)
        if cid == "k:products":
            return await _handle_k_products(interaction)
        if cid == "k:charge":
            return await _handle_k_charge(interaction)
        if cid == "k:charge_pick":
            return await _handle_k_charge_pick(interaction)
        if cid == "k:info":
            return await _handle_k_info(interaction)
        if str(cid).startswith("i:orders:") or str(cid).startswith("i:charges:") or str(cid).startswith("i:home:"):
            return await _handle_my_info_nav(interaction, str(cid))
        if cid == "k:post":
            return await _handle_k_post(interaction)
        if cid == "k:buy_cat":
            return await _handle_k_buy_cat(interaction)
        if cid == "k:buy_prod":
            return await _handle_k_buy_prod(interaction)
        if cid == "k:plist_cat":
            return await _handle_k_plist_cat(interaction)
            return await _handle_vm_info(interaction, int(str(cid).split(":")[-1]))

        if str(cid).startswith("a:cat_del:"):
            return await _handle_admin_cat_del(interaction)
        if cid == "a:prod_add_cat":
            return await _handle_admin_prod_add_cat(interaction)
        if cid == "a:prod_del":
            return await _handle_admin_prod_del(interaction)
        if cid == "a:prod_cfg_pick":
            return await _handle_admin_prod_cfg_pick(interaction)
        if cid == "a:vm_add_cat":
            return await _handle_admin_vm_add_cat(interaction)
        if str(cid).startswith("a:prod_cfg:"):
            return await _handle_admin_prod_cfg_action(interaction, str(cid))
        if str(cid).startswith("a:stock_method:"):
            return await _handle_admin_stock_method(interaction, str(cid))
        if str(cid).startswith("a:log_pick:"):
            return await _handle_admin_log_pick(interaction, str(cid))
        if cid == "a:charge_platform":
            return await _handle_admin_charge_platform(interaction)
        if cid == "a:charge_role":
            return await _handle_admin_charge_role(interaction)
        if cid == "a:charge_role_clear":
            return await _handle_admin_charge_role_clear(interaction)
        if cid == "r:menu":
            return await _handle_root_menu(interaction)


    if interaction.type == discord.InteractionType.modal_submit:
        if str(cid).startswith("v:qty:"):
            return await _handle_qty_submit(interaction, str(cid).split(":")[-1])
        if str(cid).startswith("a:panel_set:"):
            return await _handle_admin_panel_set(interaction)
        if str(cid).startswith("a:cat_add:"):
            return await _handle_admin_cat_add(interaction)
        if str(cid).startswith("a:prod_add:"):
            return await _handle_admin_prod_add(interaction, str(cid).split(":")[-1])
        if str(cid).startswith("a:vm_add:"):
            return await _handle_admin_vm_add(interaction, str(cid).split(":")[-1])
        if str(cid).startswith("a:stock_add:"):
            return await _handle_admin_stock_edit_legacy(interaction, str(cid).split(":")[-1])
        if str(cid).startswith("a:stock_edit:"):
            return await _handle_admin_stock_edit(interaction, str(cid))
        if str(cid).startswith("r:srv_del:"):
            return await _handle_root_srv_del_modal(interaction, str(cid))


async def _handle_vending_machine(interaction: discord.Interaction):
    try:
        vm_id = int((interaction.data or {}).get("values", ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)

    vm = await vending_service.vending_machine(interaction.guild.id, vm_id)
    if not vm:
        return await _reply(interaction, embed=error_embed("자판기를 찾을 수 없어"), ephemeral=True)

    prods = await vending_service.products_in_category(interaction.guild.id, int(vm["category_id"]))
    if not prods:
        return await _reply(interaction, embed=error_embed("상품이 없어"), ephemeral=True)

    v = product_view(await _vip_prods(interaction, [{"id": p["id"], "name": p["name"], "price": p["price"]} for p in prods]))
    await _reply(interaction, content="상품을 선택해주세요.", view=v, ephemeral=True)


async def _handle_product_select(interaction: discord.Interaction):
    try:
        pid = int((interaction.data or {}).get("values", ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)

    p = await vending_service.product(interaction.guild.id, pid)
    if not p:
        return await _reply(interaction, embed=error_embed("상품이 없어"), ephemeral=True)

    stock = await vending_service.stock_count(interaction.guild.id, pid)
    vip = await _vip_of(interaction)
    sale, _ = server_repo.sale_total(int(p["price"]), 1, int((vip or {}).get("purchaseDiscountPct") or (vip or {}).get("discountPct") or 0))
    from ui.v2_layouts import product_detail_layout
    v = product_detail_layout(
        name=str(p["name"]),
        price=int(p["price"]),
        description=p.get("description"),
        stock=int(stock),
        product_id=int(pid),
        sale_price=sale,
        vip_name=(vip or {}).get("name"),
        discount_pct=int((vip or {}).get("purchaseDiscountPct") or (vip or {}).get("discountPct") or 0),
    )
    await _reply(interaction, view=v, ephemeral=True)


async def _handle_buy(interaction: discord.Interaction, product_id: str):
    try:
        pid = int(product_id)
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 상품"), ephemeral=True)
    await _modal(interaction, QtyModal(pid))


async def _handle_qty_submit(interaction: discord.Interaction, product_id: str):
    try:
        pid = int(product_id)
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 상품"), ephemeral=True)

    amount = ""
    for row in (interaction.data or {}).get("components", []):
        for c in row.get("components", []):
            if c.get("custom_id") == "qty":
                amount = c.get("value", "")
    amount = str(amount).strip()

    if not amount.isdigit():
        return await _reply(interaction, embed=error_embed("수량은 숫자만"), ephemeral=True)

    qty = int(amount)
    if qty <= 0 or qty > 999:
        return await _reply(interaction, embed=error_embed("수량 범위가 이상해"), ephemeral=True)

    await _ack(interaction, thinking=True)
    res = await vending_service.purchase(interaction.guild.id, interaction.user.id, pid, qty)
    if not res.get("ok"):
        if res.get("error") == "no_money":
            return await interaction.followup.send(embed=error_embed(f"잔액 부족 (필요: {int(res.get('total',0)):,}원)"), ephemeral=True)
        if res.get("error") == "no_stock":
            return await interaction.followup.send(embed=error_embed("재고 부족"), ephemeral=True)
        return await interaction.followup.send(embed=error_embed("구매 실패"), ephemeral=True)

    role_warning = await _grant_purchase_role(interaction, res)

    from ui.v2_layouts import purchase_complete_layout
    logs = await vending_service.get_log_settings(interaction.guild.id)
    dm_opts = notify.purchase_dm_options(logs)
    delivered = str(res.get("delivered") or "")
    pn = str(res.get("product_name") or "")
    dm_extra = ""
    if dm_opts.get("description"):
        dm_extra = notify.format_template(
            dm_opts["description"],
            {
                "{유저}": interaction.user.mention,
                "{user}": interaction.user.mention,
                "{제품}": pn,
                "{product}": pn,
                "{수량}": str(int(res.get("qty") or 0)),
                "{qty}": str(int(res.get("qty") or 0)),
                "{총액}": f"{int(res.get('total') or 0):,}",
                "{total}": f"{int(res.get('total') or 0):,}",
                "{서버}": str(interaction.guild.name),
                "{server}": str(interaction.guild.name),
            },
        )
    file_to_send = None
    shown = delivered
    if delivered and len(delivered) > 3300:
        data = delivered.encode("utf-8")
        file_to_send = discord.File(io.BytesIO(data), filename=f"delivery_{int(res.get('order_id',0))}.txt")
        shown = "지급 내용이 길어서 파일로 보냈어"
    v2 = purchase_complete_layout(
        product_name=pn,
        delivered=shown,
        accent_color=dm_opts["color"],
        title=dm_opts["title"],
        description=dm_extra or None,
        image_url=dm_opts["image_url"],
    )
    try:
        if file_to_send:
            await interaction.followup.send(view=v2, file=file_to_send, ephemeral=True)
        else:
            await interaction.followup.send(view=v2, ephemeral=True)
    except Exception as e:
        print(f"purchase reply failed order={res.get('order_id')}: {type(e).__name__}: {e}")
        try:
            fallback = discord.File(io.BytesIO(delivered.encode("utf-8")), filename=f"delivery_{int(res.get('order_id', 0))}.txt") if delivered else None
            await interaction.followup.send(content=f"구매가 완료되었습니다.\n{pn}", file=fallback, ephemeral=True)
        except Exception:
            pass
    if role_warning:
        try:
            await interaction.followup.send(embed=error_embed(role_warning), ephemeral=True)
        except Exception:
            pass

    try:
        await notify.send_buy_log(
            interaction.guild.id,
            user=interaction.user,
            category=str(res.get("category_name") or ""),
            product=str(res.get("product_name") or ""),
            qty=int(res.get("qty") or 0),
            total=int(res.get("total") or 0),
        )
    except Exception:
        pass

    try:
        logs = await vending_service.get_log_settings(interaction.guild.id)
        dm_opts = notify.purchase_dm_options(logs)
        delivered = str(res.get("delivered") or "")
        pn = str(res.get("product_name") or "")
        oid = int(res.get("order_id") or 0)
        review_custom_id = f"rv:write:{int(interaction.guild.id)}:{oid}" if oid > 0 else None
        extra = ""
        if dm_opts.get("description"):
            extra = notify.format_template(
                dm_opts["description"],
                {
                    "{유저}": interaction.user.mention,
                    "{user}": interaction.user.mention,
                    "{제품}": pn,
                    "{product}": pn,
                    "{수량}": str(int(res.get("qty") or 0)),
                    "{qty}": str(int(res.get("qty") or 0)),
                    "{총액}": f"{int(res.get('total') or 0):,}",
                    "{total}": f"{int(res.get('total') or 0):,}",
                    "{서버}": str(interaction.guild.name),
                    "{server}": str(interaction.guild.name),
                },
            )
        layout_kwargs = dict(
            product_name=pn,
            delivered=delivered if delivered and len(delivered) <= 3300 else "지급 내용이 길어서 파일로 보냈어",
            review_custom_id=review_custom_id,
            accent_color=dm_opts["color"],
            title=dm_opts["title"],
            description=extra or None,
            image_url=dm_opts["image_url"],
        )
        if delivered and len(delivered) <= 3300:
            await interaction.user.send(view=purchase_complete_layout(**layout_kwargs))
        else:
            data = delivered.encode("utf-8") if delivered else b""
            f = discord.File(io.BytesIO(data), filename=f"delivery_{int(res.get('order_id',0))}.txt")
            await interaction.user.send(view=purchase_complete_layout(**layout_kwargs), file=f)
    except Exception:
        pass


async def _handle_admin_menu(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)

    v = ((interaction.data or {}).get("values") or [""])[0]

    if v == "panel_set":
        mid = interaction.message.id if interaction.message else 0
        m = AdminPanelModal(mid)
        try:
            panel = await vending_service.panel(interaction.guild.id)
            panel = dict(panel) if panel else {}
            if panel.get("title"):
                m.title_input.default = str(panel.get("title"))
            if panel.get("description"):
                m.description_input.default = str(panel.get("description"))
            if panel.get("color") is not None:
                m.color_input.default = hex(int(panel.get("color")))
            if panel.get("image_url"):
                m.image_url_input.default = str(panel.get("image_url"))
        except Exception:
            pass
        return await _modal(interaction, m)

    if v == "cat_add":
        mid = interaction.message.id if interaction.message else 0
        return await _modal(interaction, AdminCategoryAddModal(mid))

    if v == "cat_list":
        from ui.v2_layouts import list_layout, error_toast
        cats = await vending_service.list_categories(interaction.guild.id)
        if not cats:
            return await _reply(interaction, view=error_toast("카테고리가 없어"), ephemeral=True)
        lines = [f"{c['id']}: {c['name']}" for c in cats]
        return await _reply(interaction, view=list_layout(title="카테고리 목록", lines=lines), ephemeral=True)

    if v == "cat_del":
        cats = await vending_service.list_categories(interaction.guild.id)
        if not cats:
            return await _reply(interaction, embed=error_embed("카테고리가 없어"), ephemeral=True)
        opts = [discord.SelectOption(label=c["name"], value=str(c["id"])) for c in cats[:25]]
        mid = interaction.message.id if interaction.message else 0
        return await _reply(interaction, view=select_view(f"a:cat_del:{mid}", "카테고리 선택", opts), ephemeral=True)

    if v == "prod_add":
        cats = await vending_service.list_categories(interaction.guild.id)
        if not cats:
            return await _reply(interaction, embed=error_embed("카테고리를 먼저 만들어줘"), ephemeral=True)
        opts = [discord.SelectOption(label=c["name"], value=str(c["id"])) for c in cats[:25]]
        return await _reply(interaction, view=select_view("a:prod_add_cat", "카테고리 선택", opts), ephemeral=True)

    if v == "prod_list":
        from ui.v2_layouts import list_layout, error_toast
        prods = await vending_service.list_products(interaction.guild.id)
        if not prods:
            return await _reply(interaction, view=error_toast("제품이 없어"), ephemeral=True)
        lines = [f"{p['id']}: [{p['category']}] {p['name']} ({int(p['price']):,}원)" for p in prods]
        return await _reply(interaction, view=list_layout(title="제품 목록", lines=lines), ephemeral=True)

    if v == "prod_del":
        prods = await vending_service.list_products(interaction.guild.id)
        if not prods:
            return await _reply(interaction, embed=error_embed("상품이 없어"), ephemeral=True)
        opts = [discord.SelectOption(label=p["name"][:100], value=str(p["id"]), description=f"{int(p['price']):,}원"[:100]) for p in prods[:25]]
        return await _reply(interaction, view=select_view("a:prod_del", "상품 선택", opts), ephemeral=True)

    if v == "stock_add":
        return await _reply(interaction, embed=error_embed("이 메뉴는 제품 설정으로 옮겨졌어"), ephemeral=True)

    if v == "prod_cfg":
        prods = await vending_service.list_products(interaction.guild.id)
        if not prods:
            return await _reply(interaction, embed=error_embed("상품이 없어"), ephemeral=True)
        opts = [discord.SelectOption(label=p["name"][:100], value=str(p["id"]), description=f"{int(p['price']):,}원"[:100]) for p in prods[:25]]
        return await _reply(interaction, view=select_view("a:prod_cfg_pick", "제품 선택", opts), ephemeral=True)

    if v == "charge_cfg":
        return await _reply(interaction, 
            view=select_view(
                "a:charge_platform",
                "계좌 선택",
                _charge_account_options(),
            ),
            ephemeral=True,
        )
    if v == "charge_role":
        cfg = await vending_service.get_charge_settings(interaction.guild.id)
        cfg = dict(cfg) if cfg else {}
        from ui.v2_layouts import charge_role_select_layout
        role_id = int(cfg.get("charge_manager_role_id") or 0) or None
        return await _reply(interaction, view=charge_role_select_layout(role_id), ephemeral=True)

    if v == "log_cfg":
        from ui.v2_layouts import log_config_pick_layout
        return await _reply(interaction, view=log_config_pick_layout(), ephemeral=True)



    if v == "vm_cfg":
        panel = await vending_service.panel(interaction.guild.id)
        panel = dict(panel) if panel else {}
        title = (panel.get("title") or "").strip()
        desc = (panel.get("description") or "").strip()
        image_url = (panel.get("image_url") or None)
        color = int(panel.get("color") or 0)
        from ui.v2_layouts import vending_machine_message
        view = vending_machine_message(title=title, description=desc, image_url=image_url, color=color)
        return await _reply(interaction, view=view, ephemeral=True)

    if v == "vm_add":
        cats = await vending_service.list_categories(interaction.guild.id)
        if not cats:
            return await _reply(interaction, embed=error_embed("카테고리가 없어"), ephemeral=True)
        opts = [discord.SelectOption(label=c["name"][:100], value=str(c["id"])) for c in cats[:25]]
        return await _reply(interaction, view=select_view("a:vm_add_cat", "카테고리 선택", opts), ephemeral=True)

    await _reply(interaction, embed=error_embed("알 수 없는 작업"), ephemeral=True)


async def _handle_admin_cat_del(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    parts = str((interaction.data or {}).get("custom_id") or "").split(":")
    mid = 0
    if len(parts) >= 3 and parts[2].isdigit():
        mid = int(parts[2])

    try:
        cid = int(((interaction.data or {}).get("values") or ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)
    await _ack(interaction, thinking=True)
    try:
        await vending_service.delete_category(interaction.guild.id, cid)
    except Exception:
        from ui.v2_layouts import error_toast
        return await interaction.followup.send(view=error_toast("삭제할 수 없어(구매내역/연결된 데이터 확인)"), ephemeral=True)
    await _refresh_panel_message(interaction, mid)
    from ui.v2_layouts import ok_toast
    await interaction.followup.send(view=ok_toast("삭제 완료"), ephemeral=True)


async def _handle_admin_prod_add_cat(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    try:
        cat_id = int(((interaction.data or {}).get("values") or ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)
    await _modal(interaction, AdminProductAddModal(cat_id))



async def _handle_admin_vm_add_cat(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    try:
        cat_id = int(((interaction.data or {}).get("values") or ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)
    await _modal(interaction, AdminVendingMachineAddModal(cat_id))


async def _handle_admin_vm_add(interaction: discord.Interaction, cat_id_raw: str):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    try:
        cat_id = int(cat_id_raw)
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 값"), ephemeral=True)

    name = _get_modal_value(interaction, "name").strip()
    if not name:
        return await _reply(interaction, embed=error_embed("이름을 입력해"), ephemeral=True)

    await vending_service.add_vending_machine(interaction.guild.id, name, cat_id)
    return await _reply(interaction, embed=ok_embed("자판기 추가 완료"), ephemeral=True)


async def _handle_admin_prod_del(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    try:
        pid = int(((interaction.data or {}).get("values") or ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)
    await _ack(interaction, thinking=True)
    try:
        await vending_service.delete_product(interaction.guild.id, pid)
    except Exception:
        from ui.v2_layouts import error_toast
        return await interaction.followup.send(view=error_toast("삭제할 수 없어(구매내역/연결된 데이터 확인)"), ephemeral=True)
    from ui.v2_layouts import ok_toast
    await interaction.followup.send(view=ok_toast("삭제 완료"), ephemeral=True)


async def _handle_admin_prod_cfg_pick(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    try:
        pid = int(((interaction.data or {}).get("values") or ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)

    p = await vending_service.product(interaction.guild.id, pid)
    if not p:
        return await _reply(interaction, embed=error_embed("상품이 없어"), ephemeral=True)

    stock = await vending_service.stock_count(interaction.guild.id, pid)
    from ui.v2_layouts import product_config_layout
    view = product_config_layout(name=str(p["name"]), price=int(p["price"]), stock=int(stock), product_id=int(pid))
    await _reply(interaction, view=view, ephemeral=True)


async def _handle_admin_prod_cfg_action(interaction: discord.Interaction, cid: str):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    parts = cid.split(":")
    if len(parts) < 4:
        return await _reply(interaction, embed=error_embed("잘못된 요청"), ephemeral=True)
    action = parts[2]
    try:
        pid = int(parts[3])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 상품"), ephemeral=True)

    if action == "check":
        return await _send_stock_txt(interaction, pid)

    if action in ("add", "set"):
        opts = [
            discord.SelectOption(label="UI로 입력", value="text", description="한 줄=1개"),
            discord.SelectOption(label="txt 파일 업로드", value="txt", description="첨부한 txt를 재고로"),
        ]
        v = select_view(f"a:stock_method:{action}:{pid}", "방식을 선택해주세요", opts)
        return await _reply(interaction, view=v, ephemeral=True)

    await _reply(interaction, embed=error_embed("알 수 없는 작업"), ephemeral=True)


async def _handle_admin_stock_method(interaction: discord.Interaction, cid: str):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)

    parts = cid.split(":")
    if len(parts) < 4:
        return await _reply(interaction, embed=error_embed("잘못된 요청"), ephemeral=True)
    mode = parts[2]
    try:
        pid = int(parts[3])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 상품"), ephemeral=True)

    picked = (((interaction.data or {}).get("values") or [""])[0])
    if picked == "text":
        return await _modal(interaction, AdminStockEditModal(mode, pid))
    if picked == "txt":
        await _reply(interaction, embed=ok_embed("이 채널에 60초 안에 txt 파일을 올려줘(한 줄=1개)"), ephemeral=True)

        def _check(m: discord.Message):
            if not m.attachments:
                return False
            if m.author.id != interaction.user.id:
                return False
            if not m.guild or m.guild.id != interaction.guild.id:
                return False
            if not m.channel or not interaction.channel or m.channel.id != interaction.channel.id:
                return False
            return True

        try:
            msg = await bot.wait_for("message", timeout=60.0, check=_check)
        except asyncio.TimeoutError:
            return

        att = msg.attachments[0]
        if not (att.filename or "").lower().endswith(".txt"):
            return await interaction.followup.send(embed=error_embed("txt 파일만 가능해"), ephemeral=True)
        try:
            data = await att.read()
        except Exception:
            return await interaction.followup.send(embed=error_embed("파일을 읽을 수 없어"), ephemeral=True)

        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            text = str(data)

        lines = [x.strip() for x in str(text).split("\n") if x.strip()]
        if not lines:
            return await interaction.followup.send(embed=error_embed("재고가 비었어"), ephemeral=True)

        if mode == "add":
            info = await vending_service.add_stock_lines(interaction.guild.id, pid, lines, actor_id=interaction.user.id, source="discord")
            _schedule_stock_log(interaction, pid, info)
            return await interaction.followup.send(embed=ok_embed(f"재고 {len(lines)}개 추가"), ephemeral=True)
        info = await vending_service.set_stock_lines(interaction.guild.id, pid, lines, actor_id=interaction.user.id, source="discord")
        _schedule_stock_log(interaction, pid, info)
        return await interaction.followup.send(embed=ok_embed(f"재고 {len(lines)}개로 설정"), ephemeral=True)

    await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)


async def _send_stock_txt(interaction: discord.Interaction, pid: int):
    await _ack(interaction, thinking=True)
    lines = await vending_service.stock_lines(interaction.guild.id, pid)
    body = "\n".join(lines) if lines else ""
    fp = io.BytesIO(body.encode("utf-8"))
    file = discord.File(fp, filename=f"stock_{pid}.txt")
    return await interaction.followup.send(content=f"재고 {len(lines)}개", file=file, ephemeral=True)


async def _handle_admin_panel_set(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)

    parts = str((interaction.data or {}).get("custom_id") or "").split(":")
    mid = 0
    if len(parts) >= 3 and parts[2].isdigit():
        mid = int(parts[2])

    title = _get_modal_value(interaction, "title").strip() or None
    desc = _get_modal_value(interaction, "description").strip() or None
    color_raw = _get_modal_value(interaction, "color").strip() or None
    img = _get_modal_value(interaction, "image_url").strip() or None

    cval = None
    if color_raw:
        try:
            cval = int(color_raw, 0)
        except Exception:
            return await _reply(interaction, embed=error_embed("color 형식이 이상해"), ephemeral=True)

    await _ack(interaction, thinking=True)
    await vending_service.set_panel(interaction.guild.id, title, desc, cval, img)
    await _refresh_panel_message(interaction, mid)
    await interaction.followup.send(embed=ok_embed("패널 설정 저장 완료"), ephemeral=True)


async def _handle_admin_cat_add(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)

    parts = str((interaction.data or {}).get("custom_id") or "").split(":")
    mid = 0
    if len(parts) >= 3 and parts[2].isdigit():
        mid = int(parts[2])

    name = _get_modal_value(interaction, "name").strip()
    if not name:
        return await _reply(interaction, embed=error_embed("이름이 비었어"), ephemeral=True)

    await _ack(interaction, thinking=True)
    try:
        await vending_service.add_category(interaction.guild.id, name)
    except Exception:
        return await interaction.followup.send(embed=error_embed("추가 실패(중복 이름일 수 있어)"), ephemeral=True)
    await _refresh_panel_message(interaction, mid)
    await interaction.followup.send(embed=ok_embed("추가 완료"), ephemeral=True)


async def _handle_admin_prod_add(interaction: discord.Interaction, category_id: str):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)

    try:
        cid = int(category_id)
    except Exception:
        return await _reply(interaction, embed=error_embed("카테고리가 이상해"), ephemeral=True)

    name = _get_modal_value(interaction, "name").strip()
    price_raw = _get_modal_value(interaction, "price").strip().replace(",", "")
    desc = _get_modal_value(interaction, "description").strip() or None

    if not name:
        return await _reply(interaction, embed=error_embed("이름이 비었어"), ephemeral=True)
    if not price_raw.isdigit():
        return await _reply(interaction, embed=error_embed("가격이 이상해"), ephemeral=True)

    price = int(price_raw)
    if price < 0 or price > 10_000_000_000:
        return await _reply(interaction, embed=error_embed("가격 범위가 이상해"), ephemeral=True)

    await _ack(interaction, thinking=True)
    await vending_service.add_product(interaction.guild.id, cid, name, price, desc)
    await notify.product_add_webhook(interaction.guild.id, cid, name)
    await interaction.followup.send(embed=ok_embed("상품 추가 완료"), ephemeral=True)


async def _handle_admin_stock_edit_legacy(interaction: discord.Interaction, product_id: str):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    try:
        pid = int(product_id)
    except Exception:
        return await _reply(interaction, embed=error_embed("상품이 이상해"), ephemeral=True)
    raw = _get_modal_value(interaction, "text")
    lines = [x.strip() for x in str(raw).split("\n") if x.strip()]
    if not lines:
        return await _reply(interaction, embed=error_embed("재고가 비었어"), ephemeral=True)
    await _ack(interaction, thinking=True)
    info = await vending_service.add_stock_lines(interaction.guild.id, pid, lines, actor_id=interaction.user.id, source="discord")
    _schedule_stock_log(interaction, pid, info)
    await interaction.followup.send(embed=ok_embed(f"재고 {len(lines)}개 추가"), ephemeral=True)


async def _handle_admin_stock_edit(interaction: discord.Interaction, cid: str):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)

    parts = cid.split(":")
    if len(parts) < 4:
        return await _reply(interaction, embed=error_embed("잘못된 요청"), ephemeral=True)
    mode = parts[2]
    try:
        pid = int(parts[3])
    except Exception:
        return await _reply(interaction, embed=error_embed("상품이 이상해"), ephemeral=True)

    raw = _get_modal_value(interaction, "text")
    lines = [x.strip() for x in str(raw).split("\n") if x.strip()]
    if not lines:
        return await _reply(interaction, embed=error_embed("재고가 비었어"), ephemeral=True)

    await _ack(interaction, thinking=True)
    if mode == "add":
        info = await vending_service.add_stock_lines(interaction.guild.id, pid, lines, actor_id=interaction.user.id, source="discord")
        _schedule_stock_log(interaction, pid, info)
        return await interaction.followup.send(embed=ok_embed(f"재고 {len(lines)}개 추가"), ephemeral=True)

    info = await vending_service.set_stock_lines(interaction.guild.id, pid, lines, actor_id=interaction.user.id, source="discord")
    _schedule_stock_log(interaction, pid, info)
    await interaction.followup.send(embed=ok_embed(f"재고 {len(lines)}개로 설정"), ephemeral=True)


async def _refresh_panel_message(interaction: discord.Interaction, message_id: int):
    if not message_id or not interaction.guild:
        return
    msg = None
    if interaction.message and int(interaction.message.id) == int(message_id):
        msg = interaction.message
    elif interaction.channel:
        try:
            msg = await interaction.channel.fetch_message(int(message_id))
        except Exception:
            msg = None
    if not msg:
        return

    prow = await vending_service.panel(interaction.guild.id)
    panel = dict(prow) if prow else {}
    view = VendingPanelLayout(
        title=(panel.get("title") or "").strip(),
        description=(panel.get("description") or "").strip(),
        color=int(panel.get("color") or 0x5865F2),
        timeout=300,
    )
    try:
        await msg.edit(view=view)
    except Exception:
        return



@bot.event
async def on_message(message: discord.Message):
    if not message.guild:
        return await bot.process_commands(message)
    try:
        cfg = await vending_service.get_charge_settings(message.guild.id)
        cfg = dict(cfg) if cfg else {}
    except Exception:
        return await bot.process_commands(message)
    if int(cfg.get("ios_enabled") or 0) != 1:
        return await bot.process_commands(message)
    ch_id = cfg.get("ios_log_channel_id")
    if not ch_id:
        return await bot.process_commands(message)
    if message.channel.id != int(ch_id):
        return await bot.process_commands(message)

    if message.author and bot.user and message.author.id == bot.user.id:
        return
    if message.webhook_id is None and not (message.author and message.author.bot):
        return await bot.process_commands(message)

    text_parts = []
    if message.content:
        text_parts.append(message.content)
    for e in message.embeds:
        if e.title:
            text_parts.append(e.title)
        if e.description:
            text_parts.append(e.description)
        for f in e.fields:
            if f.name:
                text_parts.append(f.name)
            if f.value:
                text_parts.append(f.value)
    text = "\n".join(text_parts)

    if not text.strip():
        print(f"[ios-webhook] message received but empty content/embeds (message_content intent?) mid={message.id}")
        return await bot.process_commands(message)

    m = re.search(r"([0-9][0-9,]*)\s*원", text)
    if not m:
        m = re.search(r"₩\s*([0-9][0-9,]*)", text)
    if not m:
        m = re.search(r"(?:금액|입금|송금)\s*[:：]?\s*([0-9][0-9,]*)", text)
    if not m:
        print(f"[ios-webhook] amount parse fail mid={message.id} text={text[:200]}")
        return await bot.process_commands(message)
    amount = int(m.group(1).replace(",", ""))
    depositor = ""
    for key in ("입금자", "보낸사람", "보낸 분", "보낸이", "송금인"):
        i = text.find(key)
        if i != -1:
            tail = text[i+len(key):]
            tail = re.sub(r"[:：\-\s]+", " ", tail).strip()
            tok = tail.split()[0] if tail.split() else ""
            if tok:
                depositor = tok
                break

    pending = await vending_service.ios_process_webhook(message.guild.id, message.id, amount, depositor or None)
    if not pending:
        print(f"[ios-webhook] no pending match mid={message.id} amount={amount} depositor={depositor or '-'}")
        return await bot.process_commands(message)

    try:
        await message.add_reaction("✅")
    except Exception:
        try:
            await message.reply("✅ 확인 완료", mention_author=False)
        except Exception:
            pass

    try:
        await _edit_request_message(message.guild.id, "IOS", dict(pending), "done")
    except Exception:
        pass

    return await bot.process_commands(message)


def _acquire_single_instance():
    if os.name == "nt":
        return None
    import fcntl
    from pathlib import Path
    from config import DATA_DIR
    path = Path(DATA_DIR) / "bot.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(path, "w")
    try:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("bot already running; exit")
        raise SystemExit(0)
    fp.write(str(os.getpid()))
    fp.flush()
    return fp


def main():
    _acquire_single_instance()
    bot.run(DISCORD_TOKEN)

def _is_root_user(uid: int) -> bool:
    try:
        from utils.auth import is_root
        return bool(is_root(int(uid)))
    except Exception:
        return False


async def _handle_root_menu(interaction: discord.Interaction):
    if not interaction.user or not _is_root_user(interaction.user.id):
        return await _reply(interaction, embed=error_embed("권한이 없어"), ephemeral=True)
    v = (((interaction.data or {}).get("values") or [""])[0])
    if v == "srv_del":
        return await _modal(interaction, RootServerIdModal("r:srv_del:go", "서버 데이터 삭제"))
    return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)

async def _handle_root_srv_del_modal(interaction: discord.Interaction, cid: str):
    if not interaction.user or not _is_root_user(interaction.user.id):
        return await _reply(interaction, embed=error_embed("권한이 없어"), ephemeral=True)
    sid_raw = _get_modal_value(interaction, "server_id").strip()
    try:
        gid = int(sid_raw)
    except Exception:
        return await _reply(interaction, embed=error_embed("서버 아이디가 이상해"), ephemeral=True)
    await _ack(interaction, thinking=True)
    try:
        from utils.paths import data_root
        import shutil as _sh
        d = data_root() / "servers" / str(gid)
        if d.exists():
            _sh.rmtree(d, ignore_errors=True)
    except Exception:
        pass
    await interaction.followup.send(embed=ok_embed("서버 데이터 삭제 완료"), ephemeral=True)


class ChargeConfigModal(discord.ui.Modal):
    def __init__(self, mode: str):
        self.mode = mode
        title = f"{_charge_account_label(mode)} 충전 설정"
        super().__init__(title=title, timeout=300)
        self.bank_name = discord.ui.TextInput(label="은행명", required=True, style=discord.TextStyle.short, max_length=30)
        self.bank_account = discord.ui.TextInput(label="계좌번호", required=True, style=discord.TextStyle.short, max_length=40)
        self.bank_owner = discord.ui.TextInput(label="예금주", required=True, style=discord.TextStyle.short, max_length=30)
        self.add_item(self.bank_name)
        self.add_item(self.bank_account)
        self.add_item(self.bank_owner)
        self.pushbullet = None
        if mode == "AOS":
            self.pushbullet = discord.ui.TextInput(label="Pushbullet 토큰", required=True, style=discord.TextStyle.short, max_length=200)
            self.add_item(self.pushbullet)
        self.ios_channel = None
        if mode == "IOS":
            self.ios_channel = discord.ui.TextInput(label="계좌 2 충전로그 채널(ID 또는 #멘션)", required=True, style=discord.TextStyle.short, max_length=80)
            self.add_item(self.ios_channel)

    async def on_submit(self, interaction: discord.Interaction):
        bn = str(self.bank_name.value).strip()
        ba = str(self.bank_account.value).strip()
        bo = str(self.bank_owner.value).strip()
        ios_ch_id = None
        if self.ios_channel is not None:
            raw = str(self.ios_channel.value).strip()
            m = re.search(r"(\d{15,})", raw)
            if not m:
                return await _reply(interaction, embed=error_embed("채널 ID를 찾지 못했어"), ephemeral=True)
            ios_ch_id = int(m.group(1))

        if self.mode == "AOS":
            tok = str(self.pushbullet.value).strip() if getattr(self, "pushbullet", None) is not None else None
            if not tok:
                return await _reply(interaction, embed=error_embed("Pushbullet 토큰은 필수야"), ephemeral=True)
            await vending_service.set_aos_charge_settings(interaction.guild.id, bn, ba, bo, tok or None)
            return await _reply(interaction, embed=ok_embed("계좌 1 충전 설정 저장 완료"), ephemeral=True)

        if self.mode == "IOS":
            if ios_ch_id is None:
                return await _reply(interaction, embed=error_embed("계좌 2 충전로그 채널이 필요해"), ephemeral=True)
            await vending_service.set_ios_charge_settings(interaction.guild.id, bn, ba, bo, ios_ch_id)
            return await _reply(interaction, embed=ok_embed("계좌 2 충전 설정 저장 완료"), ephemeral=True)

        return await _reply(interaction, embed=error_embed("설정 오류"), ephemeral=True)

async def _handle_charge_platform(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    platform = str(((interaction.data or {}).get("values") or [""])[0]).upper()
    if platform not in ("AOS", "IOS"):
        return await _reply(interaction, embed=error_embed("선택 오류"), ephemeral=True)
    return await _modal(interaction, ChargeConfigModal(platform))

async def _handle_vm_open(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    try:
        vm_id = int(((interaction.data or {}).get("values") or ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("선택 오류"), ephemeral=True)

    panel = await vending_service.panel(interaction.guild.id)
    vm = await vending_service.vending_machine(interaction.guild.id, vm_id)
    if not vm:
        return await _reply(interaction, embed=error_embed("자판기 없음"), ephemeral=True)

    from ui.v2_layouts import vending_machine_message
    view = vending_machine_message(
        title=(panel.get("title") or "").strip(),
        description=(panel.get("description") or "").strip(),
        image_url=panel.get("image_url"),
        color=int(panel.get("color") or 0x5865F2),
        vm_id=int(vm["id"]),
        vm_name=vm["name"],
    )
    return await _reply(interaction, view=view, ephemeral=True)


async def _handle_k_buy(interaction: discord.Interaction):
    cats = await vending_service.list_categories(interaction.guild.id)
    if not cats:
        return await _reply(interaction, embed=error_embed("카테고리가 없어"), ephemeral=True)
    return await _reply(interaction, view=purchase_dual_select_view(cats), ephemeral=True)

async def _handle_k_buy_cat(interaction: discord.Interaction):
    cats = await vending_service.list_categories(interaction.guild.id)
    try:
        cid = int((interaction.data or {}).get("values", ["0"])[0])
    except Exception:
        if interaction.response.is_done():
            return await interaction.followup.send(embed=error_embed("잘못된 선택"), ephemeral=True)
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)
    prods = await vending_service.products_in_category(interaction.guild.id, cid)
    counts = await vending_service.stock_counts(interaction.guild.id, [int(p["id"]) for p in (prods or [])])
    enriched = []
    for p in prods or []:
        item = dict(p)
        item["stock"] = int(counts.get(int(item["id"]), 0))
        enriched.append(item)
    view = purchase_dual_select_view(cats, await _vip_prods(interaction, enriched), cid)
    if interaction.response.is_done():
        return await interaction.edit_original_response(view=view)
    return await _edit(interaction, view=view)

async def _handle_k_buy_prod(interaction: discord.Interaction):
    try:
        pid = int((interaction.data or {}).get("values", ["0"])[0])
    except Exception:
        return await _reply(interaction, embed=error_embed("잘못된 선택"), ephemeral=True)
    if pid <= 0:
        return await _reply(interaction, embed=error_embed("제품을 선택해주세요."), ephemeral=True)
    return await _modal(interaction, QtyModal(pid))

async def _handle_k_products(interaction: discord.Interaction):
    cats = await vending_service.list_categories(interaction.guild.id)
    if not cats:
        return await _reply(interaction, embed=error_embed("카테고리가 없어"), ephemeral=True)
    opts = [discord.SelectOption(label=c["name"][:100], value=str(c["id"])) for c in cats[:25]]
    return await _reply(interaction, view=select_view("k:plist_cat", "카테고리 선택", opts), ephemeral=True)

async def _handle_k_plist_cat(interaction: discord.Interaction):
    from ui.v2_layouts import list_layout, error_toast
    try:
        cid = int((interaction.data or {}).get("values", ["0"])[0])
    except Exception:
        return await _reply(interaction, view=error_toast("잘못된 선택"), ephemeral=True)
    prods = await vending_service.products_in_category(interaction.guild.id, cid)
    if not prods:
        return await _reply(interaction, view=error_toast("제품이 없어"), ephemeral=True)
    vip = await _vip_of(interaction)
    counts = await vending_service.stock_counts(interaction.guild.id, [int(p["id"]) for p in prods])
    lines = []
    for p in prods:
        sc = int(counts.get(int(p["id"]), 0))
        lines.append(f"- {p['name']} | {vending_service.price_label(int(p['price']), vip)} | 재고 {sc}")
    return await _reply(interaction, view=list_layout(title="제품 목록", lines=lines), ephemeral=True)

async def _handle_k_info(interaction: discord.Interaction):
    try:
        view = await _my_info_view(interaction.guild.id, interaction.user)
        return await _reply(interaction, view=view)
    except Exception as e:
        print(f"my info failed: {type(e).__name__}: {e}")
        from ui.v2_layouts import error_toast
        return await _reply(interaction, view=error_toast("내 정보를 불러오지 못했습니다."))


async def _handle_my_info_nav(interaction: discord.Interaction, cid: str):
    parts = str(cid).split(":")
    kind = parts[1] if len(parts) > 1 else ""
    uid = _info_uid(interaction, parts[2] if len(parts) > 2 else None)
    if uid is None:
        from ui.v2_layouts import error_toast
        return await _reply_info(interaction, error_toast("다른 사람 내역은 볼 수 없습니다."), edit=True)
    if kind == "orders":
        return await _reply_info(interaction, await _my_orders_view(interaction.guild.id, uid), edit=True)
    if kind == "charges":
        return await _reply_info(interaction, await _my_charges_view(interaction.guild.id, uid), edit=True)
    target = interaction.user if uid == int(interaction.user.id) else await interaction.guild.fetch_member(uid)
    return await _reply_info(interaction, await _my_info_view(interaction.guild.id, target), edit=True)
async def _handle_admin_charge_platform(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    v = ((interaction.data or {}).get("values") or [""])[0]
    if v not in ("AOS", "IOS"):
        return await _reply(interaction, embed=error_embed("선택이 이상해"), ephemeral=True)
    cfg = await vending_service.get_charge_settings(interaction.guild.id)
    cfg = dict(cfg) if cfg else {}
    m = ChargeConfigModal(v)
    try:
        p = str(v).lower()
        bn = (cfg.get(f"{p}_bank_name") or "").strip()
        ba = (cfg.get(f"{p}_bank_account") or "").strip()
        bo = (cfg.get(f"{p}_bank_owner") or "").strip()
        if bn:
            m.bank_name.default = bn
        if ba:
            m.bank_account.default = ba
        if bo:
            m.bank_owner.default = bo
        if v == "AOS":
            tok = (cfg.get("pushbullet_token") or "").strip()
            if tok and getattr(m, "pushbullet", None) is not None:
                m.pushbullet.default = tok
        if v == "IOS":
            cid = cfg.get("ios_log_channel_id")
            if cid and getattr(m, "ios_channel", None) is not None:
                m.ios_channel.default = str(int(cid))
    except Exception:
        pass
    return await _modal(interaction, m)


async def _handle_admin_charge_role(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능합니다."), ephemeral=True)
    if not interaction.guild:
        return await _reply(interaction, embed=error_embed("서버에서만 가능합니다."), ephemeral=True)

    raw = (((interaction.data or {}).get("values") or [""])[0])
    try:
        role_id = int(raw)
    except Exception:
        return await _reply(interaction, embed=error_embed("역할을 선택해주세요."), ephemeral=True)

    role = interaction.guild.get_role(role_id)
    if not role:
        return await _reply(interaction, embed=error_embed("역할을 찾을 수 없습니다."), ephemeral=True)

    await vending_service.set_charge_manager_role(interaction.guild.id, role_id)
    return await _reply(interaction, embed=ok_embed(f"수동충전 권한을 {role.mention} 역할로 설정했습니다."), ephemeral=True)


async def _handle_admin_charge_role_clear(interaction: discord.Interaction):
    if not _is_admin(interaction):
        return await _reply(interaction, embed=error_embed("관리자만 가능합니다."), ephemeral=True)
    if not interaction.guild:
        return await _reply(interaction, embed=error_embed("서버에서만 가능합니다."), ephemeral=True)

    await vending_service.set_charge_manager_role(interaction.guild.id, None)
    return await _reply(interaction, embed=ok_embed("수동충전 권한을 해제했습니다. 이제 관리자만 수동충전을 할 수 있습니다."), ephemeral=True)



class BuyLogConfigModal(discord.ui.Modal):
    def __init__(self, defaults=None):
        super().__init__(title="구매 로그 설정", timeout=300)
        d = defaults or {}
        self.buy_channel_id = discord.ui.TextInput(label="구매로그 채널 ID", required=False, style=discord.TextStyle.short, max_length=30)
        self.buy_desc_template = discord.ui.TextInput(label="구매로그 내용 템플릿", required=False, style=discord.TextStyle.paragraph, max_length=500, default="{유저}님 {카테고리} • {제품} 구매 감사합니다")
        self.buy_color = discord.ui.TextInput(label="임베드 색상(0xRRGGBB)", required=False, style=discord.TextStyle.short, max_length=16, placeholder="0x5865F2")
        self.buy_image = discord.ui.TextInput(label="이미지 URL", required=False, style=discord.TextStyle.short, max_length=300)
        if d.get("buy_channel_id"):
            self.buy_channel_id.default = str(d.get("buy_channel_id"))
        if d.get("buy_desc_template"):
            self.buy_desc_template.default = str(d.get("buy_desc_template"))
        if d.get("buy_embed_color") is not None:
            self.buy_color.default = hex(int(d.get("buy_embed_color")))
        if d.get("buy_image_url"):
            self.buy_image.default = str(d.get("buy_image_url"))
        self.add_item(self.buy_channel_id)
        self.add_item(self.buy_desc_template)
        self.add_item(self.buy_color)
        self.add_item(self.buy_image)

    async def on_submit(self, interaction: discord.Interaction):
        from ui.v2_layouts import ok_toast, error_toast
        if not interaction.guild:
            return await _reply(interaction, view=error_toast("서버에서만 가능해"), ephemeral=True)

        def _to_int(x: str):
            x = (x or "").strip().replace("<#", "").replace(">", "")
            return int(x) if x.isdigit() else None

        logs = await vending_service.get_log_settings(interaction.guild.id)
        logs = dict(logs) if logs else {}
        buy_ch = _to_int(str(self.buy_channel_id.value))
        buy_t = str(self.buy_desc_template.value).strip() or None
        charge_ch = int(logs.get("charge_channel_id")) if logs.get("charge_channel_id") else None
        color_raw = str(self.buy_color.value or "").strip()
        color_val = None
        if color_raw:
            try:
                color_val = int(color_raw, 0)
            except Exception:
                try:
                    color_val = int(color_raw.replace("#", ""), 16)
                except Exception:
                    color_val = logs.get("buy_embed_color")
        extra = {}
        if color_val is not None:
            extra["buy_embed_color"] = color_val
        if str(self.buy_image.value or "").strip():
            extra["buy_image_url"] = str(self.buy_image.value).strip()
        await vending_service.set_log_settings(interaction.guild.id, buy_ch, buy_t, charge_ch, **extra)
        return await _reply(interaction, view=ok_toast("구매 로그 저장 완료"), ephemeral=True)


class ChargeLogConfigModal(discord.ui.Modal):
    def __init__(self, defaults=None):
        super().__init__(title="충전 로그 설정", timeout=300)
        d = defaults or {}
        self.charge_channel_id = discord.ui.TextInput(label="충전로그 채널 ID", required=False, style=discord.TextStyle.short, max_length=30)
        if d.get("charge_channel_id"):
            self.charge_channel_id.default = str(d.get("charge_channel_id"))
        self.add_item(self.charge_channel_id)

    async def on_submit(self, interaction: discord.Interaction):
        from ui.v2_layouts import ok_toast, error_toast
        if not interaction.guild:
            return await _reply(interaction, view=error_toast("서버에서만 가능해"), ephemeral=True)

        def _to_int(x: str):
            x = (x or "").strip().replace("<#", "").replace(">", "")
            return int(x) if x.isdigit() else None

        logs = await vending_service.get_log_settings(interaction.guild.id)
        logs = dict(logs) if logs else {}
        buy_ch = int(logs.get("buy_channel_id")) if logs.get("buy_channel_id") else None
        buy_t = str(logs.get("buy_desc_template") or "").strip() or None
        charge_ch = _to_int(str(self.charge_channel_id.value))
        await vending_service.set_log_settings(interaction.guild.id, buy_ch, buy_t, charge_ch)
        return await _reply(interaction, view=ok_toast("충전 로그 저장 완료"), ephemeral=True)


class ReviewLogConfigModal(discord.ui.Modal):
    def __init__(self, defaults=None):
        super().__init__(title="후기 로그 설정", timeout=300)
        d = defaults or {}
        self.review_channel_id = discord.ui.TextInput(label="후기로그 채널 ID", required=False, style=discord.TextStyle.short, max_length=30)
        if d.get("review_channel_id"):
            self.review_channel_id.default = str(d.get("review_channel_id"))
        self.add_item(self.review_channel_id)

    async def on_submit(self, interaction: discord.Interaction):
        from ui.v2_layouts import ok_toast, error_toast
        if not interaction.guild:
            return await _reply(interaction, view=error_toast("서버에서만 가능해"), ephemeral=True)

        def _to_int(x: str):
            x = (x or "").strip().replace("<#", "").replace(">", "")
            return int(x) if x.isdigit() else None

        logs = await vending_service.get_log_settings(interaction.guild.id)
        logs = dict(logs) if logs else {}
        buy_ch = int(logs.get("buy_channel_id")) if logs.get("buy_channel_id") else None
        buy_t = str(logs.get("buy_desc_template") or "").strip() or None
        charge_ch = int(logs.get("charge_channel_id")) if logs.get("charge_channel_id") else None
        review_ch = _to_int(str(self.review_channel_id.value))
        await vending_service.set_log_settings(interaction.guild.id, buy_ch, buy_t, charge_ch, review_ch)
        return await _reply(interaction, view=ok_toast("후기 로그 저장 완료"), ephemeral=True)


class StockLogConfigModal(discord.ui.Modal):
    def __init__(self, defaults=None):
        super().__init__(title="입고 로그 설정", timeout=300)
        d = defaults or {}
        self.stock_channel_id = discord.ui.TextInput(label="입고로그 채널 ID", required=False, style=discord.TextStyle.short, max_length=30)
        self.stock_desc_template = discord.ui.TextInput(
            label="입고로그 내용 템플릿",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500,
            default="{제품} >> {수량}개 추가",
        )
        self.stock_color = discord.ui.TextInput(label="임베드 색상(0xRRGGBB)", required=False, style=discord.TextStyle.short, max_length=16, placeholder="0x57F287")
        self.stock_image = discord.ui.TextInput(label="이미지 URL", required=False, style=discord.TextStyle.short, max_length=300)
        self.stock_everyone = discord.ui.TextInput(label="애브핑 (1 켜기 / 0 끄기)", required=False, style=discord.TextStyle.short, max_length=1, default="1")
        if d.get("stock_channel_id"):
            self.stock_channel_id.default = str(d.get("stock_channel_id"))
        if d.get("stock_desc_template"):
            self.stock_desc_template.default = str(d.get("stock_desc_template"))
        if d.get("stock_embed_color") is not None:
            self.stock_color.default = hex(int(d.get("stock_embed_color")))
        if d.get("stock_image_url"):
            self.stock_image.default = str(d.get("stock_image_url"))
        if d.get("stock_everyone") is not None:
            self.stock_everyone.default = "1" if int(d.get("stock_everyone") or 0) == 1 else "0"
        self.add_item(self.stock_channel_id)
        self.add_item(self.stock_desc_template)
        self.add_item(self.stock_color)
        self.add_item(self.stock_image)
        self.add_item(self.stock_everyone)

    async def on_submit(self, interaction: discord.Interaction):
        from ui.v2_layouts import ok_toast, error_toast
        if not interaction.guild:
            return await _reply(interaction, view=error_toast("서버에서만 가능해"), ephemeral=True)

        def _to_int(x: str):
            x = (x or "").strip().replace("<#", "").replace(">", "")
            return int(x) if x.isdigit() else None

        logs = await vending_service.get_log_settings(interaction.guild.id)
        logs = dict(logs) if logs else {}
        buy_ch = int(logs.get("buy_channel_id")) if logs.get("buy_channel_id") else None
        buy_t = str(logs.get("buy_desc_template") or "").strip() or None
        charge_ch = int(logs.get("charge_channel_id")) if logs.get("charge_channel_id") else None
        review_ch = int(logs.get("review_channel_id")) if logs.get("review_channel_id") else None
        stock_ch = _to_int(str(self.stock_channel_id.value))
        stock_t = str(self.stock_desc_template.value).strip() or None
        color_raw = str(self.stock_color.value or "").strip()
        color_val = None
        if color_raw:
            try:
                color_val = int(color_raw, 0)
            except Exception:
                try:
                    color_val = int(color_raw.replace("#", ""), 16)
                except Exception:
                    color_val = logs.get("stock_embed_color")
        extra = {}
        if color_val is not None:
            extra["stock_embed_color"] = color_val
        if str(self.stock_image.value or "").strip():
            extra["stock_image_url"] = str(self.stock_image.value).strip()
        ping_raw = str(self.stock_everyone.value or "").strip()
        if ping_raw in {"0", "1"}:
            extra["stock_everyone"] = int(ping_raw)
        await vending_service.set_log_settings(
            interaction.guild.id, buy_ch, buy_t, charge_ch, review_ch, stock_ch, stock_t, **extra
        )
        return await _reply(interaction, view=ok_toast("입고 로그 저장 완료"), ephemeral=True)


class ReviewWriteModal(discord.ui.Modal):
    def __init__(self, guild_id: int, order_id: int):
        super().__init__(title="후기 작성", custom_id=f"rv:submit:{int(guild_id)}:{int(order_id)}", timeout=300)
        self.content = discord.ui.TextInput(
            custom_id="content",
            label="후기 내용",
            placeholder="구매 후기를 적어줘",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.add_item(self.content)


async def _send_review_response(interaction: discord.Interaction, *, embed: discord.Embed):
    kwargs = {"ephemeral": True} if interaction.guild else {}
    if interaction.response.is_done():
        return await interaction.followup.send(embed=embed, **kwargs)
    return await _reply(interaction, embed=embed, **kwargs)


def _parse_review_custom_id(cid: str):
    parts = str(cid or "").split(":")
    if len(parts) < 4:
        return None, None
    try:
        return int(parts[2]), int(parts[3])
    except Exception:
        return None, None


async def _handle_review_write(interaction: discord.Interaction, cid: str):
    guild_id, order_id = _parse_review_custom_id(cid)
    if not guild_id or not order_id:
        return await _send_review_response(interaction, embed=error_embed("후기 요청이 올바르지 않아"))

    order = await vending_service.order(guild_id, order_id)
    if not order:
        return await _send_review_response(interaction, embed=error_embed("주문 정보를 찾을 수 없어"))
    if int(order.get("user_id") or 0) != int(interaction.user.id):
        return await _send_review_response(interaction, embed=error_embed("구매한 유저만 후기를 작성할 수 있어"))

    return await _modal(interaction, ReviewWriteModal(guild_id, order_id))


async def _handle_review_submit(interaction: discord.Interaction, cid: str):
    if not await _ack(interaction, ephemeral=bool(interaction.guild), thinking=True):
        return
    guild_id, order_id = _parse_review_custom_id(cid)
    if not guild_id or not order_id:
        return await _send_review_response(interaction, embed=error_embed("후기 요청이 올바르지 않아"))

    content = _get_modal_value(interaction, "content").strip()
    if len(content) < 2:
        return await _send_review_response(interaction, embed=error_embed("후기 내용을 2자 이상 입력해주세요."))

    order = await vending_service.order(guild_id, order_id)
    if not order:
        return await _send_review_response(interaction, embed=error_embed("주문 정보를 찾을 수 없어"))
    if int(order.get("user_id") or 0) != int(interaction.user.id):
        return await _send_review_response(interaction, embed=error_embed("구매한 유저만 후기를 작성할 수 있어"))

    kwargs = {"ephemeral": True} if interaction.guild else {}

    logs = await vending_service.get_log_settings(guild_id)
    logs = dict(logs) if logs else {}
    review_channel_id = logs.get("review_channel_id")
    if not review_channel_id:
        return await interaction.followup.send(embed=error_embed("후기 로그 채널이 아직 설정되지 않았어"), **kwargs)

    guild = bot.get_guild(int(guild_id))
    review_ch = await _resolve_log_channel(guild, int(review_channel_id))
    if not isinstance(review_ch, discord.abc.Messageable):
        return await interaction.followup.send(embed=error_embed("후기 로그 채널을 찾지 못했어"), **kwargs)

    product_name = str(order.get("product_name") or "상품")
    category_name = str(order.get("category_name") or "")
    tmpl = str(logs.get("review_desc_template") or "").strip()
    desc = _fmt_template(
        tmpl,
        user=interaction.user,
        category=category_name,
        product=product_name,
        qty=int(order.get("qty") or 0),
        total=int(order.get("total") or 0),
        content=content,
    ) if tmpl else content
    emb = discord.Embed(title="후기 로그", description=desc[:4000], color=0xFEE75C)
    emb.add_field(name="유저", value=interaction.user.mention, inline=True)
    emb.add_field(name="상품", value=f"{category_name} • {product_name}".strip(" •"), inline=True)
    emb.add_field(name="수량", value=str(int(order.get("qty") or 0)), inline=True)
    emb.add_field(name="주문번호", value=f"`{int(order_id)}`", inline=True)
    emb.timestamp = discord.utils.utcnow()
    try:
        emb.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    except Exception:
        pass

    await _send_embed_channel(channel=review_ch, embed=emb)
    return await interaction.followup.send(embed=ok_embed("후기 작성 완료"), **kwargs)




async def _handle_admin_log_pick(interaction: discord.Interaction, cid: str):
    if not _is_admin(interaction):
        from ui.v2_layouts import error_toast
        return await _reply(interaction, view=error_toast("관리자만 가능해"), ephemeral=True)
    parts = str(cid).split(":")
    kind = parts[2] if len(parts) >= 3 else ""
    logs = await vending_service.get_log_settings(interaction.guild.id)
    logs = dict(logs) if logs else {}
    if kind == "buy":
        return await _modal(interaction, BuyLogConfigModal(logs))
    if kind == "charge":
        return await _modal(interaction, ChargeLogConfigModal(logs))
    if kind == "review":
        return await _modal(interaction, ReviewLogConfigModal(logs))
    if kind == "stock":
        return await _modal(interaction, StockLogConfigModal(logs))
    from ui.v2_layouts import error_toast
    return await _reply(interaction, view=error_toast("잘못된 선택"), ephemeral=True)

class ChargeRequestModal(discord.ui.Modal):
    def __init__(self, platform: str):
        self.platform = platform.upper()
        super().__init__(title=f"{_charge_account_label(self.platform)} 충전 요청", timeout=300)
        self.amount = discord.ui.TextInput(label="금액(원)", required=True, style=discord.TextStyle.short, max_length=20)
        self.depositor = discord.ui.TextInput(label="입금자명", required=True, style=discord.TextStyle.short, max_length=30)
        self.add_item(self.amount)
        self.add_item(self.depositor)

    async def on_submit(self, interaction: discord.Interaction):
        raw_amt = str(self.amount.value).strip().replace(",", "")
        if not raw_amt.isdigit():
            return await _reply(interaction, embed=error_embed("금액이 올바르지 않아"), ephemeral=True)
        amt = int(raw_amt)
        if amt <= 0:
            return await _reply(interaction, embed=error_embed("금액은 1원 이상"), ephemeral=True)

        depositor = str(self.depositor.value).strip()
        if not depositor:
            return await _reply(interaction, embed=error_embed("입금자명을 입력해주세요."), ephemeral=True)

        if not interaction.guild:
            return await _reply(interaction, embed=error_embed("서버에서만 가능해"), ephemeral=True)

        await _ack(interaction, thinking=True)
        try:
            cfg = await vending_service.get_charge_settings(interaction.guild.id)
            cfg = dict(cfg) if cfg else {}
            min_amount = max(1, int(cfg.get("min_charge_amount") or 1))
            if amt < min_amount:
                return await interaction.edit_original_response(embed=error_embed(f"최소 충전 금액은 {min_amount:,}원입니다."))

            platform = self.platform
            pid = None

            if platform == "IOS":
                if "IOS" not in _enabled_charge_platforms(cfg):
                    return await interaction.edit_original_response(embed=error_embed("계좌 2 충전 설정이 비어있거나 완성되지 않았어"))
                pid = await vending_service.ios_create_pending(interaction.guild.id, interaction.user.id, amt, depositor)
            else:
                if "AOS" not in _enabled_charge_platforms(cfg):
                    return await interaction.edit_original_response(embed=error_embed("계좌 1 충전 설정이 비어있거나 완성되지 않았어"))
                tok = str(cfg.get("pushbullet_token") or "").strip()
                pid = await vending_service.aos_create_pending(interaction.guild.id, interaction.user.id, amt, depositor)
                PB_MANAGER.watch(tok, interaction.guild.id, pid=int(pid) if pid else None, seconds=300)

            if not pid:
                return await interaction.edit_original_response(embed=error_embed("충전요청 생성 실패"))

            key = _pending_key(interaction.guild.id, platform, int(pid))
            emb = await _charge_ephemeral_embed(
                interaction.guild.id,
                platform,
                amount=int(amt),
                depositor=depositor,
                status="pending",
            )
            await interaction.edit_original_response(embed=emb)
            try:
                original_msg = await interaction.original_response()
                EPHEMERAL_CHARGE_MSGS[key] = original_msg
                if original_msg and getattr(original_msg, "channel", None) and getattr(original_msg, "id", None):
                    await vending_service.set_pending_request_message(interaction.guild.id, platform, int(pid), int(original_msg.channel.id), int(original_msg.id))
            except Exception:
                pass

            try:
                charge_ch = await _resolve_charge_log_channel(interaction.guild)
                log_embed = await _build_charge_log_embed(
                    interaction.guild.id,
                    platform,
                    user_id=int(interaction.user.id),
                    amount=int(amt),
                    depositor=depositor,
                    pid=int(pid),
                    status="pending",
                )
                sent_log = await _send_embed_channel(
                    channel=charge_ch if isinstance(charge_ch, discord.abc.Messageable) else None,
                    embed=log_embed,
                    view=charge_log_view(platform, int(pid)),
                )
                if sent_log and getattr(sent_log, "channel", None) and getattr(sent_log, "id", None):
                    await vending_service.set_pending_request_message(interaction.guild.id, platform, int(pid), int(sent_log.channel.id), int(sent_log.id))
                elif interaction.guild:
                    print(f"[CHARGE_LOG] send_failed guild={interaction.guild.id} platform={platform} pid={pid}")
            except Exception as e:
                try:
                    print(f"[CHARGE_LOG] error guild={interaction.guild.id if interaction.guild else 0} platform={platform} pid={pid} err={e}")
                except Exception:
                    pass

            return
        except Exception:
            try:
                import traceback
                traceback.print_exc()
            except Exception:
                pass
            return await interaction.edit_original_response(embed=error_embed("충전 신청하는데 뭔가 잘못됐어요. 다시 시도해주세요"))

async def _edit_request_message(guild_id: int, platform: str, pending: dict, status: str):
    try:
        pid = int(pending.get("id") or 0)
    except Exception:
        pid = 0
    if pid:
        key = _pending_key(guild_id, platform, pid)
        msg = EPHEMERAL_CHARGE_MSGS.get(key)
        if msg:
            try:
                emb = await _charge_ephemeral_embed(
                    int(guild_id),
                    platform,
                    amount=int(pending.get("amount") or 0),
                    depositor=str(pending.get("depositor_name") or ""),
                    status=str(status),
                )
                await msg.edit(embed=emb)
            except Exception:
                pass
            if status != "pending":
                EPHEMERAL_CHARGE_MSGS.pop(key, None)

    ch_id = pending.get("request_channel_id")
    msg_id = pending.get("request_message_id")
    if not ch_id or not msg_id:
        return
    g = bot.get_guild(int(guild_id))
    if not g:
        return
    ch = g.get_channel(int(ch_id))
    if not isinstance(ch, discord.abc.Messageable):
        return
    try:
        m = await ch.fetch_message(int(msg_id))
    except Exception:
        return
    try:
        emb = await _build_charge_log_embed(
            int(guild_id),
            platform,
            user_id=int(pending.get("user_id") or 0),
            amount=int(pending.get("amount") or 0),
            depositor=str(pending.get("depositor_name") or ""),
            pid=int(pending.get("id") or 0),
            status=str(status),
            staff_id=int(pending["approved_by"]) if pending.get("approved_by") else None,
            staff_name=str(pending.get("approved_by_name") or "") or None,
            staff_at=int(pending["approved_at"]) if pending.get("approved_at") else None,
        )
        await m.edit(embed=emb, view=None)
    except Exception:
        return

async def _auto_approve_charge(guild_id: int, platform: str, pid: int, processed_key: str):
    pending = await vending_service.get_pending_by_id(guild_id, platform, pid)
    if not pending or str(pending.get("status")) != "pending":
        return False
    now = int(time.time())
    if now - int(pending.get("created_at") or 0) > 300:
        return False
    if not await vending_service.claim_pending_charge(guild_id, platform, pid):
        return False
    if not await vending_service.apply_charge_once(guild_id, int(pending["user_id"]), processed_key, int(pending["amount"])):
        await vending_service.release_pending_charge(guild_id, platform, pid)
        return False
    ok = await vending_service.credit_charge(guild_id, int(pending["user_id"]), int(pending["amount"]))
    if not ok or not ok.get("ok"):
        await vending_service.release_pending_charge(guild_id, platform, pid)
        await vending_service.forget_charge_once(guild_id, int(pending["user_id"]), processed_key, int(pending["amount"]))
        return False
    if platform.upper() == "AOS":
        await vending_service.aos_mark_done(guild_id, pid)
    else:
        await vending_service.ios_mark_done(guild_id, pid, 0)
    await _edit_request_message(guild_id, platform, pending, "done")
    return True

async def _handle_charge_approve(interaction: discord.Interaction, platform: str, pid: int):
    if not interaction.guild:
        return
    if not await _can_manage_charge(interaction):
        return await _reply(interaction, embed=error_embed("충전 승인/거절 권한이 없습니다."), ephemeral=True)
    await _ack(interaction, thinking=True)
    pending = await vending_service.get_pending_by_id(interaction.guild.id, platform, pid)
    if not pending or str(pending.get("status")) != "pending":
        return await interaction.followup.send(embed=error_embed("이미 처리된 요청이야"), ephemeral=True)
    now = int(time.time())
    if now - int(pending.get("created_at") or 0) > 300:
        await _edit_request_message(interaction.guild.id, platform, pending, "expired")
        return await interaction.followup.send(embed=error_embed("5분이 지나서 처리할 수 없어"), ephemeral=True)

    if not await vending_service.claim_pending_charge(interaction.guild.id, platform, pid):
        return await interaction.followup.send(embed=error_embed("이미 처리된 요청이야"), ephemeral=True)
    key = f"manual:{platform}:{pid}"
    if not await vending_service.apply_charge_once(interaction.guild.id, int(pending["user_id"]), key, int(pending["amount"])):
        await vending_service.release_pending_charge(interaction.guild.id, platform, pid)
        return await interaction.followup.send(embed=error_embed("이미 처리된 결제키야"), ephemeral=True)
    ok = await vending_service.credit_charge(interaction.guild.id, int(pending["user_id"]), int(pending["amount"]))
    if not ok or not ok.get("ok"):
        await vending_service.release_pending_charge(interaction.guild.id, platform, pid)
        await vending_service.forget_charge_once(interaction.guild.id, int(pending["user_id"]), key, int(pending["amount"]))
        return await interaction.followup.send(embed=error_embed("잔액 반영 실패"), ephemeral=True)
    await vending_service.set_charge_approval(
        interaction.guild.id,
        platform,
        pid,
        actor_id=interaction.user.id,
        actor_name=str(interaction.user),
        approved_at=now,
    )
    pending["approved_by"] = interaction.user.id
    pending["approved_by_name"] = str(interaction.user)
    pending["approved_at"] = now
    if platform.upper() == "AOS":
        await vending_service.aos_mark_done(interaction.guild.id, pid)
    else:
        await vending_service.ios_mark_done(interaction.guild.id, pid, 0)
    await _edit_request_message(interaction.guild.id, platform, pending, "done")
    return await interaction.followup.send(embed=ok_embed("승인 완료"), ephemeral=True)

async def _handle_charge_reject(interaction: discord.Interaction, platform: str, pid: int):
    if not interaction.guild:
        return
    if not await _can_manage_charge(interaction):
        return await _reply(interaction, embed=error_embed("충전 승인/거절 권한이 없습니다."), ephemeral=True)
    await _ack(interaction, thinking=True)
    pending = await vending_service.get_pending_by_id(interaction.guild.id, platform, pid)
    if not pending or str(pending.get("status")) != "pending":
        return await interaction.followup.send(embed=error_embed("이미 처리된 요청이야"), ephemeral=True)
    now = int(time.time())
    if now - int(pending.get("created_at") or 0) > 300:
        await _edit_request_message(interaction.guild.id, platform, pending, "expired")
        return await interaction.followup.send(embed=error_embed("5분이 지나서 처리할 수 없어"), ephemeral=True)
    if platform.upper() == "AOS":
        await vending_service.aos_mark_rejected(interaction.guild.id, pid)
    else:
        await vending_service.ios_mark_rejected(interaction.guild.id, pid)
    await _edit_request_message(interaction.guild.id, platform, pending, "rejected")
    return await interaction.followup.send(embed=ok_embed("거절 완료"), ephemeral=True)

async def _handle_k_charge(interaction: discord.Interaction):
    if not interaction.guild:
        return await _reply(interaction, embed=error_embed("서버에서만 가능해"), ephemeral=True)

    cfg = await vending_service.get_charge_settings(interaction.guild.id)
    cfg = dict(cfg) if cfg else {}
    platforms = _enabled_charge_platforms(cfg)

    if not platforms:
        return await _reply(interaction, embed=error_embed("충전 설정이 없습니다."), ephemeral=True)

    if len(platforms) > 1:
        return await _reply(interaction, 
            view=select_view("k:charge_pick", "계좌 선택", _charge_account_options(platforms, cfg)),
            ephemeral=True,
        )

    platform = platforms[0]
    if platform == "IOS":
        return await _modal(interaction, ChargeRequestModal("IOS"))

    return await _modal(interaction, ChargeRequestModal("AOS"))


async def _handle_k_charge_pick(interaction: discord.Interaction):
    if not interaction.guild:
        return await _reply(interaction, embed=error_embed("서버에서만 가능해"), ephemeral=True)
    picked = str(((interaction.data or {}).get("values") or [""])[0]).upper()
    if picked not in ("AOS", "IOS"):
        return await _reply(interaction, embed=error_embed("선택이 이상해"), ephemeral=True)
    cfg = await vending_service.get_charge_settings(interaction.guild.id)
    cfg = dict(cfg) if cfg else {}
    ready = _enabled_charge_platforms(cfg)
    if picked == "IOS":
        if "IOS" not in ready:
            return await _reply(interaction, embed=error_embed("계좌 2 충전 설정이 비어있거나 완성되지 않았어"), ephemeral=True)
        return await _modal(interaction, ChargeRequestModal("IOS"))
    if "AOS" not in ready:
        return await _reply(interaction, embed=error_embed("계좌 1 충전 설정이 비어있거나 완성되지 않았어"), ephemeral=True)
    return await _modal(interaction, ChargeRequestModal("AOS"))

async def _handle_k_post(interaction: discord.Interaction):
    if not interaction.guild or not interaction.channel:
        return await _reply(interaction, embed=error_embed("서버에서만 가능해"), ephemeral=True)
    if isinstance(interaction.user, discord.Member):
        if not interaction.user.guild_permissions.administrator:
            return await _reply(interaction, embed=error_embed("관리자만 가능해"), ephemeral=True)
    panel = await vending_service.panel(interaction.guild.id)
    panel = dict(panel) if panel else {}
    title = (panel.get("title") or "").strip()
    desc = (panel.get("description") or "").strip()
    image_url = (panel.get("image_url") or None)
    color = int(panel.get("color") or 0)
    view = vending_machine_message(title=title, description=desc, image_url=image_url, color=color)
    await interaction.channel.send(view=view)
    return await _reply(interaction, embed=ok_embed("자판기를 채널에 게시했습니다."), ephemeral=True)

async def _handle_vm_buy(interaction: discord.Interaction, vm_id: int):
    vm = await vending_service.vending_machine(interaction.guild.id, vm_id)
    if not vm:
        return await _reply(interaction, embed=error_embed("자판기 없음"), ephemeral=True)
    cid = int(vm["category_id"])
    prods = await vending_service.products_in_category(interaction.guild.id, cid)
    if not prods:
        return await _reply(interaction, embed=error_embed("제품이 없어"), ephemeral=True)

    vip = await _vip_of(interaction)
    opts = [discord.SelectOption(label=p["name"][:100], value=str(p["id"]), description=vending_service.price_label(int(p["price"]), vip)[:100]) for p in prods[:25]]
    return await _reply(interaction, view=select_view("v:prod", "제품 선택", opts), ephemeral=True)

async def _handle_vm_products(interaction: discord.Interaction, vm_id: int):
    vm = await vending_service.vending_machine(interaction.guild.id, vm_id)
    if not vm:
        return await _reply(interaction, embed=error_embed("자판기 없음"), ephemeral=True)
    cid = int(vm["category_id"])
    prods = await vending_service.products_in_category(interaction.guild.id, cid)
    if not prods:
        return await _reply(interaction, embed=error_embed("제품이 없어"), ephemeral=True)

    vip = await _vip_of(interaction)
    counts = await vending_service.stock_counts(interaction.guild.id, [int(p["id"]) for p in prods])
    lines = []
    for p in prods:
        stock = int(counts.get(int(p["id"]), 0))
        lines.append(f"- **{p['name']}** / {vending_service.price_label(int(p['price']), vip)} / 재고 {stock}개")
    body = "\n".join(lines)
    if len(body) > 3900:
        fp = io.BytesIO(body.encode("utf-8"))
        file = discord.File(fp, filename="products.txt")
        return await _reply(interaction, content="제품 목록", file=file, ephemeral=True)
    return await _reply(interaction, embed=ok_embed(body), ephemeral=True)

async def _handle_vm_charge(interaction: discord.Interaction, vm_id: int):
    cs = await vending_service.get_charge_settings(interaction.guild.id)
    cs = dict(cs) if cs else {}
    platforms = _enabled_charge_platforms(cs)
    label = ", ".join(_charge_account_label(p) for p in platforms) if platforms else "미설정"
    return await _reply(interaction, embed=ok_embed(f"충전 계좌: **{label}**"), ephemeral=True)

async def _handle_vm_info(interaction: discord.Interaction, vm_id: int):
    return await _handle_k_info(interaction)


if __name__ == "__main__":
    main()
