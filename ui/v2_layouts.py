from __future__ import annotations

from typing import Optional
import discord


class RootPanelLayout(discord.ui.LayoutView):
    message: Optional[discord.Message] = None

    def __init__(self, user: discord.abc.User, *, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.user = user

        opts = [
            discord.SelectOption(label="서버 데이터 삭제", value="srv_del", description="선택한 서버의 자판기 데이터를 삭제"),
        ]

        row = discord.ui.ActionRow()
        row.add_item(
            discord.ui.Select(
                custom_id="r:menu",
                placeholder="작업 선택",
                min_values=1,
                max_values=1,
                options=opts,
            )
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay("## 개인용 자판기 관리자 패널"),
            discord.ui.TextDisplay(f"{user.mention} 관리 작업을 선택해주세요."),
            discord.ui.Separator(),
            row,
            accent_color=discord.Color.blurple(),
        )
        self.add_item(container)


class VendingPanelLayout(discord.ui.LayoutView):
    message: Optional[discord.Message] = None

    def __init__(
        self,
        *,
        title: str,
        description: str,
        color: int,
        timeout: Optional[float] = None,
    ):
        super().__init__(timeout=timeout)

        admin_opts = [
            discord.SelectOption(label="패널 설정", value="panel_set", description="자판기 임베드(제목/설명/이미지) 수정"),
            discord.SelectOption(label="충전 설정", value="charge_cfg", description="AOS/IOS 선택 + 토큰"),
            discord.SelectOption(label="수충권한", value="charge_role", description="수동충전 역할 설정"),
            discord.SelectOption(label="로그 설정", value="log_cfg", description="구매/충전/후기/입고 로그 설정"),
            discord.SelectOption(label="카테고리 추가", value="cat_add", description="카테고리 만들기"),
            discord.SelectOption(label="카테고리 삭제", value="cat_del", description="카테고리 삭제"),
            discord.SelectOption(label="카테고리 목록", value="cat_list", description="카테고리 목록"),
            discord.SelectOption(label="제품 추가", value="prod_add", description="제품 만들기"),
            discord.SelectOption(label="제품 삭제", value="prod_del", description="제품 삭제"),
            discord.SelectOption(label="제품 목록", value="prod_list", description="제품 목록"),
            discord.SelectOption(label="제품 설정", value="prod_cfg", description="재고 확인/추가/설정"),
        ]

        row = discord.ui.ActionRow()
        row.add_item(
            discord.ui.Select(
                custom_id="v:admin",
                placeholder="관리 메뉴",
                min_values=1,
                max_values=1,
                options=admin_opts[:25],
            )
        )

        title_text = (title or "").strip()
        desc_text = (description or "").strip()
        color_text = f"색상: #{int(color):06X}" if color else "색상: 기본"

        items = []
        if title_text:
            items.append(discord.ui.TextDisplay(f"## {title_text}"))
        if desc_text:
            items.append(discord.ui.TextDisplay(desc_text))
        items.extend([
            discord.ui.TextDisplay(color_text),
            discord.ui.Separator(),
            row,
        ])

        container = discord.ui.Container(
            *items,
            accent_color=discord.Color(int(color) if color else 0x5865F2),
        )
        self.add_item(container)


def vending_machine_message(*, title: str, description: str, image_url: Optional[str], color: int, vm_id: Optional[int] = None, vm_name: Optional[str] = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)

    title_text = (title or '').strip()
    desc_text = (description or '').strip()
    header = f'## {title_text}' if title_text else ''
    if title_text and vm_name:
        header = f'## {title_text} ({vm_name})'

    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label='구매', style=discord.ButtonStyle.secondary, custom_id='k:buy'))
    row.add_item(discord.ui.Button(label='제품', style=discord.ButtonStyle.secondary, custom_id='k:products'))
    row.add_item(discord.ui.Button(label='충전', style=discord.ButtonStyle.secondary, custom_id='k:charge'))
    row.add_item(discord.ui.Button(label='정보', style=discord.ButtonStyle.secondary, custom_id='k:info'))

    comps = []
    if header:
        comps.append(discord.ui.TextDisplay(header))
    if desc_text:
        comps.append(discord.ui.TextDisplay(desc_text))

    if image_url and hasattr(discord.ui, 'MediaGallery'):
        g = discord.ui.MediaGallery()
        try:
            g.add_item(str(image_url))
        except TypeError:
            g.add_item(media=str(image_url))
        comps.append(g)

    if comps:
        comps.append(discord.ui.Separator())
    comps.append(row)

    container = discord.ui.Container(
        *comps,
        accent_color=discord.Color(int(color) if color else 0x5865F2),
    )
    view.add_item(container)
    return view


