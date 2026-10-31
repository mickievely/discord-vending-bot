from __future__ import annotations
import discord


class RootServerIdModal(discord.ui.Modal):
    def __init__(self, custom_id: str, title: str, require_days: bool = False):
        super().__init__(title=title, custom_id=custom_id)
        self.server_id = discord.ui.TextInput(custom_id="server_id", label="서버 아이디", placeholder="예: 123456789012345678", required=True, max_length=30)
        self.add_item(self.server_id)
        self.days = None
        if require_days:
            self.days = discord.ui.TextInput(custom_id="days", label="일수", placeholder="예: 30", required=True, max_length=6)
            self.add_item(self.days)
