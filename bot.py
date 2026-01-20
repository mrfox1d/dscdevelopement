# bot.py
import os
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="Minecraft | Сервер: AquaLand"), status=discord.Status.dnd)
    print(f"Logged in as {bot.user.name}")
    
    for filename in os.listdir("./v1rago/cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"v1rago.cogs.{filename[:-3]}")

bot.run(TOKEN)
