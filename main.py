import discord
from discord.ext import commands
import asyncio
import config

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")

async def main():
    async with bot:
        await bot.load_extension("cogs.setupvc_session_categories")
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
