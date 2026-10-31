from __future__ import annotations
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from services import vending_service
from ui.embeds import error_embed, ok_embed, user_stats_embed, charge_result_embed
from config import DISCORD_GUILD_ID
from ui.v2_layouts import VendingPanelLayout


def _wrong_guild(i: discord.Interaction) -> bool:
    if not i.guild or not DISCORD_GUILD_ID:
        return True
    return int(i.guild.id) != int(DISCORD_GUILD_ID)


def _is_admin(i: discord.Interaction) -> bool:
    if not i.guild or not i.user:
        return False
    if isinstance(i.user, discord.Member):
        return i.user.guild_permissions.administrator
    return False


async def _can_manual_charge(i: discord.Interaction) -> bool:
    if _is_admin(i):
        return True
    if not i.guild or not isinstance(i.user, discord.Member):
        return False
    try:
        cfg = await vending_service.get_charge_settings(i.guild.id)
        cfg = dict(cfg) if cfg else {}
    except Exception:
        cfg = {}
    role_id = int(cfg.get("charge_manager_role_id") or 0)
    if role_id <= 0:
        return False
    return any(int(r.id) == role_id for r in i.user.roles)


async def _resolve_log_channel(bot: commands.Bot, guild: discord.Guild, channel_id: int | None):
    if not channel_id:
        return None
    try:
        ch = guild.get_channel(int(channel_id))
        if ch:
            return ch
    except Exception:
        pass
    try:
        return await bot.fetch_channel(int(channel_id))
    except Exception:
        return None


