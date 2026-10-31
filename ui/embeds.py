from __future__ import annotations
from typing import Optional
from datetime import datetime
import discord
from config import EMBED_COLOR_DEFAULT

def panel_embed(title: Optional[str], description: Optional[str], color: Optional[int], image_url: Optional[str]):
    e = discord.Embed(
        title=title or None,
        description=description or None,
        color=color if isinstance(color, int) and color >= 0 else EMBED_COLOR_DEFAULT
    )
    if image_url:
        e.set_image(url=image_url)
    return e

def info_embed(balance: int):
    e = discord.Embed(title="내 정보", color=EMBED_COLOR_DEFAULT)
    e.add_field(name="잔액", value=f"{balance:,}원", inline=False)
    return e

def error_embed(msg: str):
    return discord.Embed(title="오류", description=msg, color=0xE74C3C)

def ok_embed(msg: str):
    return discord.Embed(title="완료", description=msg, color=0x2ECC71)

def product_embed(name: str, price: int, desc: Optional[str], stock: int):
    e = discord.Embed(title=name, description=desc or "", color=EMBED_COLOR_DEFAULT)
    e.add_field(name="가격", value=f"{price:,}원", inline=True)
    e.add_field(name="재고", value=str(stock), inline=True)
    return e

def purchase_embed(name: str, qty: int, total: int, balance: int, delivered: str):
    e = discord.Embed(title="구매 완료", color=0x2ECC71)
    e.add_field(name="상품", value=name, inline=True)
    e.add_field(name="수량", value=str(qty), inline=True)
    e.add_field(name="결제", value=f"{total:,}원", inline=True)
    e.add_field(name="잔액", value=f"{balance:,}원", inline=False)
    if delivered:
        e.add_field(name="지급", value=f"```{delivered[:1800]}```", inline=False)
    return e

def charge_embed(account: dict, amount: int, depositor: str, seconds_left: Optional[int]):
    e = discord.Embed(title="충전 요청", color=EMBED_COLOR_DEFAULT)
    e.add_field(name="금액", value=f"{amount:,}원", inline=True)
    e.add_field(name="입금자명", value=depositor, inline=True)
    if account and account.get("ok"):
        e.add_field(name="은행", value=account.get("bank_name") or "-", inline=True)
        e.add_field(name="계좌", value=account.get("account_number") or "-", inline=True)
        e.add_field(name="예금주", value=account.get("account_holder") or "-", inline=True)
    if seconds_left is not None:
        e.add_field(name="대기시간", value=f"{seconds_left}초", inline=False)
    e.set_footer(text="입금 후 관리자가 승인하면 잔액이 반영돼")
    return e

def user_stats_embed(title: str, user: discord.abc.User, st: dict):
    e = discord.Embed(title=title, color=EMBED_COLOR_DEFAULT)
    e.add_field(name="유저", value=user.mention, inline=False)
    e.add_field(name="잔액", value=f"{int(st.get('balance',0)):,}원", inline=True)
    vip = st.get("vip") or {}
    if vip.get("name"):
        bits = []
        buy = int(vip.get("purchaseDiscountPct") or vip.get("discountPct") or 0)
        charge = int(vip.get("chargeBonusPct") or 0)
        if buy:
            bits.append(f"구매 -{buy}%")
        if charge:
            bits.append(f"충전 +{charge}%")
        e.add_field(name="VIP", value=f"{vip.get('emoji') or ''} {vip.get('name')} {' · '.join(bits)}".strip(), inline=True)
    e.add_field(name="구매횟수", value=str(int(st.get('orders',0))), inline=True)
    e.add_field(name="구매수량", value=str(int(st.get('items',0))), inline=True)
    e.add_field(name="총 사용", value=f"{int(st.get('spent',0)):,}원", inline=True)
    last_at = st.get("last_at")
    if last_at:
        dt = datetime.fromtimestamp(int(last_at))
        e.add_field(name="마지막 구매", value=dt.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    return e

def charge_result_embed(user: discord.abc.User, before: int, after: int, delta: int, reason: Optional[str]):
    e = discord.Embed(title="수동충전", color=0x2ECC71)
    e.add_field(name="대상", value=user.mention, inline=False)
    e.add_field(name="변경", value=f"{delta:+,}원", inline=True)
    e.add_field(name="이전", value=f"{int(before):,}원", inline=True)
    e.add_field(name="이후", value=f"{int(after):,}원", inline=True)
    if reason:
        e.add_field(name="사유", value=str(reason)[:1024], inline=False)
    return e
