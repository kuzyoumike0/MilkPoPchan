from __future__ import annotations

import html
import io
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# ================= 設定 =================
DEFAULT_LIMIT = 200
MAX_LIMIT = 5000

JST = ZoneInfo("Asia/Tokyo")
TIME_FORMAT = "%Y-%m-%d %H:%M"  # 例: 2025-12-21 10:05

# Discord添付上限対策（無料枠 8MB を想定して安全側）
SAFE_MAX_BYTES = 8 * 1024 * 1024 - 200_000

URL_RE = re.compile(r"(https?://[^\s]+)")

# Discordメンションの内部表現
USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")

# ================= HTML（Discord風UI） =================
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
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans JP",
      "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
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
  .filelink {{
    margin-top: 6px;
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
  .mention {{
    padding: 0 6px;
    border-radius: 6px;
    font-weight: 600;
    background: rgba(88,101,242,.18);
    color: #c9d4ff;
  }}
</style>
</head>
<body>
  <div class="app">
    <div class="header">
      <div class="title"><strong>{html.escape(guild_name)}</strong> / <strong>#{html.escape(channel_name)}</strong> のログ</div>
      <div class="meta">Exported at (JST): {html.escape(exported_at)}</div>
    </div>
    <div class="chat">
      {messages_html}
    </div>
  </div>
</body>
</html>
"""

# ================= メンション解決 =================
def _display_user(guild: Optional[discord.Guild], user_id: int) -> str:
    if not guild:
        return f"@{user_id}"
    member = guild.get_member(user_id)
    return f"@{member.display_name}" if member else f"@{user_id}"

def _display_role(guild: Optional[discord.Guild], role_id: int) -> str:
    if not guild:
        return f"@role:{role_id}"
    role = guild.get_role(role_id)
    return f"@{role.name}" if role else f"@role:{role_id}"

def _display_channel(guild: Optional[discord.Guild], channel_id: int) -> str:
    if not guild:
        return f"#channel:{channel_id}"
    ch = guild.get_channel(channel_id)
    return f"#{ch.name}" if ch else f"#channel:{channel_id}"

def replace_mentions_to_text(raw: str, guild: Optional[discord.Guild]) -> str:
    def repl_user(m: re.Match) -> str:
        return _display_user(guild, int(m.group(1)))

    def repl_role(m: re.Match) -> str:
        return _display_role(guild, int(m.group(1)))

    def repl_channel(m: re.Match) -> str:
        return _display_channel(guild, int(m.group(1)))

    out = USER_MENTION_RE.sub(repl_user, raw)
    out = ROLE_MENTION_RE.sub(repl_role, out)
    out = CHANNEL_MENTION_RE.sub(repl_channel, out)
    return out

def sanitize_to_html(raw: str, guild: Optional[discord.Guild]) -> str:
    # 1) メンションを @名前/#名前へ（数字のままにしない）
    text = replace_mentions_to_text(raw, guild)

    # 2) HTMLエスケープ
    esc = html.escape(text)

    # 3) URLリンク化
    esc = URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', esc)

    # 4) @xxx / #xxx を軽くハイライト（Discordっぽく）
    esc = re.sub(r'(?<![\w/])(@[^\s<]+)', r'<span class="mention">\1</span>', esc)
    esc = re.sub(r'(?<![\w/])(#\S+)', r'<span class="mention">\1</span>', esc)

    # 5) ``` ``` を簡易コード表示（雰囲気）
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

# ================= メッセージHTML =================
def msg_to_html(m: discord.Message) -> str:
    author = m.author
    avatar_url = author.display_avatar.url if author.display_avatar else ""
    author_name = author.display_name

    # ★ JSTで表示（投稿時刻）
    time_str = m.created_at.astimezone(JST).strftime(TIME_FORMAT)

    content_html = sanitize_to_html(m.content or "", m.guild)

    # 添付（画像はimg、その他はリンク）
    attach_imgs = []
    attach_files = []
    for a in m.attachments:
        is_img = (a.content_type or "").startswith("image/") or a.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp")
        )
        if is_img:
            attach_imgs.append(
                f'<a href="{html.escape(a.url)}" target="_blank" rel="noopener noreferrer">'
                f'<img src="{html.escape(a.url)}" alt="{html.escape(a.filename)}"></a>'
            )
        else:
            attach_files.append(
                f'<div class="filelink"><a href="{html.escape(a.url)}" target="_blank" rel="noopener noreferrer">'
                f'{html.escape(a.filename)}</a></div>'
            )

    attach_html = ""
    if attach_imgs or attach_files:
        attach_html = '<div class="attach">' + "".join(attach_imgs) + "</div>" + "".join(attach_files)

    # embed（タイトル＋説明だけ）
    embed_html = ""
    if m.embeds:
        e = m.embeds[0]
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
          <span class="time">{html.escape(time_str)} (JST)</span>
        </div>
        <div class="content">{content_html}{embed_html}{attach_html}</div>
      </div>
    </div>
    """

def make_filename(guild: str, channel: str) -> str:
    def safe(s: str) -> str:
        return re.sub(r"[^\w\-]+", "_", s)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    return f"{safe(guild)}__{safe(channel)}__{stamp}.html"

def readable_perm_error() -> str:
    return (
        "⚠️ そのチャンネルのログを読む権限が足りません。\n"
        "Botに以下の権限を付けてください：\n"
        "・View Channel（チャンネルを見る）\n"
        "・Read Message History（メッセージ履歴を読む）\n"
        "（HTMLを返すには Attach Files も必要）"
    )

# ================= Cog =================
class ExportHtmlCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="export")
    async def export(
        self,
        ctx: commands.Context,
        limit_or_channel: str | None = None,
        channel: discord.TextChannel | None = None,
    ):
        """
        使い方:
          !export                 -> 実行したチャンネルをDEFAULT件数で
          !export 300             -> 実行したチャンネルを300件
          !export #channel        -> 指定チャンネルをDEFAULT件数
          !export 300 #channel    -> 指定チャンネルを300件
        """
        # ---- 引数解釈 ----
        limit = DEFAULT_LIMIT
        target: discord.TextChannel | None = None

        if limit_or_channel is None:
            target = ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None
        else:
            if limit_or_channel.isdigit():
                limit = int(limit_or_channel)
                target = channel if channel else (ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None)
            else:
                # 1つ目がチャンネル指定
                target = channel
                if target is None:
                    m = re.match(r"<#(\d+)>", limit_or_channel)
                    if m and ctx.guild:
                        ch = ctx.guild.get_channel(int(m.group(1)))
                        if isinstance(ch, discord.TextChannel):
                            target = ch
                if target is None:
                    target = ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None

        if not isinstance(target, discord.TextChannel):
            await ctx.reply("テキストチャンネルで実行してください。例：`!export` / `!export 300` / `!export #general`")
            return

        # limit調整
        if limit < 1:
            limit = 1
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        # ---- 権限チェック（Botが読めるか）----
        perms = target.permissions_for(target.guild.me) if target.guild and target.guild.me else None
        if perms is None or not (perms.view_channel and perms.read_message_history):
            await ctx.reply(readable_perm_error())
            return
        if not perms.attach_files:
            await ctx.reply("⚠️ Botに Attach Files（ファイル添付）の権限がありません。HTMLを添付できません。")
            return

        guild_name = ctx.guild.name if ctx.guild else "DM"
        filename = make_filename(guild_name, target.name)

        # ---- HTML生成（サイズ超過なら件数を減らす）----
        current = limit
        while True:
            msgs: list[discord.Message] = []
            try:
                async for m in target.history(limit=current, oldest_first=True):
                    msgs.append(m)
            except discord.Forbidden:
                await ctx.reply(readable_perm_error())
                return

            messages_html = "\n".join(msg_to_html(m) for m in msgs)
            page = make_html_page(
                guild_name=guild_name,
                channel_name=target.name,
                exported_at=datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                messages_html=messages_html,
            )
            data = page.encode("utf-8")

            if len(data) <= SAFE_MAX_BYTES:
                file = discord.File(fp=io.BytesIO(data), filename=filename)
                await ctx.send(f"✅ HTMLログを生成しました（対象: #{target.name} / {current}件）", file=file)
                return

            if current <= 50:
                await ctx.send("⚠️ HTMLが大きすぎて添付できません。件数を減らして `!export 100` などで試してください。")
                return

            current = max(50, current // 2)

# load_extension の入口（必須）
async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
