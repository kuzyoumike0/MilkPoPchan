from __future__ import annotations

import json
import os
from typing import Dict, Optional

import discord
from discord.ext import commands

import config


DATA_PATH = os.path.join("data", "vc_text_channels.json")


def _ensure_data_dir():
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)


def _load_db() -> Dict[str, dict]:
    _ensure_data_dir()
    if not os.path.exists(DATA_PATH):
        return {}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_db(db: Dict[str, dict]) -> None:
    _ensure_data_dir()
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _is_adminish(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.administrator or perms.manage_channels


def _text_name_for_session(session_no: int) -> str:
    return f"session-{session_no}-private"


class SessionSelectView(discord.ui.View):
    def __init__(self, cog: "SetupVCSessionCategoriesCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="セッション1", style=discord.ButtonStyle.primary, custom_id="setupvc_sc:session:1")
    async def s1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_create(interaction, 1)

    @discord.ui.button(label="セッション2", style=discord.ButtonStyle.primary, custom_id="setupvc_sc:session:2")
    async def s2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_create(interaction, 2)

    @discord.ui.button(label="セッション3", style=discord.ButtonStyle.primary, custom_id="setupvc_sc:session:3")
    async def s3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_create(interaction, 3)


class DeleteTextChannelView(discord.ui.View):
    def __init__(self, cog: "SetupVCSessionCategoriesCog", text_channel_id: int):
        super().__init__(timeout=None)
        self.add_item(DeleteButton(cog, text_channel_id))


class DeleteButton(discord.ui.Button):
    def __init__(self, cog: "SetupVCSessionCategoriesCog", text_channel_id: int):
        super().__init__(
            label="このテキストchを削除",
            style=discord.ButtonStyle.danger,
            custom_id=f"setupvc_sc:delete:{text_channel_id}",
        )
        self.cog = cog
        self.text_channel_id = text_channel_id

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_delete(interaction, self.text_channel_id)


class SetupVCSessionCategoriesCog(commands.Cog):
    """
    !setupvc を打つとセッション1/2/3ボタンを出す。
    押されたセッションのVC参加者全員 + 見学ロール が閲覧できるテキストchを、
    セッションごとの専用カテゴリに作成する。
    テキストchには削除ボタンを設置（作成者 or 管理者のみ削除可）。
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = _load_db()

        # 永続View登録
        self.bot.add_view(SessionSelectView(self))
        for ch_id_str in list(self.db.keys()):
            try:
                ch_id = int(ch_id_str)
            except ValueError:
                continue
            self.bot.add_view(DeleteTextChannelView(self, ch_id))

    @commands.command(name="setupvc")
    async def setupvc(self, ctx: commands.Context):
        if config.SETUP_CHANNEL_ID and ctx.channel.id != config.SETUP_CHANNEL_ID:
            await ctx.reply("このコマンドは専用チャンネルで実行してください。", mention_author=False)
            return

        embed = discord.Embed(
            title="VCセッション選択",
            description=(
                "作成したいセッションのボタンを押してください。\n"
                "そのVCに居る全員＋見学ロールが閲覧できるテキストchを作成します。\n"
                "作成先はセッションごとの専用カテゴリです。"
            ),
        )
        await ctx.send(embed=embed, view=SessionSelectView(self))

    async def handle_create(self, interaction: discord.Interaction, session_no: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内で実行してください。", ephemeral=True)
            return

        user = interaction.user
        if not isinstance(user, discord.Member):
            await interaction.followup.send("メンバー情報が取得できませんでした。", ephemeral=True)
            return

        # VC取得
        vc_id = config.SESSION_VC_IDS.get(session_no)
        voice = guild.get_channel(vc_id) if vc_id else None
        if not isinstance(voice, discord.VoiceChannel):
            await interaction.followup.send("指定のセッションVCが見つかりません（ID設定を確認）。", ephemeral=True)
            return

        vc_members = list(voice.members)
        if not vc_members:
            await interaction.followup.send("そのVCに誰もいません。作成できません。", ephemeral=True)
            return

        # 見学ロール
        spectator = guild.get_role(config.SPECTATOR_ROLE_ID)
        if spectator is None:
            await interaction.followup.send("見学ロールが見つかりません（SPECTATOR_ROLE_IDを確認）。", ephemeral=True)
            return

        # 作成カテゴリ（セッション別）
        cat_id = getattr(config, "SESSION_TEXT_CATEGORY_IDS", {}).get(session_no)
        category = guild.get_channel(cat_id) if cat_id else None
        if not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send(
                "このセッションの作成カテゴリが正しく設定されていません（SESSION_TEXT_CATEGORY_IDSを確認）。",
                ephemeral=True
            )
            return

        name = _text_name_for_session(session_no)

        # 権限
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            spectator: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False),
            user: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True),
        }
        for m in vc_members:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True)

        # 同カテゴリ同名があれば更新、無ければ作成
        existing = discord.utils.get(guild.text_channels, name=name, category=category)
        if existing:
            try:
                await existing.edit(overwrites=overwrites, reason="VC参加者/見学ロールの権限更新")
            except discord.Forbidden:
                await interaction.followup.send("権限不足で既存チャンネルを更新できません。", ephemeral=True)
                return
            text_ch = existing
        else:
            try:
                text_ch = await guild.create_text_channel(
                    name=name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"setupvc session {session_no} by {user}",
                )
            except discord.Forbidden:
                await interaction.followup.send("権限不足でチャンネル作成できません。", ephemeral=True)
                return

        # DB保存（削除ボタン復元用）
        self.db[str(text_ch.id)] = {
            "creator_id": user.id,
            "guild_id": guild.id,
            "session_no": session_no,
            "voice_channel_id": voice.id,
            "category_id": category.id,
        }
        _save_db(self.db)

        # 永続View登録
        self.bot.add_view(DeleteTextChannelView(self, text_ch.id))

        # 作成/更新通知（テキストch側）
        embed = discord.Embed(
            title=f"セッション{session_no}：プライベートテキストch",
            description=(
                f"対象VC：{voice.mention}\n"
                f"作成先カテゴリ：{category.name}\n"
                f"閲覧：VC参加者＋{spectator.mention}\n\n"
                "削除する場合は下のボタンを押してください。"
            ),
        )
        try:
            await text_ch.send(embed=embed, view=DeleteTextChannelView(self, text_ch.id))
        except discord.Forbidden:
            await interaction.followup.send("作成したチャンネルに投稿できません（権限不足）。", ephemeral=True)
            return

        await interaction.followup.send(f"✅ {text_ch.mention} を用意しました（セッション{session_no}）。", ephemeral=True)

    async def handle_delete(self, interaction: discord.Interaction, text_channel_id: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内で実行してください。", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send("メンバー情報が取得できませんでした。", ephemeral=True)
            return

        ch = guild.get_channel(text_channel_id)
        if not isinstance(ch, discord.TextChannel):
            # DB掃除
            if str(text_channel_id) in self.db:
                self.db.pop(str(text_channel_id), None)
                _save_db(self.db)
            await interaction.followup.send("対象のテキストchが見つかりません（既に削除済みかも）。", ephemeral=True)
            return

        info = self.db.get(str(text_channel_id), {})
        creator_id = info.get("creator_id")

        if creator_id != member.id and not _is_adminish(member):
            await interaction.followup.send("削除できるのは作成者または管理者のみです。", ephemeral=True)
            return

        try:
            await ch.delete(reason=f"Deleted by {member} via setupvc delete button")
        except discord.Forbidden:
            await interaction.followup.send("権限不足で削除できません。", ephemeral=True)
            return

        self.db.pop(str(text_channel_id), None)
        _save_db(self.db)
        await interaction.followup.send("🗑 テキストchを削除しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupVCSessionCategoriesCog(bot))
