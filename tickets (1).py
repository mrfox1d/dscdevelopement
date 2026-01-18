import disnake
from disnake.ext import commands
import aiosqlite
import asyncio
from datetime import datetime

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.path = "v1rago/dbs/file.db"

    async def init_db(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("""CREATE TABLE IF NOT EXISTS tickets (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             author_id INTEGER,
                             created_at TEXT,
                             status TEXT DEFAULT 'open',
                             channel_id INTEGER,
                             moderator_id INTEGER DEFAULT NULL)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS transcripts (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             ticket_id INTEGER,
                             message TEXT,
                             message_author INTEGER,
                             FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS setup (
                             guild_id INTEGER PRIMARY KEY, 
                             ticket_category_id INTEGER DEFAULT NULL, 
                             ticket_channel_id INTEGER DEFAULT NULL)""")
            await db.commit()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_db()
        print(f"Ког {self.__class__.__name__} загружен!")

    async def create_ticket(self, author_id, channel_id):
        async with aiosqlite.connect(self.path) as db:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await db.execute("INSERT INTO tickets (author_id, created_at, channel_id) VALUES (?, ?, ?)",
                            (author_id, created_at, channel_id))
            await db.commit()

    async def close_ticket(self, ticket_id, channel):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
            
            # Сохраняем транскрипт
            messages = await channel.history(limit=None).flatten()
            for message in messages:
                await db.execute("INSERT INTO transcripts (ticket_id, message, message_author) VALUES (?, ?, ?)",
                                (ticket_id, message.content, message.author.id))
            await db.commit()

    async def add_ticket_moderator(self, ticket_id, moderator_id):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE tickets SET moderator_id = ? WHERE id = ?", (moderator_id, ticket_id))
            await db.commit()

    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        async with aiosqlite.connect(self.path) as db:
            setup = await db.execute("SELECT * FROM setup WHERE guild_id = ?", (ctx.guild.id,)).fetchone()
            if setup:
                await ctx.send("✅ Сетап тикетов уже сделан.")
                return
            
            message = await ctx.send("""**🛠️ Процесс создания начался.**\n░░░░░░░░░░░░ | 0%""")
            
            category = await ctx.guild.create_category("🎫 Тикеты")
            await message.edit(content="""**🛠️ Создание в процессе.**\n████░░░░░░░░ | 33%""")
            
            channel = await ctx.guild.create_text_channel("🎫・создать-тикет", category=category)
            await message.edit(content="""**🛠️ Создание в процессе.**\n████████░░░░ | 66%""")
            
            emb = disnake.Embed(
                title="🎫 Создание тикета.", 
                description="・Для создания тикета нажмите на кнопку."
            )
            emb.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            
            view = disnake.ui.View(timeout=None)
            btn = disnake.ui.Button(label="🎫", style=disnake.ButtonStyle.success, custom_id="create_ticket")
            view.add_item(btn)
            
            await channel.send("@everyone", embed=emb, view=view)
            await message.edit(content="""**🛠️ Создание в процессе.**\n███████████░ | 90%""")
            
            await db.execute("INSERT INTO setup (guild_id, ticket_category_id, ticket_channel_id) VALUES (?, ?, ?)",
                            (ctx.guild.id, category.id, channel.id))
            await db.commit()
            
            await message.edit(content=f"""**🛠️ Создание завершено.**\n████████████ | 100%\n\n🎫 Созданный канал: **{channel.mention}** | Категория: **🎫 Тикеты**""")

    @commands.Cog.listener()
    async def on_button_click(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id == "create_ticket":
            async with aiosqlite.connect(self.path) as db:
                setup = await db.execute("SELECT * FROM setup WHERE guild_id = ?", (inter.guild.id,)).fetchone()
                if not setup:
                    await inter.response.send_message("❌ Сетап тикетов не сделан.", ephemeral=True)
                    return
                
                ticket_category = inter.guild.get_channel(setup[1])
                if not ticket_category:
                    await inter.response.send_message("❌ Категория тикетов не найдена.", ephemeral=True)
                    return
                
                ticket_channel = inter.guild.get_channel(setup[2])
                
                ticket = await ticket_category.create_text_channel(f"🎫・{inter.author.name}")
                await ticket.set_permissions(inter.author, read_messages=True, send_messages=True)
                await ticket.set_permissions(inter.guild.default_role, read_messages=False)
                
                await self.create_ticket(inter.author.id, ticket.id)
                await inter.response.send_message(f"✅ Тикет создан: {ticket.mention}", ephemeral=True)

                view = disnake.ui.View(timeout=None)
                button1 = disnake.ui.Button(label="✅ Принять тикет", style=disnake.ButtonStyle.blurple, custom_id="accept_ticket")
                button2 = disnake.ui.Button(label="❌ Закрыть тикет", style=disnake.ButtonStyle.danger, custom_id="close_ticket")
                view.add_item(button1)
                view.add_item(button2)
                
                emb = disnake.Embed(
                    title="🎫 Тикет создан.", 
                    description="・Спасибо, что обратились к нам!\n・Ожидайте, когда модератор ответит."
                )
                emb.set_author(name=inter.guild.name, icon_url=inter.guild.icon.url if inter.guild.icon else None)
                
                await ticket.send(embed=emb, content=f"{inter.author.mention}", view=view)
                await ticket.send("@here")

        elif inter.component.custom_id == "accept_ticket":
            async with aiosqlite.connect(self.path) as db:
                ticket = await db.execute("SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)).fetchone()
                if not ticket:
                    await inter.response.send_message("❌ Тикет не найден.", ephemeral=True)
                    return
                
                moderator = ticket[5]  # moderator_id
                if moderator:
                    await inter.response.send_message(f"❌ Тикет уже принят пользователем <@{moderator}>.", ephemeral=True)
                    return
                
                await self.add_ticket_moderator(ticket[0], inter.author.id)
                await inter.response.send_message(f"✅ Тикет принят: {inter.author.mention}", ephemeral=True)
                
                ticket_author = ticket[1]  # author_id
                await inter.channel.send(f"<@{ticket_author}>, ваш тикет обслужит <@{inter.author.id}>.")

        elif inter.component.custom_id == "close_ticket":
            async with aiosqlite.connect(self.path) as db:
                ticket = await db.execute("SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)).fetchone()
                if not ticket:
                    await inter.response.send_message("❌ Тикет не найден.", ephemeral=True)
                    return
                
                # Проверка прав
                if ticket[5] != inter.author.id and not inter.channel.permissions_for(inter.author).administrator:
                    await inter.response.send_message("❌ Вы не можете закрыть этот тикет.", ephemeral=True)
                    return
                
                await self.close_ticket(ticket[0], inter.channel)
                
                # Отсчет перед удалением
                message = await inter.channel.send("⚠️ Тикет закрыт.\n⏱️ Канал будет удалён через **5 секунд**.")
                
                for i in range(4, -1, -1):
                    await asyncio.sleep(1)
                    if i == 1:
                        await message.edit(content=f"⚠️ Тикет закрыт.\n⏱️ Канал будет удалён через **{i} секунду**.")
                    elif i == 0:
                        await message.edit(content="⚠️ Тикет закрыт.\n⏱️ Канал будет удалён через **0 секунд**.")
                        await inter.channel.delete()
                        break
                    else:
                        await message.edit(content=f"⚠️ Тикет закрыт.\n⏱️ Канал будет удалён через **{i} секунды**.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        async with aiosqlite.connect(self.path) as db:
            result = await db.execute("SELECT moderator_id, author_id FROM tickets WHERE channel_id = ?", (message.channel.id,)).fetchone()
            if not result:
                return
                
            moderator_id, ticket_author_id = result
            
            if not moderator_id:
                return
                
            if message.author.id == moderator_id:
                return
                
            if message.author.id == self.bot.user.id:
                return
                
            if message.channel.permissions_for(message.author).administrator:
                return
                
            if message.author.id == ticket_author_id:
                return
            
            # Если сообщение от постороннего
            await message.delete()
            try:
                await message.author.send("⚠️ Не мешайте работе модераторов, не влезайте в тикет!")
            except:
                pass

def setup(bot):
    bot.add_cog(TicketSystem(bot))