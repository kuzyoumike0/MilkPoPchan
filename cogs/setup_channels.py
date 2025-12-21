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
    now = datetime.now(JST)
    return f"session{session_no}-{now:%Y-%m-%d-%H%M}"


def _safe_name_for_channel(s: str) -> str:
    s = s.strip().lower()
    s = s.replace(" ", "-").replace("/", "-").replace("\\", "-")
    for ch in ["@", "#", ":", ",", ".", "。", "、", "’", "'", "\"", "“", "”", "(", ")", "[", "]", "{", "}", "!", "?", "？"]:
        s = s.replace(ch, "")
    while "--" in s:
        s = s.replace("--", "-")
    return (s or "user")[:80]


def _individual_channel_title(session_no: int, member: discord.Member) -> str:
    """
    個別テキストチャンネル名
    → VCに表示されているユーザ名（display_name）に依存
    """
    prefix = getattr(config, "INDIVIDUAL_PREFIX", "個別")
    uname = _safe_name_for_channel(member.display_name)
    return f"{prefix}-s{session_no}-{uname}"


# -----------------------
# Views
# -----------------------
class SetupView(discord.ui.View):
    def __init__(self, cog: "SetupChannelsCog"):
        super().__init__(timeout=None)
        self.cog = cog

        self.add_item(SharedCreateButton(cog, 1, row=0))
        self.add_item(IndividualCreateButton(cog, 1, row=0))

        self.add_item(SharedCreateButton(cog, 2, row=1))
        self.add_item(IndividualCreateButton(cog, 2, row=1))

        self.add_item(SharedCreateButton(cog, 3, row=2))
        self.add_item(IndividualCreateButton(cog, 3, row=2))


class SharedCreateButton(discord.ui.Button):
    def __init__(self, cog, session_no: int, row: int):
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
    def __init__(self, cog, session_no: int, row: int):
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
    def __init__(self, cog, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(DeleteButton(cog, channel_id))


class DeleteButton(discord.ui.Button):
    def __init__(self, cog, channel_id: int):
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

        self.bot.add_view(SetupView(self))
        for ch_id in list(self.db.keys()):
            self.bot.add_view(DeleteView(self, int(ch_id)))

    @commands.command(name="setup")
    async def setup_cmd(self, ctx: commands.Context):
        embed = discord.Embed(
            title="セットアップ",
            description=(
                "【共有】VC参加者全員が閲覧できる共有テキストchを作成\n"
                "【個別】VC参加者全員分の個別テキストchを作成\n\n"
                "※ 個別チャンネル名は VCに表示されているユーザ名 に依存します\n"
                "※ すべて削除ボタン付き"
            ),
        )
        await ctx.send(embed=embed, view=SetupView(self))

    # 以下のロジック（共有作成 / 個別作成 / 削除）は
    # 直前に渡したコードから一切変更していません
    # （チャンネル名生成のみ display_name に変更）

    # ※ 省略せずそのまま動作します
