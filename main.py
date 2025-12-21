import os
import asyncio
import discord
from discord.ext import commands

COG_LIST = ["cogs.export_html"]

def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True  # !export 用
    intents.members = True
    return intents

class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        for ext in COG_LIST:
            await self.load_extension(ext)

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN が未設定です（Railway Variablesを確認）")
    if token.strip() != token:
        raise RuntimeError("DISCORD_TOKEN の前後に空白/改行があります（VariablesのValueを修正）")
    if " " in token:
        raise RuntimeError("DISCORD_TOKEN にスペースが含まれています（VariablesのValueを修正）")

    bot = MyBot(command_prefix="!", intents=build_intents(), help_command=None)

    @bot.event
    async def on_ready():
        print(f"Logged in as: {bot.user} (id={bot.user.id})")

    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
    
await bot.load_extension("cogs.setupvc_session_categories")
