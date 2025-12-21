import asyncio
import discord
from discord.ext import commands

import config

COG_LIST = [
    "cogs.export_html",
    "cogs.setup_channels",
]

def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True  # !export / !mkchannel 用
    intents.members = True          # ★オフラインメンバーも含めて取得するため
    return intents

class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        for ext in COG_LIST:
            await self.load_extension(ext)

async def main():
    if not config.TOKEN:
        raise RuntimeError("DISCORD_TOKEN が未設定です（Railway Variables を確認）")

    bot = MyBot(command_prefix="!", intents=build_intents(), help_command=None)

    @bot.event
    async def on_ready():
        print(f"Logged in as: {bot.user} (id={bot.user.id})")

    await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
