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
STRIKE_RE = re.compile(r"~~(.+?)~~")
# italic は *text* と _text_（boldと衝突しないように先にbold処理する）
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

  /* 見出し（Discordっぽく大文字見出し感） */
  .h1 {{ font-size: 20px; font-weight: 900; letter-spacing: .2px; margin: 8px 0 6px; }}
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
    vertical-align: middle;
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
    """在籍ユーザー（オフライン含む）なら @表示名。取れない場合は表示しない。IDは出さない。"""
    if not guild:
        return ""
    m = guild.get_member(user_id)
    return f"@{m.display_name}" if m else ""

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

def linkify_escaped(escaped_text: str) -> str:
    # ✅ ここが重要：\1（グループ参照）でURLを表示する
    return URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', escaped_text)

def apply_inline_formatting(escaped_text: str) -> str:
    """
    すでに html.escape 済みのテキストに対して、Discordっぽい装飾をHTMLに変換。
    ※ コードブロック外にしか呼ばれない前提
    """
    # @everyone / @here を専用色
    escaped_text = escaped_text.replace("@everyone", '<span class="mention-ping">@everyone</span>')
    escaped_text = escaped_text.replace("@here", '<span class="mention-ping">@here</span>')

    # URLリンク化（装飾より先：URL内の * や _ を触りにくくする）
    escaped_text = linkify_escaped(escaped_text)

    # 太字 → 打ち消し → 斜体 の順（衝突しにくい）
    escaped_text = BOLD_RE.sub(r"<strong>\1</strong>", escaped_text)
    escaped_text = STRIKE_RE.sub(r"<del>\1</del>", escaped_text)
    escaped_text = ITALIC_ASTER_RE.sub(r"<em>\1</em>", escaped_text)
    escaped_text = ITALIC_UNDER_RE.sub(r"<em>\1</em>", escaped_text)

    # 通常メンション色（@表示名 / @ロール / #チャンネル等）
    escaped_text = re.sub(r'(?<!<)(?<![\w/])(@[^\s<]+)', r'<span class="mention">\1</span>', escaped_text)
    escaped_text = re.sub(r'(?<!<)(?<![\w/])(#\S+)', r'<span class="mention">\1</span>', escaped_text)

    return escaped_text

def render_discord_markdown(raw_text: str, guild: discord.Guild | None) -> str:
    """
    - ``` コードブロック完全再現（pre/code）
    - # / ## / ### 見出し（行頭のみ）
    - 太字/斜体/打ち消し線（コード外）
    - URLはURL文字列を表示しつつリンク
    - メンションは表示名化（取れないユーザーは消える）
    """
    raw_text = replace_discord_mentions_to_names(raw_text, guild)

    parts = raw_text.split("```")
    out: list[str] = []

    for i, part in enumerate(parts):
        is_code = (i % 2 == 1)
        if is_code:
            # Discordの ```lang\ncode... を想定
            lang = ""
            code = part

            # 先頭行が言語指定っぽいなら分離
            if "\n" in code:
                first, rest = code.split("\n", 1)
                if len(first) <= 20 and re.fullmatch(r"[A-Za-z0-9_+\-#.]+", first.strip() or ""):
                    lang = first.strip()
                    code = rest

            code_esc = html.escape(code)
            lang_html = f'<div class="lang">{html.escape(lang)}</div>' if lang else ""
            out.append(f'<pre class="codeblock"><code>{code_esc}</code></pre>{lang_html}')
        else:
            # コード外：行単位で見出し、他はインライン装飾適用
            lines = part.splitlines() or [""]
            rendered_lines: list[str] = []
            for line in lines:
                if line.startswith("### "):
                    rendered_lines.append(f'<div class="h3">{html.escape(line[4:])}</div>')
                elif line.startswith("## "):
                    rendered_lines.append(f'<div class="h2">{html.escape(line[3:])}</div>')
                elif line.startswith("# "):
                    rendered_lines.append(f'<div class="h1">{html.escape(line[2:])}</div>')
                else:
                    esc = html.escape(line)
                    esc = apply_inline_formatting(esc)
                    rendered_lines.append(esc)
            out.append("<br>".join(rendered_lines))

    return "".join(out)

def reactions_to_html(message: discord.Message) -> str:
    if not message.reactions:
        return ""

    pills: list[str] = []
    for r in message.reactions:
        emoji = r.emoji

        # カスタム絵文字なら画像表示
        if isinstance(emoji, discord.PartialEmoji) and emoji.id:
            url = emoji.url
            pills.append(
                f'<span class="reaction"><img src="{html.escape(str(url))}" alt="emoji">'
                f'<span class="count">{r.count}</span></span>'
            )
        else:
            # 通常絵文字はテキスト
            pills.append(
                f'<span class="reaction"><span>{html.escape(str(emoji))}</span>'
                f'<span class="count">{r.count}</span></span>'
            )

    return f'<div class="reactions">{"".join(pills)}</div>'

