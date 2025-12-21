import os
import html
import re
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands

# ========= 設定 =========
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

DEFAULT_LIMIT = 200  # 取得する最大件数（/export の引数で変更可）
TIME_FORMAT = "%Y-%m-%d %H:%M"

# Discordのメンション等を軽くHTML化する（最小限）
URL_RE = re.compile(r"(https?://[^\s]+)")

# ========= Discordクライアント =========
intents = discord.Intents.default()
intents.message_content = True  # 本文取得に必要
intents.members = True

class ExportBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = ExportBot()

# ========= HTMLテンプレ =========
def make_html_page(guild_name: str, channel_name: str, exported_at: str, messages_html: str) -> str:
    # “Discordっぽさ”を出すCSS（完全再現ではなく雰囲気寄せ）
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(guild_name)} - #{html.escape(channel_name)} (export)</title>
<style>
  :root {{
    --bg: #313338;         /* chat area */
    --panel: #2b2d31;      /* header-like */
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
    # HTMLエスケープ
    esc = html.escape(text)

    # URLをリンク化
    esc = URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', esc)

    # ``` のコードブロックっぽい表示（簡易）
    # 完璧なMarkdownパーサは入れず、雰囲気重視
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

def message_to_html(msg: discord.Message) -> str:
    author = msg.author
    avatar_url = author.display_avatar.url if author.display_avatar else ""
    author_name = author.display_name

    # 時刻（ローカル表示したければここで変換）
    created = msg.created_at.replace(tzinfo=timezone.utc)
    time_str = created.astimezone().strftime(TIME_FORMAT)

    content_html = sanitize_content(msg.content or "")

    # 添付（画像ならimg表示、その他はリンク）
    attach_html = ""
    if msg.attachments:
        imgs = []
        links = []
        for a in msg.attachments:
            if (a.content_type or "").startswith("image/") or a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                imgs.append(f'<a href="{html.escape(a.url)}" target="_blank" rel="noopener noreferrer"><img src="{html.escape(a.url)}" alt="{html.escape(a.filename)}"></a>')
            else:
                links.append(f'<div><a href="{html.escape(a.url)}" target="_blank" rel="noopener noreferrer">{html.escape(a.filename)}</a></div>')
        if imgs or links:
            attach_html = '<div class="attach">' + "".join(imgs) + "</div>" + "".join(links)

    # 埋め込み（タイトルと説明だけ軽く）
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

@client.event
async def on_ready():
    print(f"Logged in as: {client.user} (id={client.user.id})")

# ========= スラッシュコマンド =========
@client.tree.command(name="export", description="指定チャンネルのログをDiscord風HTMLに出力します")
@app_commands.describe(
    channel="ログを出力したいチャンネル",
    limit="取得件数（最大2000程度を推奨）"
)
async def export(interaction: discord.Interaction, channel: discord.TextChannel, limit: int = DEFAULT_LIMIT):
    await interaction.response.defer(thinking=True, ephemeral=True)

    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000

    # メッセージ取得（古い→新しい順にするため一旦逆順）
    msgs = []
    async for m in channel.history(limit=limit, oldest_first=True):
        msgs.append(m)

    messages_html = "\n".join(message_to_html(m) for m in msgs)

    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    page = make_html_page(
        guild_name=interaction.guild.name if interaction.guild else "DM",
        channel_name=channel.name,
        exported_at=exported_at,
        messages_html=messages_html
    )

    # ファイル保存
    safe_guild = re.sub(r"[^\w\-]+", "_", (interaction.guild.name if interaction.guild else "DM"))
    safe_channel = re.sub(r"[^\w\-]+", "_", channel.name)
    fname = f"{safe_guild}__{safe_channel}__{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path = EXPORT_DIR / fname
    path.write_text(page, encoding="utf-8")

    await interaction.followup.send(
        content=f"✅ HTMLを書き出しました: `{path.as_posix()}`\n（このBotが動いている環境の `exports/` フォルダに保存されています）",
        ephemeral=True
    )

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("環境変数 DISCORD_TOKEN が設定されていません。")
    client.run(token)

if __name__ == "__main__":
    main()
