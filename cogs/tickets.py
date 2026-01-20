# tickets.py
import disnake
from disnake.ext import commands
from disnake.ui import Button, View, Modal, TextInput, Select
import aiosqlite
import asyncio
from datetime import datetime
import io
import textwrap

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.path = "v1rago/dbs/file.db"
        self.ticket_cooldowns = {}

    async def init_db(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            
            # Таблица тикетов
            await db.execute("""CREATE TABLE IF NOT EXISTS tickets (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             author_id INTEGER,
                             created_at TEXT,
                             status TEXT DEFAULT 'open',
                             channel_id INTEGER,
                             moderator_id INTEGER DEFAULT NULL,
                             guild_id INTEGER,
                             ticket_type TEXT DEFAULT 'general',
                             closed_at TEXT DEFAULT NULL,
                             close_reason TEXT DEFAULT NULL)""")
            
            # Сообщения в тикетах
            await db.execute("""CREATE TABLE IF NOT EXISTS ticket_messages (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             ticket_id INTEGER,
                             author_id INTEGER,
                             message TEXT,
                             created_at TEXT,
                             attachments TEXT DEFAULT NULL,
                             FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE)""")
            
            # Транскрипты
            await db.execute("""CREATE TABLE IF NOT EXISTS transcripts (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             ticket_id INTEGER,
                             content TEXT,
                             created_at TEXT,
                             FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE)""")
            
            # Конфигурация
            await db.execute("""CREATE TABLE IF NOT EXISTS ticket_config (
                             guild_id INTEGER PRIMARY KEY,
                             category_id INTEGER DEFAULT NULL,
                             create_channel_id INTEGER DEFAULT NULL,
                             create_message_id INTEGER DEFAULT NULL,
                             log_channel_id INTEGER DEFAULT NULL,
                             support_role_id INTEGER DEFAULT NULL,
                             max_tickets_per_user INTEGER DEFAULT 3,
                             ticket_cooldown INTEGER DEFAULT 300,
                             require_topic BOOLEAN DEFAULT 0,
                             auto_close_hours INTEGER DEFAULT 24,
                             welcome_message TEXT DEFAULT 'Спасибо за обращение! Ожидайте ответа модератора.',
                             ticket_types TEXT DEFAULT 'general,report,bug,support')""")
            
            # Темы тикетов
            await db.execute("""CREATE TABLE IF NOT EXISTS ticket_topics (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             guild_id INTEGER,
                             name TEXT,
                             description TEXT,
                             emoji TEXT DEFAULT '🎫')""")
            
            await db.commit()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_db()
        print(f"Ког {self.__class__.__name__} загружен!")
        self.bot.loop.create_task(self.check_auto_close_tickets())

    async def get_ticket_config(self, guild_id):
        async with aiosqlite.connect(self.path) as db:
            config = await db.execute("SELECT * FROM ticket_config WHERE guild_id = ?", (guild_id,)).fetchone()
            if config:
                return {
                    'guild_id': config[0],
                    'category_id': config[1],
                    'create_channel_id': config[2],
                    'create_message_id': config[3],
                    'log_channel_id': config[4],
                    'support_role_id': config[5],
                    'max_tickets_per_user': config[6],
                    'ticket_cooldown': config[7],
                    'require_topic': bool(config[8]),
                    'auto_close_hours': config[9],
                    'welcome_message': config[10],
                    'ticket_types': config[11].split(',') if config[11] else ['general']
                }
            
            # Конфиг по умолчанию
            default_types = 'general,report,bug,support,other'
            await db.execute(
                "INSERT INTO ticket_config (guild_id, ticket_types) VALUES (?, ?)",
                (guild_id, default_types)
            )
            await db.commit()
            
            return {
                'guild_id': guild_id,
                'category_id': None,
                'create_channel_id': None,
                'create_message_id': None,
                'log_channel_id': None,
                'support_role_id': None,
                'max_tickets_per_user': 3,
                'ticket_cooldown': 300,
                'require_topic': False,
                'auto_close_hours': 24,
                'welcome_message': 'Спасибо за обращение! Ожидайте ответа модератора.',
                'ticket_types': default_types.split(',')
            }

    async def get_user_tickets_count(self, guild_id, user_id):
        async with aiosqlite.connect(self.path) as db:
            count = await db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND author_id = ? AND status = 'open'",
                (guild_id, user_id)
            ).fetchone()
            return count[0] if count else 0

    async def create_ticket(self, guild_id, author_id, channel_id, ticket_type='general'):
        async with aiosqlite.connect(self.path) as db:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor = await db.execute(
                "INSERT INTO tickets (guild_id, author_id, created_at, channel_id, ticket_type) VALUES (?, ?, ?, ?, ?)",
                (guild_id, author_id, created_at, channel_id, ticket_type)
            )
            await db.commit()
            return cursor.lastrowid

    async def close_ticket(self, ticket_id, moderator_id=None, reason="Не указана"):
        async with aiosqlite.connect(self.path) as db:
            closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                "UPDATE tickets SET status = 'closed', moderator_id = ?, closed_at = ?, close_reason = ? WHERE id = ?",
                (moderator_id, closed_at, reason, ticket_id)
            )
            await db.commit()

    async def add_ticket_moderator(self, ticket_id, moderator_id):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE tickets SET moderator_id = ? WHERE id = ?", (moderator_id, ticket_id))
            await db.commit()

    async def save_transcript(self, ticket_id, channel):
        """Сохранить транскрипт тикета"""
        messages = []
        
        async for message in channel.history(limit=None, oldest_first=True):
            if message.author.bot and not message.content and not message.embeds:
                continue
                
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            author = f"{message.author.name}#{message.author.discriminator}"
            
            content = message.clean_content
            if not content and message.embeds:
                content = "[EMBED]"
            elif not content and message.attachments:
                content = "[ATTACHMENT]"
            
            attachments = ""
            if message.attachments:
                attachments = " | Вложения: " + ", ".join([att.filename for att in message.attachments])
            
            messages.append(f"[{timestamp}] {author}: {content}{attachments}")
        
        transcript_content = "\n".join(messages)
        
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO transcripts (ticket_id, content, created_at) VALUES (?, ?, ?)",
                (ticket_id, transcript_content, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            await db.commit()
        
        return transcript_content

    async def get_ticket_info(self, ticket_id):
        async with aiosqlite.connect(self.path) as db:
            ticket = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if ticket:
                return {
                    'id': ticket[0],
                    'author_id': ticket[1],
                    'created_at': ticket[2],
                    'status': ticket[3],
                    'channel_id': ticket[4],
                    'moderator_id': ticket[5],
                    'guild_id': ticket[6],
                    'ticket_type': ticket[7],
                    'closed_at': ticket[8],
                    'close_reason': ticket[9]
                }
            return None

    @commands.slash_command(name="ticket_setup", description="Настроить систему тикетов")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, inter: disnake.ApplicationCommandInteraction,
                          category: disnake.CategoryChannel = commands.Param(description="Категория для тикетов"),
                          create_channel: disnake.TextChannel = commands.Param(description="Канал для создания тикетов"),
                          support_role: disnake.Role = commands.Param(description="Роль поддержки", default=None),
                          log_channel: disnake.TextChannel = commands.Param(description="Канал для логов тикетов", default=None),
                          max_tickets: int = commands.Param(description="Макс. тикетов на пользователя", default=3, ge=1, le=10),
                          cooldown: int = commands.Param(description="КД создания тикетов (сек)", default=300, ge=0, le=3600)):
        
        config = await self.get_ticket_config(inter.guild.id)
        
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""UPDATE ticket_config SET 
                             category_id = ?, create_channel_id = ?, support_role_id = ?, 
                             log_channel_id = ?, max_tickets_per_user = ?, ticket_cooldown = ? 
                             WHERE guild_id = ?""",
                           (category.id, create_channel.id, support_role.id if support_role else None,
                            log_channel.id if log_channel else None, max_tickets, cooldown, inter.guild.id))
            await db.commit()
        
        # Создаем сообщение с кнопками
        embed = disnake.Embed(
            title="🎫 Система тикетов",
            description="Выберите тип тикета:",
            color=disnake.Color.green()
        )
        
        config = await self.get_ticket_config(inter.guild.id)
        
        # Создаем view с кнопками для типов тикетов
        view = TicketCreateView(self.bot, config)
        
        # Очищаем старые сообщения и отправляем новое
        await create_channel.purge(limit=10)
        message = await create_channel.send(embed=embed, view=view)
        
        # Сохраняем ID сообщения
        await db.execute(
            "UPDATE ticket_config SET create_message_id = ? WHERE guild_id = ?",
            (message.id, inter.guild.id)
        )
        await db.commit()
        
        embed = disnake.Embed(
            title="✅ Настройка тикетов завершена",
            description=f"**Категория:** {category.mention}\n"
                       f"**Канал создания:** {create_channel.mention}\n"
                       f"**Роль поддержки:** {support_role.mention if support_role else 'Не настроена'}\n"
                       f"**Канал логов:** {log_channel.mention if log_channel else 'Не настроен'}\n"
                       f"**Макс. тикетов:** {max_tickets}\n"
                       f"**КД:** {cooldown} сек",
            color=disnake.Color.green()
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(name="ticket_close", description="Закрыть тикет")
    @commands.has_permissions(manage_channels=True)
    async def ticket_close(self, inter: disnake.ApplicationCommandInteraction,
                          reason: str = commands.Param(description="Причина закрытия", default="Не указана"),
                          user: disnake.Member = commands.Param(description="Пользователь для закрытия тикета", default=None)):
        
        if user:
            # Закрыть тикет пользователя
            async with aiosqlite.connect(self.path) as db:
                ticket = await db.execute(
                    "SELECT * FROM tickets WHERE author_id = ? AND guild_id = ? AND status = 'open'",
                    (user.id, inter.guild.id)
                ).fetchone()
                
                if not ticket:
                    await inter.response.send_message(f"❌ У {user.mention} нет открытых тикетов.", ephemeral=True)
                    return
                
                channel = inter.guild.get_channel(ticket[4])
                if channel:
                    await self.process_ticket_close(ticket[0], channel, inter.author.id, reason)
                    await inter.response.send_message(f"✅ Тикет пользователя {user.mention} закрыт.", ephemeral=True)
                else:
                    await inter.response.send_message("❌ Канал тикета не найден.", ephemeral=True)
        else:
            # Закрыть текущий тикет
            async with aiosqlite.connect(self.path) as db:
                ticket = await db.execute(
                    "SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)
                ).fetchone()
                
                if not ticket:
                    await inter.response.send_message("❌ Этот канал не является тикетом.", ephemeral=True)
                    return
                
                await self.process_ticket_close(ticket[0], inter.channel, inter.author.id, reason)
                await inter.response.send_message("✅ Тикет закрыт.", ephemeral=True)

    @commands.slash_command(name="ticket_add", description="Добавить пользователя в тикет")
    @commands.has_permissions(manage_channels=True)
    async def ticket_add(self, inter: disnake.ApplicationCommandInteraction,
                        user: disnake.Member = commands.Param(description="Пользователь для добавления")):
        
        async with aiosqlite.connect(self.path) as db:
            ticket = await db.execute(
                "SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)
            ).fetchone()
            
            if not ticket:
                await inter.response.send_message("❌ Этот канал не является тикетом.", ephemeral=True)
                return
            
            await inter.channel.set_permissions(user, read_messages=True, send_messages=True)
            
            embed = disnake.Embed(
                title="👥 Пользователь добавлен",
                description=f"{user.mention} был добавлен в тикет.",
                color=disnake.Color.green()
            )
            await inter.response.send_message(embed=embed)
            
            # Уведомляем пользователя
            try:
                await user.send(f"📨 Вас добавили в тикет на сервере **{inter.guild.name}**: {inter.channel.mention}")
            except:
                pass

    @commands.slash_command(name="ticket_remove", description="Удалить пользователя из тикета")
    @commands.has_permissions(manage_channels=True)
    async def ticket_remove(self, inter: disnake.ApplicationCommandInteraction,
                           user: disnake.Member = commands.Param(description="Пользователь для удаления")):
        
        async with aiosqlite.connect(self.path) as db:
            ticket = await db.execute(
                "SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)
            ).fetchone()
            
            if not ticket:
                await inter.response.send_message("❌ Этот канал не является тикетом.", ephemeral=True)
                return
            
            if user.id == ticket[1]:  # Автора тикета нельзя удалить
                await inter.response.send_message("❌ Нельзя удалить автора тикета.", ephemeral=True)
                return
            
            await inter.channel.set_permissions(user, overwrite=None)
            
            embed = disnake.Embed(
                title="👥 Пользователь удален",
                description=f"{user.mention} был удален из тикета.",
                color=disnake.Color.red()
            )
            await inter.response.send_message(embed=embed)

    @commands.slash_command(name="ticket_transcript", description="Получить транскрипт тикета")
    @commands.has_permissions(manage_channels=True)
    async def ticket_transcript(self, inter: disnake.ApplicationCommandInteraction,
                               ticket_id: int = commands.Param(description="ID тикета (оставьте пустым для текущего)", default=None)):
        
        if ticket_id:
            # Получить транскрипт по ID
            async with aiosqlite.connect(self.path) as db:
                transcript = await db.execute(
                    "SELECT content FROM transcripts WHERE ticket_id = ? ORDER BY id DESC LIMIT 1",
                    (ticket_id,)
                ).fetchone()
                
                if transcript:
                    file = disnake.File(
                        io.StringIO(transcript[0]),
                        filename=f"ticket_{ticket_id}.txt"
                    )
                    await inter.response.send_message("Вот транскрипт тикета:", file=file, ephemeral=True)
                else:
                    await inter.response.send_message("❌ Транскрипт не найден.", ephemeral=True)
        else:
            # Получить транскрипт текущего тикета
            async with aiosqlite.connect(self.path) as db:
                ticket = await db.execute(
                    "SELECT id FROM tickets WHERE channel_id = ?", (inter.channel.id,)
                ).fetchone()
                
                if not ticket:
                    await inter.response.send_message("❌ Этот канал не является тикетом.", ephemeral=True)
                    return
                
                transcript_content = await self.save_transcript(ticket[0], inter.channel)
                
                file = disnake.File(
                    io.StringIO(transcript_content),
                    filename=f"ticket_{ticket[0]}.txt"
                )
                await inter.response.send_message("Вот транскрипт тикета:", file=file, ephemeral=True)

    @commands.slash_command(name="ticket_stats", description="Статистика тикетов")
    @commands.has_permissions(manage_channels=True)
    async def ticket_stats(self, inter: disnake.ApplicationCommandInteraction):
        async with aiosqlite.connect(self.path) as db:
            # Общая статистика
            total = await db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ?", (inter.guild.id,)
            ).fetchone()
            
            open_tickets = await db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'", (inter.guild.id,)
            ).fetchone()
            
            closed_tickets = await db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'closed'", (inter.guild.id,)
            ).fetchone()
            
            # Топ пользователей по тикетам
            top_users = await db.execute("""
                SELECT author_id, COUNT(*) as ticket_count 
                FROM tickets WHERE guild_id = ? 
                GROUP BY author_id 
                ORDER BY ticket_count DESC 
                LIMIT 5
            """, (inter.guild.id,)).fetchall()
            
            embed = disnake.Embed(
                title="📊 Статистика тикетов",
                color=disnake.Color.blue()
            )
            
            embed.add_field(name="Всего тикетов", value=str(total[0]), inline=True)
            embed.add_field(name="Открытых", value=str(open_tickets[0]), inline=True)
            embed.add_field(name="Закрытых", value=str(closed_tickets[0]), inline=True)
            
            if top_users:
                users_text = ""
                for user_id, count in top_users:
                    user = inter.guild.get_member(user_id)
                    name = user.mention if user else f"ID: {user_id}"
                    users_text += f"{name}: {count} тикетов\n"
                embed.add_field(name="Топ пользователей", value=users_text, inline=False)
            
            await inter.response.send_message(embed=embed)

    async def process_ticket_close(self, ticket_id, channel, moderator_id, reason):
        """Обработка закрытия тикета"""
        
        # Сохраняем транскрипт
        transcript_content = await self.save_transcript(ticket_id, channel)
        
        # Обновляем статус в БД
        await self.close_ticket(ticket_id, moderator_id, reason)
        
        # Логируем закрытие
        ticket_info = await self.get_ticket_info(ticket_id)
        config = await self.get_ticket_config(channel.guild.id)
        
        if config['log_channel_id']:
            log_channel = channel.guild.get_channel(config['log_channel_id'])
            if log_channel:
                embed = disnake.Embed(
                    title="🎫 Тикет закрыт",
                    description=f"**Тикет:** #{ticket_id}\n"
                              f"**Автор:** <@{ticket_info['author_id']}>\n"
                              f"**Модератор:** <@{moderator_id}>\n"
                              f"**Причина:** {reason}\n"
                              f"**Тип:** {ticket_info['ticket_type']}\n"
                              f"**Создан:** {ticket_info['created_at']}\n"
                              f"**Закрыт:** {ticket_info['closed_at']}",
                    color=disnake.Color.red()
                )
                await log_channel.send(embed=embed)
                
                # Отправляем транскрипт как файл
                if transcript_content:
                    file = disnake.File(
                        io.StringIO(transcript_content),
                        filename=f"ticket_{ticket_id}.txt"
                    )
                    await log_channel.send(file=file)
        
        # Отсчет перед удалением
        embed = disnake.Embed(
            title="🔒 Тикет закрыт",
            description=f"**Причина:** {reason}\n\nКанал будет удален через 10 секунд.",
            color=disnake.Color.red()
        )
        await channel.send(embed=embed)
        
        for i in range(9, -1, -1):
            await asyncio.sleep(1)
            if i <= 5:
                embed.description = f"**Причина:** {reason}\n\nКанал будет удален через {i} секунд."
                await channel.send(embed=embed)
        
        await channel.delete()

    async def check_auto_close_tickets(self):
        """Проверка автозакрытия тикетов"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                async with aiosqlite.connect(self.path) as db:
                    tickets = await db.execute("""
                        SELECT t.id, t.channel_id, t.guild_id, t.created_at, c.auto_close_hours 
                        FROM tickets t 
                        JOIN ticket_config c ON t.guild_id = c.guild_id 
                        WHERE t.status = 'open' AND c.auto_close_hours > 0
                    """).fetchall()
                    
                    for ticket in tickets:
                        ticket_id, channel_id, guild_id, created_at_str, auto_close_hours = ticket
                        
                        created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                        now = datetime.now()
                        
                        if (now - created_at).total_seconds() > (auto_close_hours * 3600):
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                await self.process_ticket_close(
                                    ticket_id, channel, self.bot.user.id, 
                                    f"Автоматическое закрытие (неактивность более {auto_close_hours} часов)"
                                )
            
            except Exception as e:
                print(f"Ошибка в проверке автозакрытия: {e}")
            
            await asyncio.sleep(3600)

    @commands.Cog.listener()
    async def on_button_click(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id
        
        if custom_id.startswith("create_ticket_"):
            ticket_type = custom_id.replace("create_ticket_", "")
            await self.handle_ticket_creation(inter, ticket_type)
        
        elif custom_id == "accept_ticket":
            await self.handle_ticket_accept(inter)
        
        elif custom_id == "close_ticket":
            # Открываем модальное окно для указания причины
            modal = TicketCloseModal()
            await inter.response.send_modal(modal)

    @commands.Cog.listener()
    async def on_modal_submit(self, inter: disnake.ModalInteraction):
        if inter.custom_id == "ticket_close_modal":
            reason = inter.text_values["reason"] or "Не указана"
            
            async with aiosqlite.connect(self.path) as db:
                ticket = await db.execute(
                    "SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)
                ).fetchone()
                
                if not ticket:
                    await inter.response.send_message("❌ Тикет не найден.", ephemeral=True)
                    return
                
                await self.process_ticket_close(ticket[0], inter.channel, inter.author.id, reason)
                await inter.response.defer()

    async def handle_ticket_creation(self, inter: disnake.MessageInteraction, ticket_type):
        """Обработка создания тикета"""
        config = await self.get_ticket_config(inter.guild.id)
        
        # Проверка кд
        user_cooldown = self.ticket_cooldowns.get(inter.author.id)
        if user_cooldown and (datetime.now() - user_cooldown).total_seconds() < config['ticket_cooldown']:
            remaining = config['ticket_cooldown'] - int((datetime.now() - user_cooldown).total_seconds())
            await inter.response.send_message(
                f"❌ Подождите {remaining} секунд перед созданием нового тикета.",
                ephemeral=True
            )
            return
        
        # Проверка лимита тикетов
        user_tickets = await self.get_user_tickets_count(inter.guild.id, inter.author.id)
        if user_tickets >= config['max_tickets_per_user']:
            await inter.response.send_message(
                f"❌ У вас уже {user_tickets} открытых тикетов. Максимум: {config['max_tickets_per_user']}.",
                ephemeral=True
            )
            return
        
        # Создаем тикет
        if not config['category_id']:
            await inter.response.send_message("❌ Система тикетов не настроена.", ephemeral=True)
            return
        
        category = inter.guild.get_channel(config['category_id'])
        if not category:
            await inter.response.send_message("❌ Категория тикетов не найдена.", ephemeral=True)
            return
        
        # Создаем канал тикета
        ticket_channel = await inter.guild.create_text_channel(
            name=f"ticket-{inter.author.name}-{datetime.now().strftime('%d%m')}",
            category=category,
            topic=f"Тикет пользователя {inter.author.name} | Тип: {ticket_type}"
        )
        
        # Настраиваем права
        await ticket_channel.set_permissions(inter.author, read_messages=True, send_messages=True)
        await ticket_channel.set_permissions(inter.guild.default_role, read_messages=False)
        
        if config['support_role_id']:
            support_role = inter.guild.get_role(config['support_role_id'])
            if support_role:
                await ticket_channel.set_permissions(support_role, read_messages=True, send_messages=True)
        
        # Создаем запись в БД
        ticket_id = await self.create_ticket(inter.guild.id, inter.author.id, ticket_channel.id, ticket_type)
        
        # Устанавливаем кд
        self.ticket_cooldowns[inter.author.id] = datetime.now()
        
        # Отправляем приветственное сообщение
        view = TicketActionsView()
        
        embed = disnake.Embed(
            title=f"🎫 Тикет #{ticket_id}",
            description=config['welcome_message'],
            color=disnake.Color.green()
        )
        embed.add_field(name="👤 Автор", value=inter.author.mention, inline=True)
        embed.add_field(name="📅 Создан", value=datetime.now().strftime("%d.%m.%Y %H:%M"), inline=True)
        embed.add_field(name="🔖 Тип", value=ticket_type.capitalize(), inline=True)
        embed.set_footer(text="Тикет будет автоматически закрыт через 24 часа неактивности")
        
        await ticket_channel.send(embed=embed, view=view)
        await ticket_channel.send(f"{inter.author.mention} {f'<@&{config['support_role_id']}>' if config['support_role_id'] else ''}")
        
        await inter.response.send_message(
            f"✅ Тикет создан: {ticket_channel.mention}",
            ephemeral=True
        )
        
        # Логируем создание
        if config['log_channel_id']:
            log_channel = inter.guild.get_channel(config['log_channel_id'])
            if log_channel:
                embed = disnake.Embed(
                    title="🎫 Новый тикет",
                    description=f"**Тикет:** #{ticket_id}\n"
                              f"**Автор:** {inter.author.mention} ({inter.author.id})\n"
                              f"**Тип:** {ticket_type}\n"
                              f"**Канал:** {ticket_channel.mention}",
                    color=disnake.Color.green()
                )
                await log_channel.send(embed=embed)

    async def handle_ticket_accept(self, inter: disnake.MessageInteraction):
        """Обработка принятия тикета"""
        async with aiosqlite.connect(self.path) as db:
            ticket = await db.execute(
                "SELECT * FROM tickets WHERE channel_id = ?", (inter.channel.id,)
            ).fetchone()
            
            if not ticket:
                await inter.response.send_message("❌ Тикет не найден.", ephemeral=True)
                return
            
            if ticket[5]:  # moderator_id
                await inter.response.send_message(
                    f"❌ Тикет уже принят пользователем <@{ticket[5]}>.",
                    ephemeral=True
                )
                return
            
            await self.add_ticket_moderator(ticket[0], inter.author.id)
            
            embed = disnake.Embed(
                title="✅ Тикет принят",
                description=f"Модератор {inter.author.mention} принял тикет.",
                color=disnake.Color.green()
            )
            await inter.channel.send(embed=embed)
            
            await inter.response.send_message("✅ Вы приняли тикет.", ephemeral=True)

class TicketCreateView(View):
    """View для создания тикета с выбором типа"""
    
    def __init__(self, bot, config):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        
        # Добавляем кнопки для каждого типа тикета
        for ticket_type in self.config['ticket_types']:
            emoji = self.get_emoji_for_type(ticket_type)
            button = Button(
                label=ticket_type.capitalize(),
                emoji=emoji,
                style=disnake.ButtonStyle.primary,
                custom_id=f"create_ticket_{ticket_type}"
            )
            self.add_item(button)
    
    def get_emoji_for_type(self, ticket_type):
        emojis = {
            'general': '🎫',
            'report': '⚠️',
            'bug': '🐛',
            'support': '🛠️',
            'question': '❓',
            'suggestion': '💡',
            'other': '📝'
        }
        return emojis.get(ticket_type, '🎫')

class TicketActionsView(View):
    """View для управления тикетом"""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        accept_button = Button(
            label="✅ Принять",
            style=disnake.ButtonStyle.green,
            custom_id="accept_ticket",
            emoji="✅"
        )
        self.add_item(accept_button)
        
        close_button = Button(
            label="❌ Закрыть",
            style=disnake.ButtonStyle.red,
            custom_id="close_ticket",
            emoji="❌"
        )
        self.add_item(close_button)
        
        transcript_button = Button(
            label="📋 Транскрипт",
            style=disnake.ButtonStyle.blurple,
            custom_id="transcript_ticket",
            emoji="📋"
        )
        self.add_item(transcript_button)

class TicketCloseModal(Modal):
    """Модальное окно для закрытия тикета"""
    
    def __init__(self):
        components = [
            TextInput(
                label="Причина закрытия",
                placeholder="Укажите причину закрытия тикета...",
                custom_id="reason",
                style=disnake.TextInputStyle.long,
                max_length=500,
                required=False
            )
        ]
        super().__init__(title="Закрытие тикета", custom_id="ticket_close_modal", components=components)

def setup(bot):
    bot.add_cog(TicketSystem(bot))
