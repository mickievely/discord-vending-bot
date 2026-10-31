from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord

from config import DISCORD_TOKEN, PRODUCT_ADD_WEBHOOK_URL
from db.cache import CHANNELS
from . import http as http_pool
from . import vending_service

KST = timezone(timedelta(hours=9))

_BOT: Any = None
DEFAULT_BUY_COLOR = 0x5865F2
DEFAULT_STOCK_COLOR = 0x57F287
DEFAULT_DM_COLOR = 0x57F287


def set_bot(bot) -> None:
    global _BOT
    _BOT = bot


def spawn(coro) -> None:
    async def _run():
        try:
            await coro
        except Exception:
            pass

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        pass


def get_bot():
    return _BOT


def kst_now_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def kst_from_ts(ts: int | None) -> str:
    if not ts:
        return kst_now_str()
    try:
        return datetime.fromtimestamp(int(ts), KST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return kst_now_str()


def parse_color(value, default: int) -> int:
    if value is None or value == "":
        return int(default)
    try:
        return int(value)
    except Exception:
        raw = str(value).strip()
        if raw.startswith("#"):
            try:
                return int(raw[1:], 16)
            except Exception:
                return int(default)
        return int(default)


def apply_image(embed: discord.Embed, url: Optional[str]) -> None:
    if url and str(url).strip().startswith(("http://", "https://")):
        embed.set_image(url=str(url).strip())


def _stock_action_label(action: str) -> str:
    return "입고" if str(action or "").lower() == "add" else "설정"


def format_template(tmpl: str, mapping: dict[str, str]) -> str:
    out = str(tmpl or "")
    for key, value in mapping.items():
        out = out.replace(key, str(value))
    return out


async def resolve_channel(guild: discord.Guild | None, channel_id: int | None):
    if not channel_id:
        return None
    cid = int(channel_id)
    if guild:
        try:
            ch = guild.get_channel(cid)
            if ch:
                return ch
        except Exception:
            pass
    ok, cached = CHANNELS.peek(cid)
    if ok:
        return cached
    bot = _BOT
    if bot is None:
        return None
    try:
        ch = await bot.fetch_channel(cid)
        CHANNELS.set(cid, ch, ttl=90)
        return ch
    except Exception:
        CHANNELS.set(cid, None, ttl=12)
        return None


async def send_embed(channel, embed: discord.Embed, view=None):
    if not channel or not isinstance(channel, discord.abc.Messageable):
        return None
    try:
        return await channel.send(embed=embed, view=view)
    except Exception:
        return None


async def send_buy_log(
    guild_id: int,
    *,
    user: discord.abc.User,
    category: str,
    product: str,
    qty: int,
    total: int,
):
    logs = await vending_service.get_log_settings(int(guild_id))
    channel_id = logs.get("buy_channel_id")
    if not channel_id:
        return
    bot = _BOT
    guild = bot.get_guild(int(guild_id)) if bot else None
    channel = await resolve_channel(guild, int(channel_id))
    tmpl = str(logs.get("buy_desc_template") or "{유저}님 {카테고리} • {제품} 구매 감사합니다")
    desc = format_template(
        tmpl,
        {
            "{유저}": user.mention,
            "{사용자}": user.mention,
            "{user}": user.mention,
            "{username}": str(user),
            "{카테고리}": category,
            "{카테고리이름}": category,
            "{category}": category,
            "{categoryName}": category,
            "{제품}": product,
            "{상품}": product,
            "{product}": product,
            "{productName}": product,
            "{수량}": str(int(qty)),
            "{qty}": str(int(qty)),
            "{quantity}": str(int(qty)),
            "{총액}": f"{int(total):,}",
            "{total}": f"{int(total):,}",
            "{금액}": f"{int(total):,}",
            "{amount}": f"{int(total):,}",
        },
    )
    title_t = str(logs.get("buy_title_template") or "{카테고리}•{제품}").strip() or "{카테고리}•{제품}"
    title = format_template(
        title_t,
        {
            "{카테고리}": category,
            "{category}": category,
            "{제품}": product,
            "{product}": product,
            "{유저}": user.mention,
            "{user}": user.mention,
        },
    ).strip("•") or "구매 로그"
    from ui.v2_layouts import log_card_layout
    view = log_card_layout(
        title=title[:256],
        description=desc[:3900],
        image_url=str(logs.get("buy_image_url") or "").strip() or None,
        accent_color=parse_color(logs.get("buy_embed_color"), DEFAULT_BUY_COLOR),
    )
    if not channel or not isinstance(channel, discord.abc.Messageable):
        return
    try:
        await channel.send(view=view)
    except Exception:
        emb = discord.Embed(
            title=title[:256],
            description=desc[:4000],
            color=parse_color(logs.get("buy_embed_color"), DEFAULT_BUY_COLOR),
        )
        apply_image(emb, logs.get("buy_image_url"))
        await send_embed(channel, emb)


async def send_stock_log(
    guild_id: int,
    info: dict | None,
    *,
    actor_mention: str = "",
    actor_name: str = "",
    actor_id: int | None = None,
):
    logs = await vending_service.get_log_settings(int(guild_id))
    channel_id = logs.get("stock_channel_id")
    if not channel_id:
        return
    bot = _BOT
    guild = bot.get_guild(int(guild_id)) if bot else None
    channel = await resolve_channel(guild, int(channel_id))
    details = dict(info or {})
    product_id = details.get("product_id")
    if product_id and (not details.get("product_name") or not details.get("category_name")):
        product = await vending_service.product_with_category(int(guild_id), int(product_id))
        product = dict(product) if product else {}
        details.setdefault("product_name", product.get("name") or "상품")
        details.setdefault("category_name", product.get("category_name") or "")
    product_name = str(details.get("product_name") or "상품")
    category_name = str(details.get("category_name") or "")
    action = str(details.get("action") or "add")
    qty = int(details.get("qty") or 0)
    before_count = int(details.get("before_count") or 0)
    after_count = int(details.get("after_count") or 0)
    delta = after_count - before_count
    if str(action).lower() == "add":
        added = qty if qty > 0 else max(delta, 0)
        if added <= 0:
            return
        increased = True
        shown_qty = added
    elif delta > 0:
        increased = True
        shown_qty = delta
    elif delta < 0:
        increased = False
        shown_qty = abs(delta)
    else:
        return
    server_name = str(getattr(guild, "name", "") or "")
    mapping = {
        "{제품}": product_name,
        "{상품}": product_name,
        "{product}": product_name,
        "{카테고리}": category_name,
        "{category}": category_name,
        "{수량}": str(shown_qty),
        "{qty}": str(shown_qty),
        "{이전재고}": str(before_count),
        "{before}": str(before_count),
        "{현재재고}": str(after_count),
        "{after}": str(after_count),
        "{서버}": server_name,
        "{server}": server_name,
        "{유저}": actor_mention or actor_name,
        "{user}": actor_mention or actor_name,
    }
    raw_tmpl = str(logs.get("stock_desc_template") or "").strip()
    if not increased and raw_tmpl in {"", "{제품} >> {수량}개 추가"}:
        raw_tmpl = "{제품} >> {수량}개 감소"
    raw_tmpl = raw_tmpl or "{제품} >> {수량}개 추가"
    ping = increased and _stock_wants_everyone(logs, raw_tmpl)
    body = _strip_everyone_tokens(raw_tmpl)
    desc = format_template(body, mapping).strip() or f"{product_name} >> {shown_qty}개 추가"
    title = format_template(str(logs.get("stock_title_template") or "").strip() or "입고", mapping).strip() or "입고"
    emb = discord.Embed(
        title=title[:256],
        description=desc[:4000],
        color=parse_color(logs.get("stock_embed_color"), DEFAULT_STOCK_COLOR),
    )
    apply_image(emb, logs.get("stock_image_url"))
    if not channel or not isinstance(channel, discord.abc.Messageable):
        return
    content = "@everyone" if ping else None
    mentions = discord.AllowedMentions(everyone=bool(ping), users=False, roles=False, replied_user=False)
    try:
        await channel.send(content=content, embed=emb, allowed_mentions=mentions)
    except Exception as exc:
        if ping:
            print(f"stock everyone ping failed guild={guild_id}: {type(exc).__name__}: {exc}")
        await send_embed(channel, emb)


_EVERYONE_TOKENS = ("@everyone", "@here", "{애브핑}", "{애브}", "{everyone}", "{here}")


def _stock_wants_everyone(logs: dict, template: str) -> bool:
    flag = logs.get("stock_everyone")
    if flag is None:
        enabled = True
    else:
        enabled = int(flag or 0) == 1
    low = str(template or "").lower()
    if any(token.lower() in low for token in _EVERYONE_TOKENS):
        return True
    return enabled


def _strip_everyone_tokens(template: str) -> str:
    out = str(template or "")
    for token in _EVERYONE_TOKENS:
        out = re.sub(re.escape(token), "", out, flags=re.I)
    return out


def schedule_stock_notify(
    guild_id: int,
    info: dict | None,
    *,
    actor_mention: str = "",
    actor_name: str = "",
    actor_id: int | None = None,
    notify_buyers: bool | None = None,
) -> None:
    details = dict(info or {})
    spawn(_notify_stock_change(
        int(guild_id),
        details,
        actor_mention=actor_mention,
        actor_name=actor_name,
        actor_id=actor_id,
        notify_buyers=notify_buyers,
    ))


async def _notify_stock_change(
    guild_id: int,
    info: dict,
    *,
    actor_mention: str = "",
    actor_name: str = "",
    actor_id: int | None = None,
    notify_buyers: bool | None = None,
) -> None:
    await send_stock_log(
        guild_id,
        info,
        actor_mention=actor_mention,
        actor_name=actor_name,
        actor_id=actor_id,
    )
    await send_restock_dms(
        guild_id,
        str(info.get("product_name") or "상품"),
        action=str(info.get("action") or "add"),
        before_count=int(info.get("before_count") or 0),
        after_count=int(info.get("after_count") or 0),
        notify_buyers=notify_buyers,
    )


async def send_restock_dms(
    guild_id: int,
    product_name: str,
    *,
    action: str = "add",
    before_count: int = 0,
    after_count: int = 0,
    notify_buyers: bool | None = None,
):
    if notify_buyers is False:
        return
    if str(action).lower() != "add" and int(after_count) <= int(before_count):
        return
    logs = await vending_service.get_log_settings(int(guild_id))
    if notify_buyers is not True and int(logs.get("restock_dm_enabled") or 0) != 1:
        return
    bot = _BOT
    if bot is None:
        return
    guild = bot.get_guild(int(guild_id))
    server_name = str(getattr(guild, "name", "") or f"서버 {guild_id}")
    tmpl = str(logs.get("restock_dm_template") or "{서버} 입고되었습니다")
    text = format_template(
        tmpl,
        {
            "{서버}": server_name,
            "{server}": server_name,
            "{제품}": product_name,
            "{product}": product_name,
        },
    )
    color = parse_color(logs.get("dm_embed_color"), DEFAULT_DM_COLOR)
    buyers = await vending_service.list_buyer_ids(int(guild_id))
    for uid in buyers:
        try:
            user = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
            if not user:
                continue
            emb = discord.Embed(title="입고 알림", description=text[:4000], color=color)
            apply_image(emb, logs.get("dm_image_url") or logs.get("stock_image_url"))
            await user.send(embed=emb)
        except Exception:
            pass
        await asyncio.sleep(0.7)


def purchase_dm_options(logs: dict) -> dict:
    title = str(logs.get("dm_title") or "구매 완료").strip() or "구매 완료"
    desc = str(logs.get("dm_desc_template") or "").strip()
    return {
        "title": title,
        "description": desc,
        "color": parse_color(logs.get("dm_embed_color"), DEFAULT_DM_COLOR),
        "image_url": str(logs.get("dm_image_url") or "").strip() or None,
    }


async def refresh_charge_log_message(guild_id: int, platform: str, pending: dict, status: str):
    bot = _BOT
    if bot is None:
        return
    ch_id = pending.get("request_channel_id")
    msg_id = pending.get("request_message_id")
    if not ch_id or not msg_id:
        return
    guild = bot.get_guild(int(guild_id))
    channel = await resolve_channel(guild, int(ch_id))
    if not isinstance(channel, discord.abc.Messageable):
        return
    try:
        status_l = str(status or "").lower()
        title = "💳 충전 요청"
        color = 0x5865F2
        if status_l == "done":
            title, color = "✅ 충전 완료", 0x57F287
        elif status_l == "rejected":
            title, color = "❌ 충전 거절", 0xED4245
        elif status_l == "expired":
            title, color = "⌛ 충전 요청 만료", 0xFEE75C
        label = "계좌 2" if str(platform).upper() == "IOS" else "계좌 1"
        user_id = int(pending.get("user_id") or 0)
        emb = discord.Embed(title=title, color=color)
        emb.add_field(name="유저", value=f"<@{user_id}>" if user_id else "-", inline=True)
        emb.add_field(name="입금자명", value=f"`{(pending.get('depositor_name') or '-').strip()}`", inline=True)
        emb.add_field(name="금액", value=f"`{int(pending.get('amount') or 0):,}원`", inline=True)
        emb.add_field(name="계좌", value=f"`{label}`", inline=True)
        staff_id = pending.get("approved_by")
        staff_name = pending.get("approved_by_name")
        if staff_id or staff_name:
            mention = f"<@{int(staff_id)}>" if staff_id else str(staff_name)
            emb.add_field(name="처리 스태프", value=f"{mention}\n`{staff_name or '-'}` · ID `{staff_id or '-'}`", inline=False)
            emb.add_field(name="처리 시각", value=f"`{kst_from_ts(pending.get('approved_at'))}`", inline=True)
        emb.timestamp = discord.utils.utcnow()
        msg = await channel.fetch_message(int(msg_id))
        await msg.edit(embed=emb, view=None)
    except Exception:
        return


async def send_login_logs(username: str, ip: str, ok: bool):
    bot = _BOT
    if bot is None:
        return
    status = "성공" if ok else "실패"
    color = 0x57F287 if ok else 0xED4245
    for guild in getattr(bot, "guilds", []) or []:
        try:
            logs = await vending_service.get_log_settings(int(guild.id))
            channel_id = logs.get("login_log_channel_id")
            if not channel_id:
                continue
            channel = await resolve_channel(guild, int(channel_id))
            emb = discord.Embed(title="웹패널 로그인", color=color)
            emb.add_field(name="계정", value=f"`{username}`", inline=True)
            emb.add_field(name="결과", value=status, inline=True)
            emb.add_field(name="IP", value=f"`{ip}`", inline=False)
            emb.add_field(name="시각", value=f"`{kst_now_str()}`", inline=True)
            emb.timestamp = discord.utils.utcnow()
            await send_embed(channel, emb)
        except Exception:
            continue


DISCORD_API = "https://discord.com/api/v10"
SNOWFLAKE_RE = re.compile(r"\d{15,22}")
ANNOUNCE_DM_LIMIT = 400


def bot_auth_header() -> str:
    if not DISCORD_TOKEN:
        return ""
    return DISCORD_TOKEN if DISCORD_TOKEN.lower().startswith("bot ") else f"Bot {DISCORD_TOKEN}"


async def product_add_webhook(guild_id: int, category_id: int, name: str) -> None:
    url = (PRODUCT_ADD_WEBHOOK_URL or "").strip()
    if not url:
        return
    try:
        cats = await vending_service.list_categories(guild_id)
        cat_name = next(
            (str(c["name"]) for c in (cats or []) if int(c["id"]) == int(category_id)),
            "",
        )
        label = (name or "").strip()
        text = f"{cat_name} * {label}을 생성 했습니다" if cat_name else f"{label}을 생성 했습니다"
        session = await http_pool.session()
        wh = discord.Webhook.from_url(url, session=session)
        await wh.send(content=text)
    except Exception:
        pass


def parse_snowflakes(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = " ".join(str(x) for x in value)
    else:
        raw = str(value)
    out: list[int] = []
    seen: set[int] = set()
    for hit in SNOWFLAKE_RE.findall(raw):
        try:
            uid = int(hit)
        except Exception:
            continue
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def embed_to_dict(embed: discord.Embed) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if embed.title:
        data["title"] = embed.title[:256]
    if embed.description:
        data["description"] = embed.description[:4096]
    if embed.color:
        data["color"] = int(embed.color.value)
    if embed.image and embed.image.url:
        data["image"] = {"url": embed.image.url}
    return data


def build_announce_embed(*, title: str, description: str, color: Any, image_url: Optional[str] = None) -> discord.Embed:
    emb = discord.Embed(
        title=(title or "공지")[:256],
        description=(description or "")[:4000],
        color=parse_color(color, 0x5865F2),
    )
    apply_image(emb, image_url)
    emb.timestamp = discord.utils.utcnow()
    return emb


async def rest_json(method: str, path: str, payload: dict | None = None) -> tuple[Any, Optional[str], int]:
    auth = bot_auth_header()
    if not auth:
        return None, "DISCORD_TOKEN이 없습니다.", 0
    try:
        session = await http_pool.session()
        async with session.request(
            method.upper(),
            f"{DISCORD_API}{path}",
            json=payload,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        ) as resp:
            text = await resp.text()
            data = None
            if text:
                try:
                    data = json.loads(text)
                except Exception:
                    data = text
            if 200 <= resp.status < 300:
                return data, None, resp.status
            return data, f"Discord API {resp.status}", resp.status
    except Exception as exc:
        return None, str(exc), 0


async def rest_send_embed(channel_id: int, embed: discord.Embed) -> tuple[bool, Optional[str]]:
    _, err, _ = await rest_json("POST", f"/channels/{int(channel_id)}/messages", {"embeds": [embed_to_dict(embed)]})
    return err is None, err


async def rest_dm_embed(user_id: int, embed: discord.Embed) -> tuple[bool, Optional[str]]:
    data, err, _ = await rest_json("POST", "/users/@me/channels", {"recipient_id": str(int(user_id))})
    if err or not isinstance(data, dict) or not data.get("id"):
        return False, err or "DM 채널을 만들지 못했습니다."
    return await rest_send_embed(int(data["id"]), embed)


async def fetch_role_member_ids(guild_id: int, role_ids: list[int]) -> tuple[set[int], Optional[str]]:
    wanted = {int(x) for x in role_ids if x}
    if not wanted:
        return set(), None
    found: set[int] = set()
    guild = None
    bot = _BOT
    if bot is not None:
        try:
            guild = bot.get_guild(int(guild_id))
        except Exception:
            guild = None
    if guild is not None:
        for rid in wanted:
            role = guild.get_role(int(rid))
            if role is None:
                continue
            for member in getattr(role, "members", []) or []:
                try:
                    found.add(int(member.id))
                except Exception:
                    pass
        if found:
            return found, None
    after = 0
    pages = 0
    while pages < 8:
        path = f"/guilds/{int(guild_id)}/members?limit=1000"
        if after:
            path += f"&after={after}"
        data, err, status = await rest_json("GET", path)
        if err:
            if status == 403:
                return found, "역할 멤버를 불러오지 못했습니다. 봇에 Server Members Intent가 필요합니다."
            return found, err
        if not isinstance(data, list) or not data:
            break
        pages += 1
        for row in data:
            user = row.get("user") if isinstance(row, dict) else None
            if not isinstance(user, dict):
                continue
            try:
                uid = int(user.get("id"))
            except Exception:
                continue
            roles = {int(x) for x in (row.get("roles") or []) if str(x).isdigit()}
            if roles & wanted:
                found.add(uid)
            after = uid
        if len(data) < 1000:
            break
    return found, None


async def collect_announce_user_ids(
    guild_id: int,
    *,
    user_ids: list[int],
    role_ids: list[int],
    buyers: bool,
) -> tuple[list[int], Optional[str]]:
    targets: set[int] = set(int(x) for x in user_ids if x)
    warn = None
    if role_ids:
        role_members, role_err = await fetch_role_member_ids(int(guild_id), role_ids)
        targets.update(role_members)
        warn = role_err
    if buyers:
        try:
            targets.update(await vending_service.list_buyer_ids(int(guild_id)))
        except Exception:
            pass
    return list(targets)[:ANNOUNCE_DM_LIMIT], warn


async def send_announce(
    guild_id: int,
    *,
    title: str,
    description: str,
    color: Any = None,
    image_url: Optional[str] = None,
    channel_id: Optional[int] = None,
    user_ids: list[int] | None = None,
    role_ids: list[int] | None = None,
    buyers: bool = False,
) -> dict[str, Any]:
    embed = build_announce_embed(title=title, description=description, color=color, image_url=image_url)
    channel_ok = False
    channel_error = None
    if channel_id:
        bot = _BOT
        guild = bot.get_guild(int(guild_id)) if bot else None
        channel = await resolve_channel(guild, int(channel_id))
        sent = await send_embed(channel, embed)
        if sent:
            channel_ok = True
        else:
            ok, err = await rest_send_embed(int(channel_id), embed)
            channel_ok = ok
            channel_error = None if ok else (err or "채널에 보내지 못했습니다.")
    dm_ids, role_warn = await collect_announce_user_ids(
        int(guild_id),
        user_ids=user_ids or [],
        role_ids=role_ids or [],
        buyers=buyers,
    )
    dm_ok = 0
    dm_fail = 0
    bot = _BOT
    for uid in dm_ids:
        sent = False
        if bot is not None:
            try:
                user = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
                if user:
                    await user.send(embed=embed)
                    sent = True
            except Exception:
                sent = False
        if not sent:
            ok, _ = await rest_dm_embed(int(uid), embed)
            sent = ok
        if sent:
            dm_ok += 1
        else:
            dm_fail += 1
        await asyncio.sleep(0.55)
    return {
        "ok": bool(channel_ok or dm_ok),
        "channelOk": channel_ok,
        "channelError": channel_error,
        "dmOk": dm_ok,
        "dmFail": dm_fail,
        "dmTotal": len(dm_ids),
        "roleWarning": role_warn,
    }
