from __future__ import annotations
import discord


class AdminPanelModal(discord.ui.Modal):
    def __init__(self, message_id: int):
        super().__init__(title="패널 설정", custom_id=f"a:panel_set:{int(message_id)}")
        self.title_input = discord.ui.TextInput(custom_id="title", label="제목(옵션)", required=False, max_length=200)
        self.description_input = discord.ui.TextInput(custom_id="description", label="설명(옵션)", required=False, style=discord.TextStyle.paragraph, max_length=4000)
        self.color_input = discord.ui.TextInput(custom_id="color", label="색상(옵션)", required=False, placeholder="예: 0x6C63FF 또는 7128575", max_length=20)
        self.image_url_input = discord.ui.TextInput(custom_id="image_url", label="이미지 URL(옵션)", required=False, max_length=500)
        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.color_input)
        self.add_item(self.image_url_input)


class AdminCategoryAddModal(discord.ui.Modal):
    def __init__(self, message_id: int):
        super().__init__(title="카테고리 추가", custom_id=f"a:cat_add:{int(message_id)}")
        self.name = discord.ui.TextInput(custom_id="name", label="카테고리 이름", required=True, max_length=50)
        self.add_item(self.name)


class AdminProductAddModal(discord.ui.Modal):
    def __init__(self, category_id: int):
        super().__init__(title="상품 추가", custom_id=f"a:prod_add:{int(category_id)}")
        self.name = discord.ui.TextInput(custom_id="name", label="상품명", required=True, max_length=100)
        self.price = discord.ui.TextInput(custom_id="price", label="가격(원)", required=True, max_length=20)
        self.description_input = discord.ui.TextInput(custom_id="description", label="설명(옵션)", required=False, style=discord.TextStyle.paragraph, max_length=1000)
        self.add_item(self.name)
        self.add_item(self.price)
        self.add_item(self.description_input)


class AdminStockAddModal(discord.ui.Modal):
    def __init__(self, product_id: int):
        super().__init__(title="재고 추가", custom_id=f"a:stock_add:{int(product_id)}")
        self.text = discord.ui.TextInput(custom_id="text", label="재고(한 줄=1개)", required=True, style=discord.TextStyle.paragraph, max_length=4000)
        self.add_item(self.text)


class AdminStockEditModal(discord.ui.Modal):
    def __init__(self, mode: str, product_id: int):
        title = "재고 설정" if mode == "set" else "재고 추가"
        super().__init__(title=title, custom_id=f"a:stock_edit:{mode}:{int(product_id)}")
        self.text = discord.ui.TextInput(custom_id="text", label="재고(한 줄=1개)", required=True, style=discord.TextStyle.paragraph, max_length=4000)
        self.add_item(self.text)


class AdminVendingMachineAddModal(discord.ui.Modal):
    def __init__(self, category_id: int):
        super().__init__(title="자판기 추가", custom_id=f"a:vm_add:{int(category_id)}")
        self.name = discord.ui.TextInput(custom_id="name", label="자판기 이름", placeholder="예: 프리미엄 자판기", required=True, max_length=50)
        self.add_item(self.name)
