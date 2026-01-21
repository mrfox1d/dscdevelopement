import os
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")

bot = commands.Bot(command_prefix=".", intents=discord.Intents.all(), help_command=None)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="Minecraft | Сервер: AquaLand"), status=discord.Status.dnd)
    print(f"Logged in as {bot.user.name}")

    

bot.run(TOKEN)
