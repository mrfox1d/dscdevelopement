import os
import disnake
from disnake.ext import commands

TOKEN = "MTM5MTM2MjgzNjEwOTcyMTYyMA.GJQMh8.cHlnr_Z4clMki4DcDctu_Sna1xJZqyPPMuGYIo"

bot = commands.Bot(command_prefix=".", intents=disnake.Intents.all(), help_command=None)

@bot.event
async def on_ready():
    await bot.change_presence(activity=disnake.Activity(type=disnake.ActivityType.playing, name="Minecraft | Сервер: AquaLand"), status=disnake.Status.dnd)
    print(f"Logged in as {bot.user.name}")

    bot.load_extensions("v1rago/cogs")

bot.run(TOKEN)