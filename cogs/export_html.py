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

SAFE_MAX_BYTES = 8 * 1024 * 1024 - 200_000  # 8MB未満に収める安全値（Nitro無し想定）

# URLは「URL文字列を表示したまま」クリックできるようにする
URL_RE = re.compile(r"(https?://[^\s<>()\]\}]+)")

# Discord内部メンション表現
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")

# インライン装飾（コードブロック外で適用）
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
UNDERLINE_RE = re.compile(r"__(.+?)__")        # ★ 追加：アンダーライン
STRIKE_RE = re.compile(r"~~(.+?)~~")
# italic は *text* と _text_（bold/underlineと衝突しないように後段で処理）
ITALIC_ASTER_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
ITALIC_UNDER_RE = re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")

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

    --code-bg: rgba(0,0,0,.22);
    --code-border: rgba(255,255,255,.08);

    --react-bg: rgba(255,255,255,.06);
    --react-border: rgba(255,255,255,.10);
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
    line-height: 1.55;
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

  /* 見出し */
  .h1 {{ font-size: 20px; font-weight: 900; margin: 8px 0 6px; }}
  .h2 {{ font-size: 18px; font-weight: 850; margin: 8px 0 6px; }}
  .h3 {{ font-size: 16px; font-weight: 800; margin: 8px 0 6px; }}

  /* コードブロック */
  pre.codeblock {{
    margin: 8px 0 6px;
    padding: 10px 12px;
    background: var(--code-bg);
    border: 1px solid var(--code-border);
    border-radius: 10px;
    overflow-x: auto;
  }}
  pre.codeblock code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--text);
  }}
  .lang {{
    display: inline-block;
    margin: 6px 0 0;
    font-size: 11px;
    color: var(--muted);
  }}

  /* 添付 */
  .attach {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 8px; }}
  .attach img {{
    max-width: 360px;
    max-height: 240px;
    border-radius: 10px;
    border: 1px solid var(--border);
    object-fit: cover;
  }}
  .filelink {{
    margin-top: 6px;
    font-size: 13px;
  }}

  /* リアクション */
  .reactions {{
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }}
  .reaction {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--react-bg);
    border: 1px solid var(--react-border);
    font-size: 12px;
    color: var(--text);
  }}
  .reaction img {{
    width: 16px;
    height: 16px;
  }}
  .reaction .count {{
    color: var(--muted);
    font-weight: 700;
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

def _display_user(guild: discord.Guild | None, user_id: int) -> str:
    if not guild:
        return ""
    m = guild.get_member(user_id)
    return f"@{m.display_name}" if m else ""

def _display_role(guild: discord.Guild | None, role_id: int) -> str:
    role = guild.get_role(role_id) if guild else None
    return f"@{role.name}" if role else "@ロール"

def _display_channel(guild: discord.Guild | None, channel_id: int) -> str:
    ch = guild.get_channel(channel_id) if guild else None
    return f"#{ch.name}" if ch else "#チャンネル"

def replace_discord_mentions_to_names(raw: str, guild: discord.Guild | None) -> str:
    raw = USER_MENTION_RE.sub(lambda m: _display_user(guild, int(m.group(1))), raw)
    raw = ROLE_MENTION_RE.sub(lambda m: _display_role(guild, int(m.group(1))), raw)
    raw = CHANNEL_MENTION_RE.sub(lambda m: _display_channel(guild, int(m.group(1))), raw)
    return raw

def linkify_escaped(escaped_text: str) -> str:
    return URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', escaped_text)

def apply_inline_formatting(escaped_text: str) -> str:
    escaped_text = escaped_text.replace("@everyone", '<span class="mention-ping">@everyone</span>')
    escaped_text = escaped_text.replace("@here", '<span class="mention-ping">@here</span>')

    escaped_text = linkify_escaped(escaped_text)

    # 太字 → 下線 → 打ち消し → 斜体 の順（Discordに近い見え方）
    escaped_text = BOLD_RE.sub(r"<strong>\1</strong>", escaped_text)
    escaped_text = UNDERLINE_RE.sub(r"<u>\1</u>", escaped_text)
    escaped_text = STRIKE_RE.sub(r"<del>\1</del>", escaped_text)
    escaped_text = ITALIC_ASTER_RE.sub(r"<em>\1</em>", escaped_text)
    escaped_text = ITALIC_UNDER_RE.sub(r"<em>\1</em>", escaped_text)

    escaped_text = re.sub(r'(?<!<)(?<![\w/])(@[^\s<]+)', r'<span class="mention">\1</span>', escaped_text)
    escaped_text = re.sub(r'(?<!<)(?<![\w/])(#\S+)', r'<span class="mention">\1</span>', escaped_text)

    return escaped_text

def render_discord_markdown(raw_text: str, guild: discord.Guild | None) -> str:
    raw_text = replace_discord_mentions_to_names(raw_text, guild)
    parts = raw_text.split("```")
    out: list[str] = []

    for i, part in enumerate(parts):
        if i % 2 == 1:
            lang = ""
            code = part
            if "\n" in code:
                first, rest = code.split("\n", 1)
                if len(first) <= 20 and re.fullmatch(r"[A-Za-z0-9_+\-#.]+", first.strip() or ""):
                    lang = first.strip()
                    code = rest
            out.append(
                f'<pre class="codeblock"><code>{html.escape(code)}</code></pre>'
                f'{f"<div class=\\"lang\\">{html.escape(lang)}</div>" if lang else ""}'
            )
        else:
            lines = part.splitlines() or [""]
            rendered: list[str] = []
            for line in lines:
                if line.startswith("### "):
                    rendered.append(f'<div class="h3">{html.escape(line[4:])}</div>')
                elif line.startswith("## "):
                    rendered.append(f'<div class="h2">{html.escape(line[3:])}</div>')
                elif line.startswith("# "):
                    rendered.append(f'<div class="h1">{html.escape(line[2:])}</div>')
                else:
                    esc = html.escape(line)
                    rendered.append(apply_inline_formatting(esc))
            out.append("<br>".join(rendered))

    return "".join(out)

def reactions_to_html(message: discord.Message) -> str:
    if not message.reactions:
        return ""
    pills = []
    for r in message.reactions:
        emoji = r.emoji
        if isinstance(emoji, discord.PartialEmoji) and emoji.id:
            pills.append(
                f'<span class="reaction"><img src="{html.escape(str(emoji.url))}">'
                f'<span class="count">{r.count}</span></span>'
            )
        else:
            pills.append(
                f'<span class="reaction"><span>{html.escape(str(emoji))}</span>'
                f'<span class="count">{r.count}</span></span>'
            )
    return f'<div class="reactions">{"".join(pills)}</div>'

def attachments_to_html(message: discord.Message) -> str:
    if not message.attachments:
        return ""
    imgs, files = [], []
    for a in message.attachments:
        is_img = (a.content_type or "").startswith("image/") or a.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp")
        )
        if is_img:
            imgs.append(f'<a href="{html.escape(a.url)}" target="_blank"><img src="{html.escape(a.url)}"></a>')
        else:
            files.append(f'<div class="filelink"><a href="{html.escape(a.url)}" target="_blank">{html.escape(a.filename)}</a></div>')
    return (f'<div class="attach">{"".join(imgs)}</div>' if imgs else "") + "".join(files)

def msg_to_html(m: discord.Message) -> str:
    return f"""
    <div class="msg">
      <img class="avatar" src="{html.escape(m.author.display_avatar.url)}">
      <div>
        <div class="line1">
          <span class="author">{html.escape(m.author.display_name)}</span>
          <span class="time">{m.created_at.astimezone(JST).strftime(TIME_FORMAT)}</span>
        </div>
        <div class="content">
          {render_discord_markdown(m.content or "", m.guild)}
          {attachments_to_html(m)}
          {reactions_to_html(m)}
        </div>
      </div>
    </div>
    """

def make_filename(channel_name: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", channel_name)
    return f"{safe}__{datetime.now(JST).strftime('%Y%m%d_%H%M%S')}.html"

class ExportHtmlCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="export")
    async def export(self, ctx: commands.Context, limit: int = DEFAULT_LIMIT):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.reply("テキストチャンネルで実行してください。")
            return

        limit = max(1, min(limit, MAX_LIMIT))

        if ctx.guild:
            try:
                await asyncio.wait_for(ctx.guild.chunk(cache=True), timeout=5)
            except Exception:
                pass

        msgs = []
        async for m in ctx.channel.history(limit=limit, oldest_first=True):
            msgs.append(m)

        page = make_html_page(
            ctx.guild.name if ctx.guild else "DM",
            ctx.channel.name,
            datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
            "\n".join(msg_to_html(m) for m in msgs),
        )

        data = page.encode("utf-8")
        await ctx.send(
            "✅ HTMLログを生成しました",
            file=discord.File(io.BytesIO(data), filename=make_filename(ctx.channel.name)),
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
