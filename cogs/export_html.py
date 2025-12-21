from __future__ import annotations

import html
import re
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

DEFAULT_LIMIT = 200
MAX_LIMIT = 2000
TIME_FORMAT = "%Y-%m-%d %H:%M"

URL_RE = re.compile(r"(https?://[^\s]+)")

def make_html_page(guild_name: str, channel_name: str, exported_at: str, messages_html: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(guild_name)} - #{html.escape(channel_name)} (export)</title>
<style>
  :root {{
    --bg: #313338;
    --panel: #2b2d31;
    --text: #dbdee1;
    --muted: #949ba4;
    --name: #f2f3f5;
    --border: rgba(255,255,255,.06);
    --link: #00a8fc;
    --code: #1e1f22;
  }}
  body {{
    margin: 0;
    background: #1e1f22;
    color: var(--text);
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans JP", "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
  }}
  .app {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px 12px;
  }}
  .header {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 12px;
  }}
  .title {{
    font-size: 14px;
    color: var(--muted);
  }}
  .title strong {{
    color: var(--name);
    font-weight: 700;
  }}
  .meta {{
    font-size: 12px;
    margin-top: 6px;
    color: var(--muted);
  }}
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
  .msg:first-child {{
    border-top: none;
  }}
  .avatar {{
    width: 40px;
    height: 40px;
    border-radius: 999px;
    object-fit: cover;
    background: #111;
    border: 1px solid var(--border);
  }}
  .line1 {{
    display: flex;
    align-items: baseline;
    gap: 8px;
  }}
  .author {{
    color: var(--name);
    font-weight: 700;
    font-size: 14px;
  }}
  .time {{
    color: var(--muted);
    font-size: 12px;
  }}
  .content {{
    margin-top: 2px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  a {{
    color: var(--link);
    text-decoration: none;
  }}
  a:hover {{ text-decoration: underline; }}
  .attach {{
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .attach img {{
    max-width: 360px;
    max-height: 240px;
    border-radius: 10px;
    border: 1px solid var(--border);
    object-fit: cover;
  }}
  .embed {{
    margin-top: 8px;
    padding: 10px 12px;
    border-left: 4px solid rgba(88,101,242,.9);
    background: rgba(0,0,0,.15);
    border-radius: 8px;
  }}
  .embed .etitle {{
    font-weight: 700;
    margin-bottom: 4px;
  }}
  .code {{
    background: var(--code);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 12px;
    margin-top: 6px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 13px;
    white-space: pre-wrap;
  }}
</style>
</head>
<body>
  <div class="app">
    <div class="header">
      <div class="title"><strong>{html.escape(guild_name)}</strong> / <strong>#{html.escape(channel_name)}</strong> のログ</div>
      <div class="meta">Exported at: {html.escape(exported_at)}</div>
    </div>
    <div class="chat">
      {messages_html}
    </div>
  </div>
</body>
</html>
"""

def sanitize_content(text: str) -> str:
    esc = html.escape(text)

    # URLリンク化
    esc = URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', esc)

    # ``` ``` を簡易コード表示（雰囲気重視）
    if "```" in esc:
        parts = esc.split("```")
        out = []
        for i, p in enumerate(parts):
            if i % 2 == 1:
                out.append(f'<div class="code">{p}</div>')
            else:
                out.append(p)
        esc = "".join(out)

    return esc

def safe_filename(s: str) -> str:
    # Windows/UNIXで危ない文字をざっくり潰す
    return re.sub(r"[^\w\-]+", "_", s)

def message_to_html(msg: discord.Message) -> str:
    author = msg.author
    avatar_url = author.display_avatar.url if author.display_avatar else ""
    author_name = author.display_name

    created = msg.created_at.replace(tzinfo=timezone.utc)
    time_str = created.astimezone().strftime(TIME_FORMAT)

    content_html = sanitize_content(msg.content or "")

    # 添付（画像はimg、その他はリンク）
    attach_html = ""
    if msg.attachments:
        imgs = []
        files = []
        for a in msg.attachments:
            is_img = (a.content_type or "").startswith("image/") or a.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            )
            if is_img:
                imgs.append(
                    f'<a href="{html.escape(a.url)}" target="_blank" rel="noopener noreferrer">'
                    f'<img src="{html.escape(a.url)}" alt="{html.escape(a.filename)}"></a>'
                )
            else:
                files.append(
                    f'<div><a href="{html.escape(a.url)}" target="_blank" rel="noopener noreferrer">'
                    f'{html.escape(a.filename)}</a></div>'
                )

        if imgs or files:
            attach_html = '<div class="attach">' + "".join(imgs) + "</div>" + "".join(files)

    # embed（タイトル＋説明だけ）
    embed_html = ""
    if msg.embeds:
        e = msg.embeds[0]
        et = html.escape(e.title) if e.title else ""
        ed = html.escape(e.description) if e.description else ""
        if et or ed:
            embed_html = f"""
            <div class="embed">
              {f'<div class="etitle">{et}</div>' if et else ''}
              {f'<div class="edesc">{ed}</div>' if ed else ''}
            </div>
            """

    return f"""
    <div class="msg">
      <img class="avatar" src="{html.escape(avatar_url)}" alt="avatar">
      <div>
        <div class="line1">
          <span class="author">{html.escape(author_name)}</span>
          <span class="time">{html.escape(time_str)}</span>
        </div>
        <div class="content">{content_html}{embed_html}{attach_html}</div>
      </div>
    </div>
    """

class ExportHtmlCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="export", description="指定チャンネルのログをDiscord風HTMLに出力します")
    @app_commands.describe(
        channel="ログを出力したいチャンネル",
        limit="取得件数（1〜2000）"
    )
    async def export(self, interaction: discord.Interaction, channel: discord.TextChannel, limit: int = DEFAULT_LIMIT):
        # 権限チェック：メッセージ履歴を読む
        if not channel.permissions_for(interaction.user).read_message_history:
            await interaction.response.send_message("このチャンネルの履歴を読む権限がありません。", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        if limit < 1:
            limit = 1
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        msgs: list[discord.Message] = []
        async for m in channel.history(limit=limit, oldest_first=True):
            msgs.append(m)

        messages_html = "\n".join(message_to_html(m) for m in msgs)

        guild_name = interaction.guild.name if interaction.guild else "DM"
        exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        page = make_html_page(
            guild_name=guild_name,
            channel_name=channel.name,
            exported_at=exported_at,
            messages_html=messages_html,
        )

        fname = f"{safe_filename(guild_name)}__{safe_filename(channel.name)}__{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path = EXPORT_DIR / fname
        path.write_text(page, encoding="utf-8")

        await interaction.followup.send(
            content=f"✅ HTMLを書き出しました: `{path.as_posix()}`\n"
                    f"（Railway上のファイルなので、必要なら『Discordに添付して返す』方式に変更できます）",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
