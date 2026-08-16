# config.py
import os   # ← ★これが必要

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

# !setup を打つ専用チャンネル（制限しないなら None）
SETUP_CHANNEL_ID = None

# 見学ロール
SPECTATOR_ROLE_ID = 1396919553413353503

SESSION_VC_IDS = {
    1: 1386201663446057102,
    2: 1533895358696914999,
    3: 1397685082369818881,
    4: 1480576321196261458,
}

SESSION_SHARED_CATEGORY_IDS = {
    1: 1452111204188160164,
    2: 1452111277127372921,
    3: 1452111331938402359,
    4: 1480575973148590141,
}

SESSION_INDIVIDUAL_CATEGORY_IDS = {
    1: 1452111204188160164,
    2: 1452111277127372921,
    3: 1452111331938402359,
    4: 1480575973148590141,
}
# ===== version_info.py（最終更新日表示）=====
# GitHub照会を使う場合は "ユーザー名/リポジトリ名" を設定。None なら照会しない
GITHUB_REPO = None          # 例: "yourname/MilkPoPchan"
GITHUB_BRANCH = "main"      # None ならデフォルトブランチ
VERSION_ADMIN_ONLY = False  # True で管理者のみ実行可
