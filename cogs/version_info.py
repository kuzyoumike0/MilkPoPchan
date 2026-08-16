"""最終更新日を表示するCog。

`!version` で「今このBotが動かしているコードが、いつGitHubから取得されたものか」を表示する。

■ 表示する4つの日時
    1. コードの最終更新   … ソースファイルの mtime で最も新しいもの
                            （GitHubのZIPをDLした場合＝そのコミットの日時）
    2. 取得/展開          … プロジェクトフォルダ自体の mtime（ZIPを展開した日時／デプロイ日時）
    3. このコードの初回起動 … 中身が変わったことを検知した最初の起動時刻を data/ に記録
    4. GitHubの最新コミット … APIで照会（config.GITHUB_REPO を設定した場合のみ）

■ 使い方
    !version        … まとめて表示
    !version files  … ファイル別の最終更新日時（新しい順15件）

■ 設定（config.py）
    GITHUB_REPO        … "ユーザー名/リポジトリ名"。None ならGitHub照会をしない
    GITHUB_BRANCH      … 照会するブランチ（省略時はデフォルトブランチ）
    VERSION_ADMIN_ONLY … True にすると管理者のみ実行可
    環境変数 GITHUB_TOKEN があれば認証付きで照会する（private リポジトリ／レート制限対策）
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

import aiohttp
import discord
from discord.ext import commands

import config

# zoneinfo は Windows で tzdata が要るため、JSTは自前定義にする
JST = timezone(timedelta(hours=9))
FMT = "%Y-%m-%d %H:%M:%S"

# cogs/version_info.py → 1つ上がプロジェクトルート
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(PROJECT_ROOT, "data", "version_info.json")

# 走査対象から外すフォルダ（data/ を除外しないと自分の記録で更新日が変わってしまう）
SKIP_DIRS = {"__pycache__", ".git", "data", ".venv", "venv", "node_modules", ".idea"}
WATCH_EXT = (".py", ".txt", ".json", ".md", ".toml")

GITHUB_API = "https://api.github.com/repos/{repo}/commits"
CACHE_SECONDS = 300  # GitHub APIは未認証だと60回/時なので5分キャッシュする

RAILWAY_KEYS = [
    ("RAILWAY_GIT_BRANCH", "ブランチ"),
    ("RAILWAY_GIT_COMMIT_SHA", "コミット"),
    ("RAILWAY_GIT_COMMIT_MESSAGE", "メッセージ"),
]


# -----------------------
# helpers
# -----------------------
def _jst(ts: float) -> str:
    return datetime.fromtimestamp(ts, JST).strftime(FMT)


def _ago(ts: float) -> str:
    """現在との差を「3日2時間前」のような文字列にする。"""
    sec = int(time.time() - ts)
    if sec < 60:
        return "たった今"
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}日{hours}時間前"
    if hours:
        return f"{hours}時間{minutes}分前"
    return f"{minutes}分前"


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _scan_source_files() -> List[Tuple[str, float]]:
    """プロジェクト内のソースを走査し、(相対パス, mtime) を新しい順で返す。"""
    found: List[Tuple[str, float]] = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if not name.endswith(WATCH_EXT):
                continue
            path = os.path.join(root, name)
            try:
                found.append((os.path.relpath(path, PROJECT_ROOT), os.path.getmtime(path)))
            except OSError:
                continue
    found.sort(key=lambda x: x[1], reverse=True)
    return found


def _load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[NG] version_info: 記録を保存できません -> {type(e).__name__}: {e}")


# -----------------------
# Cog
# -----------------------
class VersionInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = time.time()
        self.first_seen = self.started_at
        self._cache: Optional[dict] = None
        self._cache_at = 0.0

    async def cog_load(self):
        """コードの中身が前回と違えば「初回起動時刻」を今に更新する。"""
        files = _scan_source_files()
        newest = files[0][1] if files else 0.0
        fingerprint = f"{len(files)}:{newest:.0f}"

        state = _load_state()
        if state.get("fingerprint") != fingerprint:
            state = {
                "fingerprint": fingerprint,
                "first_seen": self.started_at,
                "first_seen_jst": _jst(self.started_at),
            }
            _save_state(state)
            print(f"[OK] version_info: 新しいコードを検知しました（{_jst(newest)}）")

        self.first_seen = float(state.get("first_seen", self.started_at))

    async def _fetch_latest_commit(self) -> Optional[dict]:
        """GitHubの最新コミットを取得する。未設定なら None、失敗時は {"error": ...}。"""
        repo = getattr(config, "GITHUB_REPO", None)
        if not repo:
            return None

        now = time.time()
        if self._cache and now - self._cache_at < CACHE_SECONDS:
            return self._cache

        params = {"per_page": "1"}
        branch = getattr(config, "GITHUB_BRANCH", None)
        if branch:
            params["sha"] = branch

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "discord-bot-version-info",
        }
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    GITHUB_API.format(repo=repo), params=params, headers=headers
                ) as resp:
                    if resp.status == 404:
                        return {"error": "リポジトリが見つかりません（private なら GITHUB_TOKEN が必要）"}
                    if resp.status == 403:
                        return {"error": "レート制限に達しました（GITHUB_TOKEN を設定すると緩和されます）"}
                    if resp.status != 200:
                        return {"error": f"GitHub API がステータス {resp.status} を返しました"}
                    data = await resp.json()
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

        if not isinstance(data, list) or not data:
            return {"error": "コミットが1件も取得できませんでした"}

        commit = data[0]
        detail = commit.get("commit", {}) or {}
        author = detail.get("author", {}) or {}
        message = (detail.get("message") or "").splitlines()
        info = {
            "sha": (commit.get("sha") or "")[:7],
            "message": message[0][:100] if message else "(メッセージなし)",
            "author": author.get("name") or "?",
            "date": author.get("date") or "",
            "url": commit.get("html_url") or "",
        }

        self._cache = info
        self._cache_at = now
        return info

    @commands.command(name="version", aliases=["ver", "lastupdate"])
    async def version_cmd(self, ctx: commands.Context, mode: str = ""):
        """!version：コードの最終更新日とGitHubの最新コミットを表示する"""
        if getattr(config, "VERSION_ADMIN_ONLY", False):
            perms = getattr(ctx.author, "guild_permissions", None)
            if perms is None or not (perms.administrator or perms.manage_guild):
                await ctx.reply("このコマンドは管理者のみ使用できます。", mention_author=False)
                return

        files = _scan_source_files()
        if not files:
            await ctx.reply("ソースファイルが見つかりませんでした。", mention_author=False)
            return

        # !version files → ファイル別の一覧
        if mode.lower() in ("files", "file", "list"):
            lines = [f"`{_jst(ts)}`  {name}" for name, ts in files[:15]]
            embed = discord.Embed(
                title="ファイル別 最終更新日時",
                description="\n".join(lines),
                color=0x5865F2,
            )
            embed.set_footer(text=f"新しい順 / 対象 {len(files)} ファイル")
            await ctx.reply(embed=embed, mention_author=False)
            return

        newest_name, newest_ts = files[0]
        try:
            root_ts = os.path.getmtime(PROJECT_ROOT)
        except OSError:
            root_ts = newest_ts

        embed = discord.Embed(title="📦 最終更新情報", color=0x5865F2)

        embed.add_field(
            name="コード（GitHubから取得した内容）",
            value=(
                f"最終更新: **{_jst(newest_ts)}**（{_ago(newest_ts)}）\n"
                f"最新ファイル: `{newest_name}`\n"
                f"取得/展開: {_jst(root_ts)}\n"
                f"このコードの初回起動: {_jst(self.first_seen)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="Bot",
            value=(
                f"起動: {_jst(self.started_at)}（{_ago(self.started_at)}）\n"
                f"discord.py {discord.__version__}"
            ),
            inline=False,
        )

        railway = []
        for key, label in RAILWAY_KEYS:
            raw = os.getenv(key, "").strip()
            if not raw:
                continue
            if key.endswith("SHA"):
                raw = raw[:7]
            railway.append(f"{label}: {discord.utils.escape_markdown(raw[:80])}")
        if railway:
            embed.add_field(name="デプロイ（Railway）", value="\n".join(railway), inline=False)

        commit = await self._fetch_latest_commit()
        repo = getattr(config, "GITHUB_REPO", None)

        if commit is None:
            embed.add_field(
                name="GitHub",
                value="`config.GITHUB_REPO` が未設定のため照会していません。",
                inline=False,
            )
        elif "error" in commit:
            embed.add_field(name=f"GitHub（{repo}）", value=f"⚠️ {commit['error']}", inline=False)
        else:
            dt = _parse_iso(commit["date"])
            when = _jst(dt.timestamp()) if dt else commit["date"]

            status = ""
            if dt:
                # ZIP取得ならファイルmtime＝コミット日時になるため、120秒の余裕を見る
                if dt.timestamp() > newest_ts + 120:
                    status = "\n⚠️ **GitHub側が新しいです（未反映の可能性）**"
                else:
                    status = "\n✅ 最新のコードで動作中"

            value = (
                f"最新コミット: **{when}**\n"
                f"`{commit['sha']}` {discord.utils.escape_markdown(commit['message'])}\n"
                f"by {discord.utils.escape_markdown(commit['author'])}{status}"
            )
            if commit["url"]:
                value += f"\n[コミットを開く]({commit['url']})"
            embed.add_field(name=f"GitHub（{repo}）", value=value, inline=False)

        embed.set_footer(text="日時はすべて日本時間（JST） / !version files でファイル別一覧")
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(VersionInfoCog(bot))