def select_layout(
    *,
    title: str,
    description: str,
    custom_id: str,
    placeholder: str,
    options: list[discord.SelectOption],
    timeout: float = 300.0,
    accent_color: Optional[int] = None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=timeout)

    row = discord.ui.ActionRow()
    row.add_item(
        discord.ui.Select(
            custom_id=str(custom_id),
            placeholder=str(placeholder),
        min_values=1,
        max_values=1,
        options=(options or [])[:25],
        )
    )

    container = discord.ui.Container(
        discord.ui.TextDisplay(f"## {title}"),
        discord.ui.TextDisplay((description or "").strip() or "선택해주세요."),
        discord.ui.Separator(),
        row,
        accent_color=discord.Color(int(accent_color) if accent_color else 0x5865F2),
    )
    view.add_item(container)
    return view


def _bar(pct: int, width: int = 10) -> str:
    n = max(0, min(100, int(pct or 0)))
    filled = round(n * width / 100)
    return "█" * filled + "░" * (width - filled)


def _vip_next(tiers: list[dict], spent: int) -> tuple[dict | None, dict | None]:
    rows = sorted(
        [t for t in (tiers or []) if int(t.get("unlockSpent") or 0) > 0],
        key=lambda t: (int(t.get("unlockSpent") or 0), int(t.get("position") or 0), int(t.get("id") or 0)),
    )
    prev = None
    nxt = None
    for t in rows:
        if int(t.get("unlockSpent") or 0) <= int(spent or 0):
            prev = t
        elif nxt is None:
            nxt = t
            break
    return prev, nxt


def _vip_block(vip: dict | None) -> list:
    if not vip or not vip.get("name"):
        return [discord.ui.TextDisplay("등급이 아직 없습니다. 구매하면 자동으로 열려요.")]
    bits = []
    buy = int(vip.get("purchaseDiscountPct") or vip.get("discountPct") or 0)
    charge = int(vip.get("chargeBonusPct") or 0)
    if buy:
        bits.append(f"구매 -{buy}%")
    if charge:
        bits.append(f"충전 +{charge}%")
    title = f"### {(vip.get('emoji') or '').strip()} {vip.get('name')}".strip()
    perks = " · ".join(bits) if bits else "혜택 없음"
    return [discord.ui.TextDisplay(title), discord.ui.TextDisplay(perks)]


def my_info_layout(
    *,
    mention: str,
    balance: int,
    spent: int,
    orders: int,
    vip: dict | None,
    tiers: list[dict] | None,
    user_id: int,
    accent_color: Optional[int] = None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    prev, nxt = _vip_next(tiers or [], int(spent or 0))
    color = int((vip or {}).get("color") or 0) if vip else 0
    items = [
        discord.ui.TextDisplay("## 내 정보"),
        discord.ui.TextDisplay(str(mention)),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"잔액 **{int(balance):,}원**\n누적 구매 **{int(spent):,}원** · {int(orders):,}건"),
        discord.ui.Separator(),
        *_vip_block(vip),
    ]
    if nxt:
        need = max(0, int(nxt.get("unlockSpent") or 0) - int(spent or 0))
        floor = int((prev or {}).get("unlockSpent") or 0)
        span = max(1, int(nxt.get("unlockSpent") or 0) - floor)
        pct = max(0, min(100, int((int(spent or 0) - floor) * 100 / span)))
        items.append(discord.ui.Separator())
        items.append(discord.ui.TextDisplay(
            f"다음 등급 **{nxt.get('name')}** 까지 **{need:,}원**\n`{_bar(pct)}` {pct}%"
        ))
    elif vip:
        items.append(discord.ui.Separator())
        items.append(discord.ui.TextDisplay("다음 등급이 없습니다. 최고 등급입니다."))
    row = discord.ui.ActionRow()
    uid = int(user_id)
    row.add_item(discord.ui.Button(label="구매 내역", style=discord.ButtonStyle.secondary, custom_id=f"i:orders:{uid}"))
    row.add_item(discord.ui.Button(label="충전 내역", style=discord.ButtonStyle.secondary, custom_id=f"i:charges:{uid}"))
    items.extend([discord.ui.Separator(), row])
    view.add_item(discord.ui.Container(*items, accent_color=discord.Color(int(color or accent_color or 0x5865F2))))
    return view


