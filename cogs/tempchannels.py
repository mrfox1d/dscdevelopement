# tempchannels.py
import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, Select, View, Button
import aiosqlite
import asyncio

class TempVoices(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.path = "v1rago/dbs/file.db"

    async def init_db(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS tempchannels (
                            guild_id INTEGER PRIMARY KEY,
                            category_id INTEGER DEFAULT NULL,
                            settings_channel_id INTEGER DEFAULT NULL,
                            mother_channel_id INTEGER DEFAULT NULL
                            )""")
            await db.execute("""CREATE TABLE IF NOT EXISTS tempvoiceusers (
                             creator_id INTEGER PRIMARY KEY,
                             channel_id INTEGER,
                             owner_id INTEGER,
                             max_users INTEGER DEFAULT NULL,
                             is_private TEXT DEFAULT "true",
                             name TEXT,
                             bitrate INTEGER DEFAULT 64000,
                             banned_users_ids TEXT DEFAULT NULL,
                             deafened_users_ids TEXT DEFAULT NULL
                             )""")
            await db.commit()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_db()
        print(f"Ког {self.__class__.__name__} загружен!")

    async def edit_settings(self, creator_id, **kwargs):
        async with aiosqlite.connect(self.path) as db:
            if kwargs:
                set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
                values = list(kwargs.values())
                values.append(creator_id)
                await db.execute(f"UPDATE tempvoiceusers SET {set_clause} WHERE creator_id = ?", values)
                await db.commit()

    async def create_temp_voice(self, creator_id, channel_id, owner_id=None, **kwargs):
        async with aiosqlite.connect(self.path) as db:
            owner_id = owner_id or creator_id
            await db.execute("""INSERT OR REPLACE INTO tempvoiceusers 
                              (creator_id, channel_id, owner_id, max_users, is_private, name, bitrate, banned_users_ids, deafened_users_ids) 
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                            (creator_id, channel_id, owner_id, 
                             kwargs.get('max_users'), kwargs.get('is_private', 'true'),
                             kwargs.get('name'), kwargs.get('bitrate', 64000),
                             kwargs.get('banned_users_ids'), kwargs.get('deafened_users_ids')))
            await db.commit()

    async def get_temp_voice(self, creator_id):
        async with aiosqlite.connect(self.path) as db:
            voice = await db.execute("SELECT * FROM tempvoiceusers WHERE creator_id = ?", (creator_id,)).fetchone()
            return voice

    async def delete_empty_channels(self):
        for guild in self.bot.guilds:
            async with aiosqlite.connect(self.path) as db:
                channels = await db.execute("SELECT channel_id FROM tempvoiceusers").fetchall()
                for channel_data in channels:
                    channel_id = channel_data[0]
                    channel = guild.get_channel(channel_id)
                    if channel and hasattr(channel, 'members'):
                        if len(channel.members) == 0:
                            await channel.delete()
                            await db.execute("DELETE FROM tempvoiceusers WHERE channel_id = ?", (channel_id,))
                await db.commit()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel is None and after.channel is not None:
            async with aiosqlite.connect(self.path) as db:
                setup = await db.execute("SELECT mother_channel_id FROM tempchannels WHERE guild_id = ?", (member.guild.id,)).fetchone()
                if setup and after.channel.id == setup[0]:
                    category = member.guild.get_channel(setup[1]) if setup[1] else None
                    tempvoice = await member.guild.create_voice_channel(
                        f"🔊・{member.display_name}",
                        category=category
                    )
                    await self.create_temp_voice(member.id, tempvoice.id, owner_id=member.id)
                    await member.move_to(tempvoice)
                    
                    await tempvoice.set_permissions(member, connect=True, speak=True, view_channel=True)
        
        if before.channel and before.channel != after.channel:
            if len(before.channel.members) == 0:
                async with aiosqlite.connect(self.path) as db:
                    voice = await db.execute("SELECT * FROM tempvoiceusers WHERE channel_id = ?", (before.channel.id,)).fetchone()
                    if voice:
                        await before.channel.delete()
                        await db.execute("DELETE FROM tempvoiceusers WHERE channel_id = ?", (before.channel.id,))
                        await db.commit()

    @commands.command(name="tv")
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        async with aiosqlite.connect(self.path) as db:
            setup = await db.execute("SELECT * FROM tempchannels WHERE guild_id = ?", (ctx.guild.id,)).fetchone()
            if setup:
                await ctx.send("✅ Сетап уже сделан.")
                return
            
            message = await ctx.send("""**🛠️ Процесс создания начался.**\n░░░░░░░░░░░░ | 0%""")
            
            category = await ctx.guild.create_category_channel("🎵 Временные голосовые каналы")
            await message.edit(content="""**🛠️ Создание в процессе.**\n███░░░░░░░░░ | 25%""")
            
            channel = await ctx.guild.create_text_channel("🎵・настройки", category=category)
            await message.edit(content="""**🛠️ Создание в процессе.**\n██████░░░░░░ | 50%""")
            
            mother_channel = await ctx.guild.create_voice_channel("➕・Создать канал", category=category)
            await message.edit(content="""**🛠️ Создание в процессе.**\n█████████░░░ | 75%""")
            
            await db.execute("""INSERT INTO tempchannels (guild_id, category_id, settings_channel_id, mother_channel_id) 
                             VALUES (?, ?, ?, ?)""", 
                           (ctx.guild.id, category.id, channel.id, mother_channel.id))
            await db.commit()
            
            emb = discord.Embed(
                title="🔊 Настройка временных голосовых каналов.", 
                description="""🔇 - **заглушить пользователя**
❌ - **забанить пользователя**
👢 - **кикнуть пользователя**
🔐 - **открыть / закрыть канал**
👑 - **передать владение каналом**
⚙️ - **изменить битрейт канала**"""
            )
            
            view = View(timeout=None)
            buttons = [
                ("🔇", "mute", discord.ButtonStyle.secondary),
                ("❌", "ban", discord.ButtonStyle.secondary),
                ("👢", "kick", discord.ButtonStyle.secondary),
                ("🔐", "lock", discord.ButtonStyle.secondary),
                ("👑", "give_ownership", discord.ButtonStyle.secondary),
                ("⚙️", "bitrate", discord.ButtonStyle.secondary),
            ]
            
            for label, custom_id, style in buttons:
                btn = Button(label=label, style=style, custom_id=custom_id)
                view.add_item(btn)
            
            await channel.send("@everyone", embed=emb, view=view)
            await message.edit(content=f"""**✅ Сетап завершён!**\n████████████ | 100%\n
🔊 Каналы: {channel.mention}, {mother_channel.mention} | Категория: {category.name}""")

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data['custom_id']
        
        if custom_id == "lock":
            tempvoice = await self.get_temp_voice(interaction.user.id)
            if not tempvoice:
                await interaction.response.send_message("❌ Вы не создали временный канал.", ephemeral=True)
                return
            
            channel = interaction.guild.get_channel(tempvoice[1])
            if not channel:
                await interaction.response.send_message("❌ Канал не найден.", ephemeral=True)
                return
            
            if tempvoice[4] == "true":
                await channel.set_permissions(interaction.guild.default_role, connect=False)
                await self.edit_settings(interaction.user.id, is_private="false")
                await interaction.response.send_message("✅ Вы закрыли канал.", ephemeral=True)
            else:
                await channel.set_permissions(interaction.guild.default_role, connect=True)
                await self.edit_settings(interaction.user.id, is_private="true")
                await interaction.response.send_message("✅ Вы открыли канал.", ephemeral=True)
        
        elif custom_id == "give_ownership":
            tempvoice = await self.get_temp_voice(interaction.user.id)
            
            if not tempvoice:
                await interaction.response.send_message("❌ Вы не создали временный канал.", ephemeral=True)
                return
            
            channel = interaction.guild.get_channel(tempvoice[1])
            if not channel or not hasattr(channel, 'members'):
                await interaction.response.send_message("❌ Голосовой канал не найден.", ephemeral=True)
                return
            
            members = channel.members
            if not members:
                await interaction.response.send_message("❌ Канал пуст.", ephemeral=True)
                return
            
            options = []
            for i, member in enumerate(members[:25]):
                emoji = "👤"
                if member.voice:
                    if member.voice.mute:
                        emoji = "🔇"
                    elif member.voice.self_mute:
                        emoji = "🎙️"
                    elif member.voice.self_deaf:
                        emoji = "🎧"
                
                options.append(discord.SelectOption(
                    label=member.display_name[:100],
                    value=str(member.id),
                    emoji=emoji
                ))
            
            options.append(discord.SelectOption(
                label="Вписать ID вручную",
                value="manual",
                emoji="⌨️"
            ))
            
            select = Select(
                placeholder=f"Выберите пользователя ({len(members)} чел.)",
                options=options,
                custom_id="select_owner"
            )
            
            async def select_callback(select_interaction):
                if select.values[0] == "manual":
                    modal = Modal(
                        title="Введите ID пользователя",
                        custom_id="manual_id_modal"
                    )
                    modal.add_item(
                        TextInput(
                            label="ID пользователя",
                            custom_id="user_id",
                            placeholder="123456789012345678"
                        )
                    )
                    await select_interaction.response.send_modal(modal)
                    
                    try:
                        modal_interaction = await self.bot.wait_for(
                            "modal_submit",
                            timeout=60.0,
                            check=lambda m: m.data['custom_id'] == "manual_id_modal" and m.user.id == interaction.user.id
                        )
                        
                        user_id = int(modal_interaction.data['components'][0]['components'][0]['value'])
                        new_owner = interaction.guild.get_member(user_id)
                        
                        if not new_owner:
                            await modal_interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)
                            return
                        
                        if new_owner not in members:
                            await modal_interaction.response.send_message("❌ Этот пользователь не в вашем канале.", ephemeral=True)
                            return
                        
                        await self.edit_settings(interaction.user.id, owner_id=new_owner.id)
                        await modal_interaction.response.send_message(f"✅ Вы передали владение канала {new_owner.mention}.", ephemeral=True)
                        
                    except ValueError:
                        await select_interaction.followup.send("❌ Неверный ID. Введите числовой ID.", ephemeral=True)
                    except asyncio.TimeoutError:
                        await select_interaction.followup.send("❌ Время ожидания истекло.", ephemeral=True)
                
                else:
                    new_owner_id = int(select.values[0])
                    new_owner = interaction.guild.get_member(new_owner_id)
                    
                    if new_owner and new_owner in members:
                        await self.edit_settings(interaction.user.id, owner_id=new_owner_id)
                        await select_interaction.response.send_message(f"✅ Вы передали владение канала {new_owner.mention}.", ephemeral=True)
                    else:
                        await select_interaction.response.send_message("❌ Пользователь не найден или не в канале.", ephemeral=True)
            
            select.callback = select_callback
            
            view = View()
            view.add_item(select)
            
            await interaction.response.send_message("Выберите нового владельца:", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TempVoices(bot))
