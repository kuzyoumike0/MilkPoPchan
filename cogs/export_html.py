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

# =====================
# HTMLテンプレ
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
  border: 1px solid var(--border);
}}

.author {{ color: var(--name); font-weight: 700; }}
.time {{ color: var(--muted); font-size: 12px; margin-left: 6px; }}

.content {{
  margin-top: 4px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}}

a {{ color: var(--link); }}

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

h1 {{ font-size: 1.6em; margin: 6px 0; }}
h2 {{ font-size: 1.4em; margin: 6px 0; }}
h3 {{ font-size: 1.2em; margin: 6px 0; }}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="title"><strong>{html.escape(guild_name)}</strong> / <strong>#{html.escape(channel_name)}</strong></div>
    <div class="meta">Exported at: {exported_at}（JST）</div>
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
    m = guild.get_member(user_id)
    return f"@{m.display_name}" if m else ""

def sanitize(text: str, guild: discord.Guild | None) -> str:
    text = USER_MENTION_RE.sub(lambda m: _display_user(guild, int(m.group(1))), text)

    lines = []
    for line in text.splitlines():
        if line.startswith("### "):
            lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        else:
            esc = html.escape(line)
            esc = URL_RE.sub(r'<a href="\\1" target="_blank">\\1</a>', esc)
            esc = esc.replace("@everyone", '<span class="mention-ping">@everyone</span>')
            esc = esc.replace("@here", '<span class="mention-ping">@here</span>')
            esc = re.sub(r'(@[^\s<]+)', r'<span class="mention">\1</span>', esc)
            lines.append(esc)

    return "<br>".join(lines)

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
    <div>
      <span class="author">{html.escape(m.author.display_name)}</span>
      <span class="time">{time_jst}</span>
    </div>
    <div class="content">{content}</div>
  </div>
</div>
"""

# =====================
# Cog
# =====================
class ExportHtmlCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="export")
    async def export(self, ctx: commands.Context, limit: int = DEFAULT_LIMIT):
        if not isinstance(ctx.channel, discord.TextChannel):
            return

        if ctx.guild:
            try:
                await asyncio.wait_for(ctx.guild.chunk(cache=True), timeout=5)
            except Exception:
                pass

        msgs = []
        async for m in ctx.channel.history(limit=min(limit, MAX_LIMIT), oldest_first=True):
            msgs.append(m)

        html_msgs = "\n".join(msg_to_html(m) for m in msgs)

        page = make_html_page(
            ctx.guild.name if ctx.guild else "DM",
            ctx.channel.name,
            datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
            html_msgs,
        )

        data = page.encode("utf-8")
        file = discord.File(io.BytesIO(data), filename=f"{ctx.channel.name}.html")
        await ctx.send("✅ HTMLログを生成しました", file=file)

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