def my_info_history_layout(
    *,
    title: str,
    lines: list[str],
    user_id: int,
    accent_color: Optional[int] = None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    body = "\n".join(str(x) for x in (lines or []) if str(x).strip()) or "내역이 없습니다."
    if len(body) > 3800:
        body = body[:3800] + "…"
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="내 정보", style=discord.ButtonStyle.secondary, custom_id=f"i:home:{int(user_id)}"))
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(f"## {title}"),
        discord.ui.TextDisplay(body),
        discord.ui.Separator(),
        row,
        accent_color=discord.Color(int(accent_color) if accent_color else 0x5865F2),
    ))
    return view


def list_layout(*, title: str, lines: list[str], accent_color: Optional[int] = None, max_lines: int = 45) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    lines = [str(x) for x in (lines or []) if str(x).strip()]
    hidden = 0
    if len(lines) > int(max_lines):
        hidden = len(lines) - int(max_lines)
        lines = lines[: int(max_lines)]
    body = '\n'.join(lines)
    if hidden > 0:
        body += f'\n…외 {hidden}개'
    if len(body) > 3800:
        body = body[:3800] + '…'
    container = discord.ui.Container(
        discord.ui.TextDisplay(f'## {title}'),
        discord.ui.TextDisplay(f'```\n{body}\n```' if body else '비어 있습니다.'),
        accent_color=discord.Color(int(accent_color) if accent_color else 0x5865F2),
    )
    view.add_item(container)
    return view


def toast_layout(
    *,
    title: str,
    description: str,
    accent_color: Optional[int] = None,
    timeout: float = 20.0,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=timeout)
    container = discord.ui.Container(
        discord.ui.TextDisplay(f"## {title}"),
        discord.ui.TextDisplay((description or "").strip() or ""),
        accent_color=discord.Color(int(accent_color) if accent_color else 0x5865F2),
    )
    view.add_item(container)
    return view


def ok_toast(text: str) -> discord.ui.LayoutView:
    return toast_layout(title="완료", description=text, accent_color=0x57F287)


def error_toast(text: str) -> discord.ui.LayoutView:
    return toast_layout(title="오류", description=text, accent_color=0xED4245)


def log_config_pick_layout() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)

    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="구매 로그", style=discord.ButtonStyle.secondary, custom_id="a:log_pick:buy"))
    row.add_item(discord.ui.Button(label="충전 로그", style=discord.ButtonStyle.secondary, custom_id="a:log_pick:charge"))
    row.add_item(discord.ui.Button(label="후기 로그", style=discord.ButtonStyle.secondary, custom_id="a:log_pick:review"))
    row.add_item(discord.ui.Button(label="입고 로그", style=discord.ButtonStyle.secondary, custom_id="a:log_pick:stock"))

    container = discord.ui.Container(
        discord.ui.TextDisplay("## 로그 설정"),
        discord.ui.TextDisplay("설정할 로그 종류를 선택해주세요."),
        discord.ui.Separator(),
        row,
        accent_color=discord.Color.blurple(),
    )
    view.add_item(container)
    return view


def charge_role_select_layout(current_role_id: Optional[int] = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)

    row = discord.ui.ActionRow()
    row.add_item(
        discord.ui.RoleSelect(
            custom_id="a:charge_role",
            placeholder="수동충전 역할 선택",
            min_values=1,
            max_values=1,
        )
    )

    clear_row = discord.ui.ActionRow()
    clear_row.add_item(discord.ui.Button(label="권한 해제", style=discord.ButtonStyle.secondary, custom_id="a:charge_role_clear"))

    current = f"<@&{int(current_role_id)}>" if current_role_id else "현재 설정된 역할이 없습니다. 설정 전에는 관리자만 수동충전할 수 있습니다."
    container = discord.ui.Container(
        discord.ui.TextDisplay("## 수충권한"),
        discord.ui.TextDisplay(f"현재 역할: {current}"),
        discord.ui.TextDisplay("선택한 역할은 /수동충전으로 유저 잔액을 충전할 수 있습니다. 충전로그 승인은 관리자만 가능합니다."),
        discord.ui.Separator(),
        row,
        clear_row,
        accent_color=discord.Color.blurple(),
    )
    view.add_item(container)
    return view


