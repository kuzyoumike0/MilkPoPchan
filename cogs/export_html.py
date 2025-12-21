from __future__ import annotations

import html
import io
import re
from datetime import datetime

import discord
from discord.ext import commands

DEFAULT_LIMIT = 200
MAX_LIMIT = 5000
TIME_FORMAT = "%Y-%m-%d %H:%M"

SAFE_MAX_BYTES = 8 * 1024 * 1024 - 200_000  # 8MB未満に収める安全値
URL_RE = re.compile(r"(https?://[^\s]+)")

# Discord内部メンション表現
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")


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

    /* 通常メンション */
    --mention-bg: rgba(88,101,242,.18);
    --mention-fg: #c9d4ff;

    /* @everyone/@here 専用 */
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

  .attach {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 8px; }}
  .attach img {{
    max-width: 360px;
    max-height: 240px;
    border-radius: 10px;
    border: 1px solid var(--border);
    object-fit: cover;
  }}

  /* 通常メンション（@表示名 / #チャンネル / @ロールなど） */
  .mention {{
    background: var(--mention-bg);
    color: var(--mention-fg);
    padding: 0 6px;
    border-radius: 6px;
    font-weight: 600;
  }}

  /* @everyone / @here 専用 */
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
      <div class="meta">Exported at: {html.escape(exported_at)}</div>
    </div>
    <div class="chat">
      {messages_html}
    </div>
  </div>
</body>
</html>
"""


def _display_user(guild: discord.Guild | None, user_id: int) -> str:
    """
    <@id> / <@!id> を @表示名 に変換。
    サーバー内にいればオフラインでも表示名にする（guild.chunk後は get_member で取れる想定）。
    取れない場合は「表示しない」（空文字）。IDは出さない。
    """
    if not guild:
        return ""

    member = guild.get_member(user_id)
    if member:
        return f"@{member.display_name}"

    return ""


def _display_role(guild: discord.Guild | None, role_id: int) -> str:
    if not guild:
        return "@ロール"
    role = guild.get_role(role_id)
    return f"@{role.name}" if role else "@ロール"


def _display_channel(guild: discord.Guild | None, channel_id: int) -> str:
    if not guild:
        return "#チャンネル"
    ch = guild.get_channel(channel_id)
    return f"#{ch.name}" if ch else "#チャンネル"


def replace_discord_mentions_to_names(raw: str, guild: discord.Guild | None) -> str:
    raw = USER_MENTION_RE.sub(lambda m: _display_user(guild, int(m.group(1))), raw)
    raw = ROLE_MENTION_RE.sub(lambda m: _display_role(guild, int(m.group(1))), raw)
    raw = CHANNEL_MENTION_RE.sub(lambda m: _display_channel(guild, int(m.group(1))), raw)
    return raw


def sanitize(text: str, guild: discord.Guild | None) -> str:
    # 1) Discord内部メンションを表示名へ（取れないユーザーは空文字）
    text = replace_discord_mentions_to_names(text, guild)

    # 2) 連続スペースだけ軽く詰める（空文字化で崩れた時の見た目対策）
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 3) HTMLエスケープ
    esc = html.escape(text)

    # 4) URLリンク化（元仕様維持：\1を文字列として使う）
    esc = URL_RE.sub(r'<a href="\\1" target="_blank" rel="noopener noreferrer">\\1</a>', esc)

    # 5) @everyone / @here を専用色
    esc = esc.replace("@everyone", '<span class="mention-ping">@everyone</span>')
    esc = esc.replace("@here", '<span class="mention-ping">@here</span>')

    # 6) 通常メンション色（@表示名 / @ロール / #チャンネル 等）
    esc = re.sub(r'(?<!<)(?<![\w/])(@[^\s<]+)', r'<span class="mention">\1</span>', esc)
    esc = re.sub(r'(?<!<)(?<![\w/])(#\S+)', r'<span class="mention">\1</span>', esc)

    return esc


def msg_to_html(m: discord.Message) -> str:
    author = m.author
    avatar_url = author.display_avatar.url if author.display_avatar else ""
    author_name = author.display_name
    time_str = m.created_at.astimezone().strftime(TIME_FORMAT)

    content = sanitize(m.content or "", m.guild)

    attach_html = ""
    if m.attachments:
        imgs: list[str] = []
        files: list[str] = []
        for a in m.attachments:
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

    return f"""
    <div class="msg">
      <img class="avatar" src="{html.escape(avatar_url)}" alt="avatar">
      <div>
        <div class="line1">
          <span class="author">{html.escape(author_name)}</span>
          <span class="time">{html.escape(time_str)}</span>
        </div>
        <div class="content">{content}{attach_html}</div>
      </div>
    </div>
    """


def make_filename(channel_name: str) -> str:
    def safe(s: str) -> str:
        return re.sub(r"[^\w\-]+", "_", s)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe(channel_name)}__{stamp}.html"


class ExportHtmlCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="export")
    async def export(self, ctx: commands.Context, limit: int = DEFAULT_LIMIT):
        """!export [件数]：実行したチャンネルのログをHTMLにして添付で返す"""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.reply("テキストチャンネルで実行してください。")
            return

        channel: discord.TextChannel = ctx.channel

        if limit < 1:
            limit = 1
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        # ★重要：オフライン含むメンバーをキャッシュへ（Members Intent が有効な場合に効く）
        if ctx.guild is not None:
            try:
                await ctx.guild.chunk(cache=True)
            except discord.Forbidden:
                # chunkに失敗しても export 自体は続行（取れた分だけメンション名にする）
                pass

        guild_name = ctx.guild.name if ctx.guild else "DM"
        filename = make_filename(channel.name)

        # サイズ超過なら自動で件数を減らす
        current = limit
        while True:
            msgs: list[discord.Message] = []
            async for m in channel.history(limit=current, oldest_first=True):
                msgs.append(m)

            messages_html = "\n".join(msg_to_html(m) for m in msgs)
            page = make_html_page(
                guild_name=guild_name,
                channel_name=channel.name,
                exported_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                messages_html=messages_html,
            )
            data = page.encode("utf-8")

            if len(data) <= SAFE_MAX_BYTES:
                file = discord.File(fp=io.BytesIO(data), filename=filename)
                await ctx.send(f"✅ HTMLログを生成しました（{current}件）", file=file)
                return

            if current <= 50:
                await ctx.send("⚠️ HTMLが大きすぎて添付できません。`!export 100` など件数を減らして試してください。")
                return

            current = max(50, current // 2)


async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
