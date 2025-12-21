from __future__ import annotations

import html
import io
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo  # ★ JST用（Python 3.9+）

import discord
from discord.ext import commands

# ================= 設定 =================
DEFAULT_LIMIT = 200
MAX_LIMIT = 5000
TIMEZONE = ZoneInfo("Asia/Tokyo")   # ★ 日本時間
TIME_FORMAT = "%Y-%m-%d %H:%M"      # 例: 2025-12-21 10:05

SAFE_MAX_BYTES = 8 * 1024 * 1024 - 200_000
URL_RE = re.compile(r"(https?://[^\s]+)")

USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")

# ================= HTML =================
def make_html_page(guild_name: str, channel_name: str, exported_at: str, messages_html: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>{html.escape(guild_name)} - #{html.escape(channel_name)}</title>
<style>
body {{ background:#1e1f22; color:#dbdee1; font-family: system-ui; }}
.msg {{ display:grid; grid-template-columns:44px 1fr; gap:12px; padding:10px 16px; }}
.avatar {{ width:40px; height:40px; border-radius:999px; }}
.author {{ font-weight:700; }}
.time {{ color:#949ba4; font-size:12px; margin-left:6px; }}
.attach img {{ max-width:360px; border-radius:10px; }}
</style>
</head>
<body>
<h3>{html.escape(guild_name)} / #{html.escape(channel_name)}</h3>
<p>Exported at (JST): {exported_at}</p>
{messages_html}
</body>
</html>
"""

# ================= メンション変換 =================
def _display_user(guild: Optional[discord.Guild], user_id: int) -> str:
    if not guild:
        return f"@{user_id}"
    m = guild.get_member(user_id)
    return f"@{m.display_name}" if m else f"@{user_id}"

def _display_role(guild: Optional[discord.Guild], role_id: int) -> str:
    if not guild:
        return f"@role:{role_id}"
    r = guild.get_role(role_id)
    return f"@{r.name}" if r else f"@role:{role_id}"

def _display_channel(guild: Optional[discord.Guild], channel_id: int) -> str:
    if not guild:
        return f"#channel:{channel_id}"
    c = guild.get_channel(channel_id)
    return f"#{c.name}" if c else f"#channel:{channel_id}"

def replace_mentions(text: str, guild: Optional[discord.Guild]) -> str:
    text = USER_MENTION_RE.sub(lambda m: _display_user(guild, int(m.group(1))), text)
    text = ROLE_MENTION_RE.sub(lambda m: _display_role(guild, int(m.group(1))), text)
    text = CHANNEL_MENTION_RE.sub(lambda m: _display_channel(guild, int(m.group(1))), text)
    return text

def sanitize(text: str, guild: Optional[discord.Guild]) -> str:
    text = replace_mentions(text, guild)
    esc = html.escape(text)
    esc = URL_RE.sub(r'<a href="\1">\1</a>', esc)
    return esc

# ================= メッセージHTML =================
def msg_to_html(m: discord.Message) -> str:
    author = m.author

    # ★ UTC → JST に変換
    jst_time = m.created_at.astimezone(TIMEZONE)
    time_str = jst_time.strftime(TIME_FORMAT)

    content = sanitize(m.content or "", m.guild)

    attach = ""
    if m.attachments:
        attach = "<div class='attach'>" + "".join(
            f"<img src='{a.url}'>" for a in m.attachments
            if a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
        ) + "</div>"

    return f"""
<div class="msg">
  <img class="avatar" src="{author.display_avatar.url}">
  <div>
    <div>
      <span class="author">{html.escape(author.display_name)}</span>
      <span class="time">{time_str} (JST)</span>
    </div>
    <div>{content}{attach}</div>
  </div>
</div>
"""

def make_filename(guild: str, channel: str) -> str:
    safe = lambda s: re.sub(r"[^\w\-]+", "_", s)
    return f"{safe(guild)}__{safe(channel)}__{datetime.now(TIMEZONE).strftime('%Y%m%d_%H%M%S')}.html"

# ================= Cog =================
class ExportHtmlCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="export")
    async def export(self, ctx: commands.Context, limit: int = DEFAULT_LIMIT):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.reply("テキストチャンネルで実行してください。")
            return

        if limit < 1:
            limit = 1
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        channel = ctx.channel
        guild_name = ctx.guild.name if ctx.guild else "DM"

        msgs = []
        async for m in channel.history(limit=limit, oldest_first=True):
            msgs.append(m)

        body = "\n".join(msg_to_html(m) for m in msgs)
        page = make_html_page(
            guild_name,
            channel.name,
            datetime.now(TIMEZONE).strftime(TIME_FORMAT),
            body
        )

        data = page.encode("utf-8")
        file = discord.File(fp=io.BytesIO(data), filename=make_filename(guild_name, channel.name))

        await ctx.send("✅ 日本時間（JST）でHTMLログを生成しました", file=file)

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
