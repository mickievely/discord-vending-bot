from __future__ import annotations
import discord

class QtyModal(discord.ui.Modal):
    def __init__(self, product_id: int):
        super().__init__(title="수량 입력", custom_id=f"v:qty:{product_id}")
        self.qty = discord.ui.TextInput(custom_id="qty", label="수량", placeholder="예: 1", required=True, max_length=3)
        self.add_item(self.qty)

class ChargeModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="충전 요청", custom_id="v:charge_modal")
        self.amount = discord.ui.TextInput(custom_id="amount", label="금액(원)", placeholder="예: 10000", required=True, max_length=10)
        self.depositor = discord.ui.TextInput(custom_id="depositor", label="입금자명(한글)", placeholder="예: 홍길동", required=True, max_length=20)
        self.add_item(self.amount)
        self.add_item(self.depositor)
