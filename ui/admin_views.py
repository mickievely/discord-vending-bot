from __future__ import annotations
import discord


def select_view(custom_id: str, placeholder: str, options: list[discord.SelectOption]):
    from ui.v2_layouts import select_layout
    return select_layout(
        title=placeholder,
        description="선택해주세요.",
        custom_id=str(custom_id),
        placeholder=str(placeholder),
        options=options,
    )