def product_detail_layout(*, name: str, price: int, description: Optional[str], stock: int, product_id: int, accent_color: Optional[int] = None, sale_price: Optional[int] = None, vip_name: Optional[str] = None, discount_pct: int = 0) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    body = (description or "").strip()
    if body and len(body) > 1200:
        body = body[:1200] + "…"
    if sale_price is not None and int(sale_price) != int(price) and int(discount_pct or 0) > 0:
        info = f"가격: {int(price):,}원 → **{int(sale_price):,}원** ({vip_name or 'VIP'} -{int(discount_pct)}%)\n재고: {int(stock)}"
    else:
        info = f"가격: {int(price):,}원\n재고: {int(stock)}"

    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="구매하기", style=discord.ButtonStyle.secondary, custom_id=f"v:buy:{int(product_id)}"))

    items = [
        discord.ui.TextDisplay(f"## {name}"),
        discord.ui.TextDisplay(info),
    ]
    if body:
        items.append(discord.ui.Separator())
        items.append(discord.ui.TextDisplay(body))
    items.append(discord.ui.Separator())
    items.append(row)

    container = discord.ui.Container(
        *items,
        accent_color=discord.Color(int(accent_color) if accent_color else 0x5865F2),
    )
    view.add_item(container)
    return view


def product_config_layout(*, name: str, price: int, stock: int, product_id: int, accent_color: Optional[int] = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    info = f"**{name}**\n가격: {int(price):,}원\n재고: {int(stock)}"

    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="재고 확인", style=discord.ButtonStyle.secondary, custom_id=f"a:prod_cfg:check:{int(product_id)}"))
    row.add_item(discord.ui.Button(label="재고 추가", style=discord.ButtonStyle.secondary, custom_id=f"a:prod_cfg:add:{int(product_id)}"))
    row.add_item(discord.ui.Button(label="재고 설정", style=discord.ButtonStyle.secondary, custom_id=f"a:prod_cfg:set:{int(product_id)}"))

    container = discord.ui.Container(
        discord.ui.TextDisplay("## 제품 설정"),
        discord.ui.TextDisplay(info),
        discord.ui.Separator(),
        row,
        accent_color=discord.Color(int(accent_color) if accent_color else 0x5865F2),
    )
    view.add_item(container)
    return view


def _accent(color: Optional[int], default: int = 0x57F287) -> discord.Color:
    try:
        value = default if color is None else int(color)
    except Exception:
        value = default
    return discord.Color(max(0, min(value, 0xFFFFFF)))


def _media(image_url: Optional[str]):
    if not image_url or not hasattr(discord.ui, "MediaGallery"):
        return None
    g = discord.ui.MediaGallery()
    try:
        g.add_item(str(image_url))
    except TypeError:
        g.add_item(media=str(image_url))
    return g


def log_card_layout(
    *,
    title: str,
    description: str,
    image_url: Optional[str] = None,
    accent_color: Optional[int] = None,
    timeout: Optional[float] = None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=timeout)
    items = [discord.ui.TextDisplay(f"## {(title or '로그').strip() or '로그'}")]
    body = (description or "").strip()
    if body:
        items.append(discord.ui.TextDisplay(body[:3900]))
    media = _media(image_url)
    if media:
        items.append(media)
    view.add_item(discord.ui.Container(*items, accent_color=_accent(accent_color, 0x5865F2)))
    return view


def purchase_complete_layout(
    *,
    product_name: str,
    delivered: str,
    accent_color: Optional[int] = None,
    review_custom_id: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    dn = (delivered or "").strip()
    if dn and len(dn) > 3500:
        dn = dn[:3500] + "…"
    body = "지급 내용이 없습니다." if not dn else f"```\n{dn}\n```"
    heading = (title or "구매 완료").strip() or "구매 완료"

    items = [
        discord.ui.TextDisplay(f"## {heading}"),
        discord.ui.TextDisplay(f"상품: **{product_name}**"),
    ]
    if description:
        items.append(discord.ui.TextDisplay(str(description)[:1800]))
    items.extend([
        discord.ui.Separator(),
        discord.ui.TextDisplay(body),
    ])
    media = _media(image_url)
    if media:
        items.append(media)

    if review_custom_id:
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="후기 작성하기", style=discord.ButtonStyle.secondary, custom_id=str(review_custom_id)))
        items.extend([discord.ui.Separator(), row])

    view.add_item(discord.ui.Container(*items, accent_color=_accent(accent_color, 0x57F287)))
    return view
