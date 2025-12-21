from __future__ import annotations

import json
import os
from typing import Dict, Optional, List
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

import config

DB_PATH = os.path.join("data", "setup_channels_db.json")
JST = ZoneInfo("Asia/Tokyo")


# -----------------------
# DB helpers
# -----------------------
def _ensure_db():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _load_db() -> Dict[str, dict]:
    _ensure_db()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_db(db: Dict[str, dict]) -> None:
    _ensure_db()
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _is_adminish(member: discord.Member) -> bool:
    p = member.guild_permissions
    return p.administrator or p.manage_channels


# -----------------------
# Naming
# -----------------------
def _shared_channel_title(session_no: int) -> str:
    # 「セッション（１，２，３に依存する）年、月、日、時間」
    # Discordのチャンネル名はカンマや全角スペース等が扱いにくいので、読みやすいハイフン形式に。
    # 例: session1-2025-12-21-1030
    now = datetime.now(JST)
    return f"session{session_no}-{now:%Y-%m-%d-%H%M}"


def _safe_name_for_channel(s: str) -> str:
    # Discordチャンネル名向け最低限整形
    s = s.strip().lower()
    s = s.replace(" ", "-").replace("/", "-").replace("\\", "-")
    # 記号をざっくり安全に
    for ch in ["@", "#", ":", ",", ".", "。", "、", "’", "'", "\"", "“", "”", "(", ")", "[", "]", "{", "}", "!", "?", "？"]:
        s = s.replace(ch, "")
    # 連続ハイフンを多少潰す
    while "--" in s:
        s = s.replace("--", "-")
    if not s:
        s = "user"
    return s[:80]


def _individual_channel_title(session_no: int, member: discord.Member) -> str:
    # 「個別チャンネルのタイトルはディスコードのユーザ名に依存」
    # 例: 個別-s1-username
    prefix = getattr(config, "INDIVIDUAL_PREFIX", "個別")
    uname = _safe_name_for_channel(member.name)  # ユーザ名依存（display_nameではなくuser.name）
    return f"{prefix}-s{session_no}-{uname}"


# -----------------------
# Views
# -----------------------
class SetupView(discord.ui.View):
    """
    !setup 後のボタン群
    仕様上セッション依存があるため、セッションごとに「共有作成」「個別作成」を用意する。
    """
    def __init__(self, cog: "SetupChannelsCog"):
        super().__init__(timeout=None)
        self.cog = cog

        # 3行に分けて配置（見やすさ重視）
        self.add_item(SharedCreateButton(cog, 1, row=0))
        self.add_item(IndividualCreateButton(cog, 1, row=0))

        self.add_item(SharedCreateButton(cog, 2, row=1))
        self.add_item(IndividualCreateButton(cog, 2, row=1))

        self.add_item(SharedCreateButton(cog, 3, row=2))
        self.add_item(IndividualCreateButton(cog, 3, row=2))


class SharedCreateButton(discord.ui.Button):
    def __init__(self, cog: "SetupChannelsCog", session_no: int, row: int):
        super().__init__(
            label=f"セッション{session_no}：共有テキストch作成",
            style=discord.ButtonStyle.secondary,
            custom_id=f"setup:shared_create:{session_no}",
            row=row,
        )
        self.cog = cog
        self.session_no = session_no

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_shared_create(interaction, self.session_no)


class IndividualCreateButton(discord.ui.Button):
    def __init__(self, cog: "SetupChannelsCog", session_no: int, row: int):
        super().__init__(
            label=f"セッション{session_no}：個別テキストch作成",
            style=discord.ButtonStyle.primary,
            custom_id=f"setup:individual_create:{session_no}",
            row=row,
        )
        self.cog = cog
        self.session_no = session_no

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_individual_create(interaction, self.session_no)


class DeleteView(discord.ui.View):
    def __init__(self, cog: "SetupChannelsCog", channel_id: int):
        super().__init__(timeout=None)
        self.add_item(DeleteButton(cog, channel_id))


class DeleteButton(discord.ui.Button):
    def __init__(self, cog: "SetupChannelsCog", channel_id: int):
        super().__init__(
            label="このチャンネルを削除",
            style=discord.ButtonStyle.danger,
            custom_id=f"setup:delete:{channel_id}",
        )
        self.cog = cog
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_delete(interaction, self.channel_id)


