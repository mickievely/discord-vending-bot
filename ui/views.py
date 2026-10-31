from __future__ import annotations
import discord
from ui.v2_layouts import select_layout


def category_view(categories: list[dict]):
    opts = [discord.SelectOption(label=c["name"], value=str(c["id"])) for c in categories[:25]]
    return select_layout(
        title="카테고리",
        description="카테고리를 선택해주세요.",
        custom_id="v:cat",
        placeholder="카테고리 선택",
        options=opts,
        timeout=300,
    )


def product_view(products: list[dict]):
    opts = []
    for p in products[:25]:
        label = str(p["name"])[:100]
        desc = str(p.get("price_label") or f"{int(p['price']):,}원")[:100]
        opts.append(discord.SelectOption(label=label, value=str(p["id"]), description=desc))
    return select_layout(
        title="상품",
        description="상품을 선택해주세요.",
        custom_id="v:prod",
        placeholder="상품 선택",
        options=opts,
        timeout=300,
    )


def purchase_dual_select_view(categories: list[dict], products: list[dict] | None = None, selected_category_id: int | None = None):
    view = discord.ui.LayoutView(timeout=300)

    cat_opts = []
    for c in categories[:25]:
        opt = discord.SelectOption(label=str(c["name"])[:100], value=str(c["id"]))
        if selected_category_id is not None and int(c["id"]) == int(selected_category_id):
            opt.default = True
        cat_opts.append(opt)

    prod_opts = []
    for p in (products or [])[:25]:
        price_text = str(p.get("price_label") or f"{int(p['price']):,}원")
        stock = p.get("stock")
        desc = price_text if stock is None else f"{price_text} ・ 재고 {int(stock)}개"
        prod_opts.append(
            discord.SelectOption(
                label=str(p["name"])[:100],
                value=str(p["id"]),
                description=desc[:100],
            )
        )

    row1 = discord.ui.ActionRow()
    row1.add_item(
        discord.ui.Select(
            custom_id="k:buy_cat",
            placeholder="카테고리 선택",
            min_values=1,
            max_values=1,
            options=(cat_opts or [discord.SelectOption(label="카테고리 없음", value="0")])[:25],
            disabled=not bool(cat_opts),
        )
    )

    row2 = discord.ui.ActionRow()
    row2.add_item(
        discord.ui.Select(
            custom_id="k:buy_prod",
            placeholder="제품 선택",
            min_values=1,
            max_values=1,
            options=(prod_opts or [discord.SelectOption(label="제품 없음", value="0")])[:25],
            disabled=not bool(prod_opts),
        )
    )

    container = discord.ui.Container(
        discord.ui.TextDisplay("## 구매"),
        discord.ui.TextDisplay("카테고리를 선택한 뒤 제품을 선택해주세요."),
        discord.ui.Separator(),
        row1,
        row2,
        accent_color=discord.Color.blurple(),
    )
    view.add_item(container)
    return view


def buy_view(product_id: int):
    view = discord.ui.LayoutView(timeout=300)
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="구매", style=discord.ButtonStyle.secondary, custom_id=f"v:buy:{int(product_id)}"))
    container = discord.ui.Container(
        discord.ui.TextDisplay("## 구매"),
        discord.ui.TextDisplay("구매를 진행하시겠어요?"),
        discord.ui.Separator(),
        row,
        accent_color=discord.Color.blurple(),
    )
    view.add_item(container)
    return view


def charge_check_view():
    view = discord.ui.LayoutView(timeout=300)
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="상태 확인", style=discord.ButtonStyle.secondary, custom_id="v:charge_check"))
    container = discord.ui.Container(
        discord.ui.TextDisplay("## 충전"),
        discord.ui.TextDisplay("충전 상태를 확인하시겠어요?"),
        discord.ui.Separator(),
        row,
        accent_color=discord.Color.blurple(),
    )
    view.add_item(container)
    return view


def vending_panel_view(categories: list[dict]):
    view = discord.ui.LayoutView(timeout=300)
    cat_opts = [discord.SelectOption(label=c["name"], value=str(c["id"])) for c in categories[:25]]
    admin_opts = [
        discord.SelectOption(label="패널 설정", value="panel_set", description="자판기 임베드 설정"),
        discord.SelectOption(label="충전 설정", value="charge_cfg", description="AOS/IOS 선택 + 토큰"),
        discord.SelectOption(label="로그 설정", value="log_cfg", description="구매로그/충전로그 설정"),
    ]

    row1 = discord.ui.ActionRow()
    row1.add_item(
        discord.ui.Select(
            custom_id="v:cat",
            placeholder="카테고리 선택",
            min_values=1,
            max_values=1,
            options=(cat_opts or [discord.SelectOption(label="카테고리 없음", value="0")])[:25],
            disabled=not bool(cat_opts),
        )
    )

    row2 = discord.ui.ActionRow()
    row2.add_item(
        discord.ui.Select(
            custom_id="v:admin",
            placeholder="관리 메뉴",
            min_values=1,
            max_values=1,
            options=admin_opts[:25],
        )
    )

    container = discord.ui.Container(
        discord.ui.TextDisplay("## 자판기 패널"),
        discord.ui.TextDisplay("원하는 메뉴를 선택해주세요."),
        discord.ui.Separator(),
        row1,
        row2,
        accent_color=discord.Color.blurple(),
    )
    view.add_item(container)
    return view
