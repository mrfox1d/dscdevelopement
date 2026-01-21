import os
import disnake
from disnake.ext import commands

TOKEN = os.getenv("TOKEN")

bot = commands.Bot(command_prefix=".", intents=disnake.Intents.all(), help_command=None)

@bot.event
async def on_ready():
    await bot.change_presence(activity=disnake.Activity(type=disnake.ActivityType.playing, name="Minecraft | Сервер: AquaLand"), status=disnake.Status.dnd)
    print(f"Logged in as {bot.user.name}")

    bot.load_extensions("cogs")

bot.run(TOKEN)
