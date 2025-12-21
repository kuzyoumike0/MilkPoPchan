import os
import asyncio
import discord
from discord.ext import commands

COG_LIST = [
    "cogs.export_html",
]

def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True  # ログ本文取得に必要（DevPortalでもON）
    intents.members = True
    return intents

class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        # Cogs load
        for ext in COG_LIST:
            await self.load_extension(ext)

        # スラッシュコマンド同期（グローバル）
        # ※反映に時間がかかる場合があります
        await self.tree.sync()

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("環境変数 DISCORD_TOKEN が設定されていません。")

    bot = MyBot(
        command_prefix="!",
        intents=build_intents(),
        help_command=None,
    )

    @bot.event
    async def on_ready():
        print(f"Logged in as: {bot.user} (id={bot.user.id})")

    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
