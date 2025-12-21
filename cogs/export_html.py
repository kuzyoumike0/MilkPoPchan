from __future__ import annotations

import asyncio
import html
import io
import re
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands

# =====================
# 日本時間（JST）
# =====================
JST = timezone(timedelta(hours=9))

DEFAULT_LIMIT = 200
MAX_LIMIT = 5000
TIME_FORMAT = "%Y-%m-%d %H:%M"

SAFE_MAX_BYTES = 8 * 1024 * 1024 - 200_000
URL_RE = re.compile(r"(https?://[^\s]+)")

USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")

# =====================
# HTML生成
# =====================
def make_html_page(guild_name: str, channel_name: str, exported_at: str, messages_html: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(guild_name)} - #{html.escape(channel_name)}</title>
<style>
  :root {{
    --bg: #313338;
    --panel: #2b2d31;
    --text: #dbdee1;
    --muted: #949ba4;
    --name: #f2f3f5;
    --border: rgba(255,255,255,.06);
    --link: #00a8fc;

    --mention-bg: rgba(88,101,242,.18);
    --mention-fg: #c9d4ff;

    --ping-bg: rgba(250,166,26,.20);
    --ping-fg: #ffd59a;
  }}

  body {{
    margin: 0;
    background: #1e1f22;
    color: var(--text);
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans JP",
      "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
  }}

  .app {{ max-width: 1100px; margin: 0 auto; padding: 24px 12px; }}

  .header {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 12px;
  }}

  .title {{ font-size: 14px; color: var(--muted); }}
  .title strong {{ color: var(--name); font-weight: 700; }}
  .meta {{ font-size: 12px; margin-top: 6px; color: var(--muted); }}

  .chat {{
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }}

  .msg {{
    display: grid;
    grid-template-columns: 44px 1fr;
    gap: 12px;
    padding: 10px 16px;
    border-top: 1px solid var(--border);
  }}
  .msg:first-child {{ border-top: none; }}

  .avatar {{
    width: 40px;
    height: 40px;
    border-radius: 999px;
    object-fit: cover;
    background: #111;
    border: 1px solid var(--border);
  }}

  .line1 {{ display: flex; align-items: baseline; gap: 8px; }}
  .author {{ color: var(--name); font-weight: 700; font-size: 14px; }}
  .time {{ color: var(--muted); font-size: 12px; }}

  .content {{
    margin-top: 2px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }}

  a {{ color: var(--link); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  .mention {{
    background: var(--mention-bg);
    color: var(--mention-fg);
    padding: 0 6px;
    border-radius: 6px;
    font-weight: 600;
  }}

  .mention-ping {{
    background: var(--ping-bg);
    color: var(--ping-fg);
    padding: 0 6px;
    border-radius: 6px;
    font-weight: 800;
  }}
</style>
</head>
<body>
  <div class="app">
    <div class="header">
      <div class="title"><strong>{html.escape(guild_name)}</strong> / <strong>#{html.escape(channel_name)}</strong> のログ</div>
      <div class="meta">Exported at: {html.escape(exported_at)}（JST）</div>
    </div>
    <div class="chat">
      {messages_html}
    </div>
  </div>
</body>
</html>
"""

# =====================
# メンション変換
# =====================
def _display_user(guild: discord.Guild | None, user_id: int) -> str:
    if not guild:
        return ""
    member = guild.get_member(user_id)
    return f"@{member.display_name}" if member else ""

def replace_discord_mentions_to_names(raw: str, guild: discord.Guild | None) -> str:
    raw = USER_MENTION_RE.sub(lambda m: _display_user(guild, int(m.group(1))), raw)
    return raw

def sanitize(text: str, guild: discord.Guild | None) -> str:
    text = replace_discord_mentions_to_names(text, guild)
    esc = html.escape(text)

    esc = URL_RE.sub(r'<a href="\\1" target="_blank">\\1</a>', esc)
    esc = esc.replace("@everyone", '<span class="mention-ping">@everyone</span>')
    esc = esc.replace("@here", '<span class="mention-ping">@here</span>')
    esc = re.sub(r'(@[^\s<]+)', r'<span class="mention">\1</span>', esc)

    return esc

# =====================
# メッセージHTML
# =====================
def msg_to_html(m: discord.Message) -> str:
    time_jst = m.created_at.astimezone(JST).strftime(TIME_FORMAT)

    content = sanitize(m.content or "", m.guild)

    return f"""
    <div class="msg">
      <img class="avatar" src="{html.escape(m.author.display_avatar.url)}">
      <div>
        <div class="line1">
          <span class="author">{html.escape(m.author.display_name)}</span>
          <span class="time">{time_jst}</span>
        </div>
        <div class="content">{content}</div>
      </div>
    </div>
    """

# =====================
# ファイル名
# =====================
def make_filename(channel_name: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", channel_name)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    return f"{safe}__{stamp}.html"

# =====================
# Cog
# =====================
class ExportHtmlCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="export")
    async def export(self, ctx: commands.Context, limit: int = DEFAULT_LIMIT):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.reply("テキストチャンネルで実行してください。")
            return

        channel = ctx.channel
        limit = max(1, min(limit, MAX_LIMIT))

        if ctx.guild:
            try:
                await asyncio.wait_for(ctx.guild.chunk(cache=True), timeout=5.0)
            except Exception:
                pass

        messages = []
        async for m in channel.history(limit=limit, oldest_first=True):
            messages.append(m)

        messages_html = "\n".join(msg_to_html(m) for m in messages)

        page = make_html_page(
            guild_name=ctx.guild.name if ctx.guild else "DM",
            channel_name=channel.name,
            exported_at=datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
            messages_html=messages_html,
        )

        data = page.encode("utf-8")
        file = discord.File(io.BytesIO(data), filename=make_filename(channel.name))
        await ctx.send("✅ HTMLログを生成しました（JST）", file=file)

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