# -----------------------
# Cog
# -----------------------
class SetupChannelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = _load_db()

        # 永続View登録
        self.bot.add_view(SetupView(self))

        # 既存削除ボタン復元
        for ch_id_str in list(self.db.keys()):
            try:
                ch_id = int(ch_id_str)
            except ValueError:
                continue
            self.bot.add_view(DeleteView(self, ch_id))

    # -----------------
    # !setup
    # -----------------
    @commands.command(name="setup")
    async def setup_cmd(self, ctx: commands.Context):
        if config.SETUP_CHANNEL_ID and ctx.channel.id != config.SETUP_CHANNEL_ID:
            await ctx.reply("このコマンドは専用チャンネルで使用してください。", mention_author=False)
            return

        embed = discord.Embed(
            title="セットアップ",
            description=(
                "下のボタンで作成できます。\n\n"
                "【共有】VC参加者全員が閲覧できる共有テキストchを作成（タイトル：セッションN + 日時）\n"
                "【個別】VC参加者全員ぶん個別テキストchを作成（閲覧：本人 + setup実行者 + 見学ロール）\n\n"
                "※ すべてのチャンネルに削除ボタンが付きます。"
            ),
        )
        await ctx.send(embed=embed, view=SetupView(self))

    # -----------------
    # Getters
    # -----------------
    def _get_session_vc(self, guild: discord.Guild, session_no: int) -> Optional[discord.VoiceChannel]:
        vc_id = getattr(config, "SESSION_VC_IDS", {}).get(session_no)
        ch = guild.get_channel(vc_id) if vc_id else None
        return ch if isinstance(ch, discord.VoiceChannel) else None

    def _get_spectator_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        rid = getattr(config, "SPECTATOR_ROLE_ID", None)
        return guild.get_role(rid) if rid else None

    def _get_shared_category(self, guild: discord.Guild, session_no: int) -> Optional[discord.CategoryChannel]:
        cid = getattr(config, "SESSION_SHARED_CATEGORY_IDS", {}).get(session_no)
        ch = guild.get_channel(cid) if cid else None
        return ch if isinstance(ch, discord.CategoryChannel) else None

    def _get_individual_category(self, guild: discord.Guild, session_no: int) -> Optional[discord.CategoryChannel]:
        cid = getattr(config, "SESSION_INDIVIDUAL_CATEGORY_IDS", {}).get(session_no)
        ch = guild.get_channel(cid) if cid else None
        return ch if isinstance(ch, discord.CategoryChannel) else None

    # -----------------
    # Shared create
    # -----------------
    async def handle_shared_create(self, interaction: discord.Interaction, session_no: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内で実行してください。", ephemeral=True)
            return

        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            await interaction.followup.send("メンバー情報が取得できませんでした。", ephemeral=True)
            return

        vc = self._get_session_vc(guild, session_no)
        if vc is None:
            await interaction.followup.send("セッションVCが見つかりません（ID設定を確認）。", ephemeral=True)
            return

        vc_members: List[discord.Member] = list(vc.members)
        if not vc_members:
            await interaction.followup.send("そのVCに誰もいません。作成できません。", ephemeral=True)
            return

        category = self._get_shared_category(guild, session_no)
        if category is None:
            await interaction.followup.send("共有ch作成先カテゴリが見つかりません（SESSION_SHARED_CATEGORY_IDSを確認）。", ephemeral=True)
            return

        name = _shared_channel_title(session_no)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            # 共有は「VC参加者全員が閲覧できる」が要件なので、VCメンバーに付与
        }

        # 実行者がVCに居ないケースでも触れるように（要件外だが実用上便利）
        overwrites[invoker] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=True
        )

        for m in vc_members:
            overwrites[m] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=True
            )

        try:
            text_ch = await guild.create_text_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                reason=f"setup shared session {session_no} by {invoker}",
            )
        except discord.Forbidden:
            await interaction.followup.send("権限不足で共有テキストchを作成できません。", ephemeral=True)
            return

        # DB登録（削除ボタン復元用）
        self.db[str(text_ch.id)] = {
            "guild_id": guild.id,
            "creator_id": invoker.id,
            "session_no": session_no,
            "type": "shared",
        }
        _save_db(self.db)
        self.bot.add_view(DeleteView(self, text_ch.id))

        embed = discord.Embed(
            title="共有テキストチャンネル",
            description=(
                f"セッション{session_no} / 対象VC：{vc.mention}\n"
                f"閲覧：VC参加者\n\n"
                "削除する場合は下のボタンを押してください。"
            ),
        )
        await text_ch.send(embed=embed, view=DeleteView(self, text_ch.id))

        await interaction.followup.send(f"✅ 共有テキストchを作成しました：{text_ch.mention}", ephemeral=True)

    # -----------------
    # Individual create (for every VC member)
    # -----------------
    async def handle_individual_create(self, interaction: discord.Interaction, session_no: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内で実行してください。", ephemeral=True)
            return

        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            await interaction.followup.send("メンバー情報が取得できませんでした。", ephemeral=True)
            return

        vc = self._get_session_vc(guild, session_no)
        if vc is None:
            await interaction.followup.send("セッションVCが見つかりません（ID設定を確認）。", ephemeral=True)
            return

        vc_members: List[discord.Member] = list(vc.members)
        if not vc_members:
            await interaction.followup.send("そのVCに誰もいません。作成できません。", ephemeral=True)
            return

        category = self._get_individual_category(guild, session_no)
        if category is None:
            await interaction.followup.send("個別ch作成先カテゴリが見つかりません（SESSION_INDIVIDUAL_CATEGORY_IDSを確認）。", ephemeral=True)
            return

        spectator = self._get_spectator_role(guild)
        if spectator is None:
            await interaction.followup.send("見学ロールが見つかりません（SPECTATOR_ROLE_IDを確認）。", ephemeral=True)
            return

        created = 0
        failed: List[str] = []

        for target in vc_members:
            ch_name = _individual_channel_title(session_no, target)

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),

                # 見学ロール：全員「閲覧できるようにする」
                spectator: discord.PermissionOverwrite(
                    view_channel=True, read_message_history=True, send_messages=False
                ),

                # setup実行者：閲覧＋送信可
                invoker: discord.PermissionOverwrite(
                    view_channel=True, read_message_history=True, send_messages=True
                ),

                # 対象本人：閲覧＋送信可
                target: discord.PermissionOverwrite(
                    view_channel=True, read_message_history=True, send_messages=True
                ),
            }

            try:
                text_ch = await guild.create_text_channel(
                    name=ch_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"setup individual session {session_no} target {target.id} by {invoker.id}",
                )
                created += 1

                # DB登録
                self.db[str(text_ch.id)] = {
                    "guild_id": guild.id,
                    "creator_id": invoker.id,
                    "session_no": session_no,
                    "type": "individual",
                    "target_member_id": target.id,
                }
                _save_db(self.db)
                self.bot.add_view(DeleteView(self, text_ch.id))

                embed = discord.Embed(
                    title=f"個別テキストチャンネル：{target.name}",
                    description=(
                        f"セッション{session_no} / 対象VC：{vc.mention}\n"
                        f"本人：{target.mention}\n"
                        f"作成者：{invoker.mention}\n"
                        f"見学：{spectator.mention}（閲覧のみ）\n\n"
                        "削除する場合は下のボタンを押してください。"
                    ),
                )
                await text_ch.send(embed=embed, view=DeleteView(self, text_ch.id))

            except discord.Forbidden:
                failed.append(target.name)
            except Exception:
                failed.append(target.name)

        msg = f"✅ 個別テキストchを作成しました（セッション{session_no}）: {created}件"
        if failed:
            msg += f"\n⚠ 作成失敗: {', '.join(failed[:10])}" + (" …" if len(failed) > 10 else "")

        await interaction.followup.send(msg, ephemeral=True)

    # -----------------
    # Delete (all channels)
    # -----------------
    async def handle_delete(self, interaction: discord.Interaction, channel_id: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内で実行してください。", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send("メンバー情報が取得できませんでした。", ephemeral=True)
            return

        ch = guild.get_channel(channel_id)
        if not isinstance(ch, discord.TextChannel):
            # DB掃除
            if str(channel_id) in self.db:
                self.db.pop(str(channel_id), None)
                _save_db(self.db)
            await interaction.followup.send("対象チャンネルが見つかりません（既に削除済みかも）。", ephemeral=True)
            return

        info = self.db.get(str(channel_id), {})
        creator_id = info.get("creator_id")

        # 削除できる人：作成者 or 管理者
        if creator_id != member.id and not _is_adminish(member):
            await interaction.followup.send("削除できるのは作成者または管理者のみです。", ephemeral=True)
            return

        try:
            await ch.delete(reason=f"Deleted by {member} via delete button")
        except discord.Forbidden:
            await interaction.followup.send("権限不足で削除できません。", ephemeral=True)
            return

        self.db.pop(str(channel_id), None)
        _save_db(self.db)

        await interaction.followup.send("🗑 チャンネルを削除しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupChannelsCog(bot))