def _manual_charge_embed(
    interaction: discord.Interaction,
    user: discord.Member,
    *,
    before: int,
    after: int,
    delta: int,
    reason: Optional[str],
    log: bool,
) -> discord.Embed:
    from services.notify import kst_now_str
    actor = interaction.user
    amount = abs(int(delta))
    action_label = "충전" if int(delta) >= 0 else "차감"
    color = 0x57F287 if int(delta) >= 0 else 0xED4245
    actor_mention = actor.mention if getattr(actor, "mention", None) else str(actor)
    actor_name = str(actor)
    actor_id = getattr(actor, "id", None)
    when = kst_now_str()

    embed = discord.Embed(
        title="수동충전 로그" if log else "수동충전",
        description=f"{actor_mention} 님이 {user.mention} 님에게 {amount:,}원 {action_label}했습니다.",
        color=color,
    )
    if not log:
        embed.add_field(name="처리자", value=f"{actor_mention}\n`{actor_name}` · ID `{actor_id}`", inline=False)
        embed.add_field(name="시각", value=f"`{when}`", inline=True)
        embed.timestamp = discord.utils.utcnow()
        return embed

    embed.add_field(name="처리자", value=f"{actor_mention}\n`{actor_name}`", inline=True)
    embed.add_field(name="처리자 ID", value=f"`{actor_id}`", inline=True)
    embed.add_field(name="대상", value=f"{user.mention}\n`{user}`", inline=True)
    embed.add_field(name="대상 ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="금액", value=f"`{amount:,}원`", inline=True)
    embed.add_field(name="변경", value=f"`{int(delta):+,}원`", inline=True)
    embed.add_field(name="이전 잔액", value=f"`{int(before):,}원`", inline=True)
    embed.add_field(name="이후 잔액", value=f"`{int(after):,}원`", inline=True)
    embed.add_field(name="시각", value=f"`{when}`", inline=True)
    if reason:
        embed.add_field(name="사유", value=str(reason)[:1024], inline=False)
    embed.timestamp = discord.utils.utcnow()
    return embed


async def _send_manual_charge_messages(
    bot: commands.Bot,
    interaction: discord.Interaction,
    user: discord.Member,
    *,
    before: int,
    after: int,
    delta: int,
    reason: Optional[str],
):
    if not interaction.guild:
        return

    try:
        cfg = await vending_service.get_charge_settings(interaction.guild.id)
        cfg = dict(cfg) if cfg else {}
    except Exception:
        cfg = {}
    public_enabled = int(cfg.get("manual_charge_notice_enabled") if cfg.get("manual_charge_notice_enabled") is not None else 1) == 1

    if public_enabled and isinstance(interaction.channel, discord.abc.Messageable):
        try:
            await interaction.channel.send(embed=_manual_charge_embed(interaction, user, before=before, after=after, delta=delta, reason=reason, log=False))
        except Exception:
            pass

    try:
        logs = await vending_service.get_log_settings(interaction.guild.id)
        logs = dict(logs) if logs else {}
        channel_id = int(logs.get("manual_charge_channel_id") or 0)
    except Exception:
        channel_id = 0
    if not channel_id:
        return

    channel = await _resolve_log_channel(bot, interaction.guild, channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        return

    try:
        await channel.send(embed=_manual_charge_embed(interaction, user, before=before, after=after, delta=delta, reason=reason, log=True))
    except Exception:
        pass


class CoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="자판기", description="자판기를 채널에 띄워(다른 사람도 사용 가능)")
    async def vending_public(self, interaction: discord.Interaction):
        if _wrong_guild(interaction):
            return await interaction.response.send_message(embed=error_embed("이 봇은 설정된 서버에서만 사용할 수 있어"), ephemeral=True)
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message(embed=error_embed("서버에서만 가능해"), ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("관리자만 가능해"), ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        panel = await vending_service.panel(interaction.guild.id)
        panel = dict(panel) if panel else {}
        title = (panel.get("title") or "").strip()
        desc = (panel.get("description") or "").strip()
        image_url = (panel.get("image_url") or None)
        color = int(panel.get("color") or 0)
        from ui.v2_layouts import vending_machine_message
        view = vending_machine_message(title=title, description=desc, image_url=image_url, color=color)
        await interaction.channel.send(view=view)
        await interaction.followup.send(embed=ok_embed("자판기 게시 완료"), ephemeral=True)


    @app_commands.command(name="자판기패널", description="자판기 패널을 채널에 게시해")
    async def vending_panel(self, interaction: discord.Interaction):
        if _wrong_guild(interaction):
            return await interaction.response.send_message(embed=error_embed("이 봇은 설정된 서버에서만 사용할 수 있어"), ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message(embed=error_embed("서버에서만 가능해"), ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("관리자만 가능해"), ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        panel = await vending_service.panel(interaction.guild.id)
        panel = dict(panel) if panel else {}
        view = VendingPanelLayout(
            title=(panel.get("title") or "").strip(),
            description=(panel.get("description") or "").strip(),
            color=int(panel.get("color") or 0x5865F2),
            timeout=300,
        )
        await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="내정보", description="내 잔액/구매 정보를 확인")
    async def my_info(self, interaction: discord.Interaction):
        if _wrong_guild(interaction):
            return await interaction.response.send_message(embed=error_embed("이 봇은 설정된 서버에서만 사용할 수 있어"), ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message(embed=error_embed("서버에서만 가능해"), ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        from bot import _my_info_view
        await interaction.followup.send(view=await _my_info_view(interaction.guild.id, interaction.user), ephemeral=True)

    @app_commands.command(name="정보", description="유저 잔액/구매 정보를 확인(관리자)")
    @app_commands.describe(user="조회할 유저")
    async def user_info(self, interaction: discord.Interaction, user: discord.Member):
        if _wrong_guild(interaction):
            return await interaction.response.send_message(embed=error_embed("이 봇은 설정된 서버에서만 사용할 수 있어"), ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message(embed=error_embed("서버에서만 가능해"), ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("관리자만 가능해"), ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        st = await vending_service.user_stats(interaction.guild.id, user.id)
        await interaction.followup.send(embed=user_stats_embed("유저 정보", user, st), ephemeral=True)

    @app_commands.command(name="수동충전", description="유저 잔액을 추가/차감(관리자/수충권한)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="추가", value="add"),
            app_commands.Choice(name="차감", value="sub"),
        ]
    )
    @app_commands.describe(user="대상 유저", action="추가/차감", amount="금액(양수)", reason="사유(선택)")
    async def manual_charge(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        action: app_commands.Choice[str],
        amount: int,
        reason: Optional[str] = None,
    ):
        if _wrong_guild(interaction):
            return await interaction.response.send_message(embed=error_embed("이 봇은 설정된 서버에서만 사용할 수 있어"), ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message(embed=error_embed("서버에서만 가능해"), ephemeral=True)
        if not await _can_manual_charge(interaction):
            return await interaction.response.send_message(embed=error_embed("수동충전 권한이 없습니다."), ephemeral=True)
        amt = int(amount)
        if amt <= 0:
            return await interaction.response.send_message(embed=error_embed("금액은 1원 이상"), ephemeral=True)
        delta = amt if action.value == "add" else -amt

        await interaction.response.defer(ephemeral=True, thinking=True)
        before = await vending_service.get_balance(interaction.guild.id, user.id)
        res = await vending_service.add_balance(interaction.guild.id, user.id, delta)
        if not res or not res.get("ok"):
            return await interaction.followup.send(embed=error_embed("차감할 잔액이 부족해"), ephemeral=True)
        after = int(res["balance"])
        await _send_manual_charge_messages(
            self.bot,
            interaction,
            user,
            before=before,
            after=after,
            delta=delta,
            reason=reason,
        )
        await interaction.followup.send(embed=charge_result_embed(user, before, after, delta, reason), ephemeral=True)

    @app_commands.command(name="vip부여", description="유저에게 VIP 할인 티어를 부여(관리자)")
    @app_commands.describe(user="대상 유저", 티어="티어 이름. 비우면 해제")
    async def grant_vip(self, interaction: discord.Interaction, user: discord.Member, 티어: Optional[str] = None):
        if _wrong_guild(interaction):
            return await interaction.response.send_message(embed=error_embed("이 봇은 설정된 서버에서만 사용할 수 있어"), ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message(embed=error_embed("서버에서만 가능해"), ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("관리자만 가능해"), ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        tiers = await vending_service.list_vip_tiers(interaction.guild.id)
        if not 티어:
            await vending_service.set_user_vip(interaction.guild.id, user.id, None)
            return await interaction.followup.send(embed=ok_embed(f"{user.mention} VIP를 해제했습니다."), ephemeral=True)
        want = str(티어).strip().lower()
        hit = next((t for t in tiers if str(t.get("name") or "").strip().lower() == want), None)
        if not hit:
            names = ", ".join(str(t.get("name") or "") for t in tiers) or "없음"
            return await interaction.followup.send(embed=error_embed(f"없는 티어입니다. 가능: {names}"), ephemeral=True)
        await vending_service.set_user_vip(interaction.guild.id, user.id, int(hit["id"]))
        await interaction.followup.send(
            embed=ok_embed(f"{user.mention} → {hit.get('emoji') or ''} {hit.get('name')} (-{int(hit.get('discountPct') or 0)}%)".strip()),
            ephemeral=True,
        )

    @grant_vip.autocomplete("티어")
    async def vip_name_ac(self, interaction: discord.Interaction, current: str):
        if not interaction.guild:
            return []
        try:
            tiers = await vending_service.list_vip_tiers(interaction.guild.id)
        except Exception:
            return []
        q = (current or "").strip().lower()
        out = []
        for t in tiers:
            name = str(t.get("name") or "")
            if q and q not in name.lower():
                continue
            out.append(app_commands.Choice(name=f"{t.get('emoji') or ''} {name} -{int(t.get('discountPct') or 0)}%".strip(), value=name))
            if len(out) >= 25:
                break
        return out


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCog(bot))
