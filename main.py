# main.py
import asyncio
import discord
from discord.ext import commands
import config

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True  # prefixコマンド用

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")

async def main():
    async with bot:
        await bot.load_extension("cogs.setup_channels")
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