def attachments_to_html(message: discord.Message) -> str:
    if not message.attachments:
        return ""

    imgs: list[str] = []
    files: list[str] = []

    for a in message.attachments:
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
                f'<div class="filelink"><a href="{html.escape(a.url)}" target="_blank" rel="noopener noreferrer">'
                f'{html.escape(a.filename)}</a></div>'
            )

    attach_block = ""
    if imgs:
        attach_block += '<div class="attach">' + "".join(imgs) + "</div>"
    if files:
        attach_block += "".join(files)

    return attach_block

def msg_to_html(m: discord.Message) -> str:
    author = m.author
    avatar_url = author.display_avatar.url if author.display_avatar else ""
    author_name = author.display_name
    time_str = m.created_at.astimezone(JST).strftime(TIME_FORMAT)

    body_html = render_discord_markdown(m.content or "", m.guild)
    attach_html = attachments_to_html(m)
    react_html = reactions_to_html(m)

    return f"""
    <div class="msg">
      <img class="avatar" src="{html.escape(avatar_url)}" alt="avatar">
      <div>
        <div class="line1">
          <span class="author">{html.escape(author_name)}</span>
          <span class="time">{html.escape(time_str)}</span>
        </div>
        <div class="content">{body_html}{attach_html}{react_html}</div>
      </div>
    </div>
    """

def make_filename(channel_name: str) -> str:
    def safe(s: str) -> str:
        return re.sub(r"[^\w\-]+", "_", s)

    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    return f"{safe(channel_name)}__{stamp}.html"

def _missing_perms_text(perms: discord.Permissions) -> str:
    need = []
    if not perms.view_channel:
        need.append("View Channel（チャンネルを見る）")
    if not perms.read_message_history:
        need.append("Read Message History（履歴を見る）")
    if not perms.send_messages:
        need.append("Send Messages（送信）")
    if not perms.attach_files:
        need.append("Attach Files（ファイル添付）")
    if need:
        return "⚠️ Botに権限が足りません：\n- " + "\n- ".join(need)
    return ""

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

        # 権限チェック
        me = channel.guild.me
        if me is None:
            await ctx.reply("⚠️ Bot自身の情報が取得できませんでした。少し待ってから再実行してください。")
            return

        perms = channel.permissions_for(me)
        miss = _missing_perms_text(perms)
        if miss:
            await ctx.reply(miss)
            return

        # 件数整形
        limit = max(1, min(limit, MAX_LIMIT))

        # ★オフライン含むメンバーをキャッシュ（詰まり防止でタイムアウト）
        if ctx.guild is not None:
            try:
                await asyncio.wait_for(ctx.guild.chunk(cache=True), timeout=5.0)
            except Exception:
                pass

        guild_name = ctx.guild.name if ctx.guild else "DM"
        filename = make_filename(channel.name)

        # サイズ超過なら自動で件数を減らす
        current = limit
        while True:
            msgs: list[discord.Message] = []
            try:
                async for m in channel.history(limit=current, oldest_first=True):
                    msgs.append(m)
            except discord.Forbidden:
                await ctx.reply("⚠️ メッセージ履歴を読む権限がありません（Read Message History）。")
                return
            except discord.HTTPException as e:
                await ctx.reply(f"⚠️ Discord API エラーで履歴取得に失敗しました：{e}")
                return

            messages_html = "\n".join(msg_to_html(m) for m in msgs)

            exported_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
            page = make_html_page(
                guild_name=guild_name,
                channel_name=channel.name,
                exported_at=exported_at,
                messages_html=messages_html,
            )
            data = page.encode("utf-8")

            if len(data) <= SAFE_MAX_BYTES:
                try:
                    file = discord.File(fp=io.BytesIO(data), filename=filename)
                    await ctx.send(f"✅ HTMLログを生成しました（{current}件）", file=file)
                except discord.Forbidden:
                    await ctx.reply("⚠️ 送信/添付権限がありません（Send Messages / Attach Files）。")
                except discord.HTTPException as e:
                    await ctx.reply(f"⚠️ ファイル送信に失敗しました：{e}")
                return

            if current <= 50:
                await ctx.send(
                    "⚠️ HTMLが大きすぎて添付できません。\n"
                    "画像/リアクション/コードなどで8MBを超える場合があります。`!export 100` など件数を減らして試してください。"
                )
                return

            current = max(50, current // 2)

async def setup(bot: commands.Bot):
    await bot.add_cog(ExportHtmlCog(bot))
