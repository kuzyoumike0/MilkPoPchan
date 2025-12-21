from __future__ import annotations

import discord
from discord.ext import commands
import json
import os
from typing import Dict

import config


DATA_PATH = "data/vc_text_channels.json"


# =====================
# Utility
# =====================

def ensure_data():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DATA_PATH):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)


def load_db() -> Dict[str, dict]:
    ensure_data()
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db: Dict[str, dict]):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def is_admin(member: discord.Member) -> bool:
    p = member.guild_permissions
    return p.administrator or p.manage_channels


def text_channel_name(session_no: int) -> str:
    return f"session-{session_no}-private"


# =====================
# Views
# =====================

class SessionSelectView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="セッション1", style=discord.ButtonStyle.primary, custom_id="setup:session:1")
    async def s1(self, interaction: discord.Interaction, _):
        await self.cog.create_text_channel(interaction, 1)

    @discord.ui.button(label="セッション2", style=discord.ButtonStyle.primary, custom_id="setup:session:2")
    async def s2(self, interaction: discord.Interaction, _):
        await self.cog.create_text_channel(interaction, 2)

    @discord.ui.button(label="セッション3", style=discord.ButtonStyle.primary, custom_id="setup:session:3")
    async def s3(self, interaction: discord.Interaction, _):
        await self.cog.create_text_channel(interaction, 3)


class DeleteView(discord.ui.View):
    def __init__(self, cog, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(DeleteButton(cog, channel_id))


class DeleteButton(discord.ui.Button):
    def __init__(self, cog, channel_id: int):
        super().__init__(
            label="このテキストchを削除",
            style=discord.ButtonStyle.danger,
            custom_id=f"setup:delete:{channel_id}"
        )
        self.cog = cog
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        await self.cog.delete_text_channel(interaction, self.channel_id)


# =====================
# Cog
# =====================

class SetupVCSessionCategoriesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = load_db()

        # 永続View登録
        self.bot.add_view(SessionSelectView(self))
        for ch_id in self.db.keys():
            self.bot.add_view(DeleteView(self, int(ch_id)))

    # -----------------
    # !setup コマンド
    # -----------------
    @commands.command(name="setup")
    async def setup(self, ctx: commands.Context):
        if config.SETUP_CHANNEL_ID and ctx.channel.id != config.SETUP_CHANNEL_ID:
            await ctx.reply("このコマンドは専用チャンネルで使用してください。", mention_author=False)
            return

        embed = discord.Embed(
            title="VCセッション設定",
            description=(
                "作成したいセッションを選択してください。\n\n"
                "✔ VC参加者全員が閲覧・書き込み可\n"
                "✔ 見学ロールは閲覧のみ可\n"
                "✔ セッション別カテゴリに作成\n"
            )
        )
        await ctx.send(embed=embed, view=SessionSelectView(self))

    # -----------------
    # 作成処理
    # -----------------
    async def create_text_channel(self, interaction: discord.Interaction, session_no: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        vc_id = config.SESSION_VC_IDS.get(session_no)
        cat_id = config.SESSION_TEXT_CATEGORY_IDS.get(session_no)

        vc = guild.get_channel(vc_id)
        category = guild.get_channel(cat_id)
        spectator = guild.get_role(config.SPECTATOR_ROLE_ID)

        if not isinstance(vc, discord.VoiceChannel):
            await interaction.followup.send("VC設定が正しくありません。", ephemeral=True)
            return
        if not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("カテゴリ設定が正しくありません。", ephemeral=True)
            return
        if spectator is None:
            await interaction.followup.send("見学ロールが見つかりません。", ephemeral=True)
            return
        if not vc.members:
            await interaction.followup.send("そのVCに誰もいません。", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            spectator: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        }

        for m in vc.members:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        name = text_channel_name(session_no)
        existing = discord.utils.get(guild.text_channels, name=name, category=category)

        if existing:
            text_ch = existing
            await text_ch.edit(overwrites=overwrites)
        else:
            text_ch = await guild.create_text_channel(
                name=name,
                category=category,
                overwrites=overwrites
            )

        self.db[str(text_ch.id)] = {
            "creator_id": user.id,
            "session": session_no
        }
        save_db(self.db)

        self.bot.add_view(DeleteView(self, text_ch.id))

        embed = discord.Embed(
            title=f"セッション{session_no} プライベートch",
            description="このチャンネルは削除可能です。"
        )
        await text_ch.send(embed=embed, view=DeleteView(self, text_ch.id))

        await interaction.followup.send(f"✅ {text_ch.mention} を作成しました。", ephemeral=True)

    # -----------------
    # 削除処理
    # -----------------
    async def delete_text_channel(self, interaction: discord.Interaction, channel_id: int):
        await interaction.response.defer(ephemeral=True)

        ch = interaction.guild.get_channel(channel_id)
        member = interaction.user

        if not ch:
            self.db.pop(str(channel_id), None)
            save_db(self.db)
            await interaction.followup.send("既に削除されています。", ephemeral=True)
            return

        info = self.db.get(str(channel_id))
        if info and info["creator_id"] != member.id and not is_admin(member):
            await interaction.followup.send("削除できるのは作成者または管理者のみです。", ephemeral=True)
            return

        await ch.delete()
        self.db.pop(str(channel_id), None)
        save_db(self.db)

        await interaction.followup.send("🗑 テキストchを削除しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupVCSessionCategoriesCog(bot))
