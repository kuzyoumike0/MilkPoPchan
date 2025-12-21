from __future__ import annotations

import html
import io
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

DEFAULT_LIMIT = 200
MAX_LIMIT = 5000
TIME_FORMAT = "%Y-%m-%d %H:%M"

SAFE_MAX_BYTES = 8 * 1024 * 1024 - 200_000  # Discord添付安全サイズ
URL_RE = re.compile(r"(https?://[^\s]+)")

# ================= HTML生成 =================

def make_html_page(guild_name: str, channel_name: str, exported_at: str, messages_html: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>{html.escape(guild_name)} - #{html.escape(channel_name)}</title>
<style>
body {{
  background:#1e1f22; color:#dbdee1;
  font-family: system-ui, sans-serif;
}}
.msg {{
  display:grid; grid-template-columns:44px 1fr;
  gap:12px; padding:10px 16px;
  border-bottom:1px solid rgba(255,255,255,.05);
}}
.avatar {{
  width:40px; height:40px; border-radius:999px;
}}
.author {{ font-weight:700; }}
.time {{ color:#949ba4; font-size:12px; margin-left:6px; }}
.attach img {{ max-width:360px; border-radius:10px; }}
</style>
</head>
<body>
<h3>{html.escape(guild_name)} / #{html.escape(channel_name)}</h3>
<p>Exported at: {exported_at}</p>
{messages_html}
</body>
</html>
"""

def
