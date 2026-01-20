# logs.py
import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.path = "v1rago/dbs/file.db"

    async def init_db(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS logs (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER DEFAULT NULL,
                log_messages INTEGER DEFAULT 1,
                log_moderation INTEGER DEFAULT 1,
                log_voice INTEGER DEFAULT 1,
                log_members INTEGER DEFAULT 1,
                log_tickets INTEGER DEFAULT 1
            )""")
            await db.commit()

    async def get_log_channel(self, guild_id):
        async with aiosqlite.connect(self.path) as db:
            result = await db.execute("SELECT channel_id FROM logs WHERE guild_id = ?", (guild_id,)).fetchone()
            return result[0] if result else None

    async def get_log_settings(self, guild_id, log_type):
        """Получить настройки логов для конкретного типа"""
        async with aiosqlite.connect(self.path) as db:
            result = await db.execute(f"SELECT {log_type} FROM logs WHERE guild_id = ?", (guild_id,)).fetchone()
            return result[0] if result else 1

    async def log_event(self, guild, embed):
        channel_id = await self.get_log_channel(guild.id)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except:
                    pass

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_db()

    @commands.slash_command(name="setup_logs", description="Настроить канал для логов")
    @commands.has_permissions(administrator=True)
    async def setup_logs(self, ctx,
                         channel: discord.TextChannel = commands.Option(description="Канал для логов")):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR REPLACE INTO logs (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, channel.id))
            await db.commit()
        
        embed = discord.Embed(title="📝 Логи настроены", description=f"Логи будут отправляться в {channel.mention}", color=0x00ff00)
        await ctx.respond(embed=embed, ephemeral=True)

    @commands.slash_command(name="log_settings", description="Настройки логов")
    @commands.has_permissions(administrator=True)
    async def log_settings(self, ctx,
                           messages: bool = commands.Option(default=True, description="Логировать сообщения"),
                           moderation: bool = commands.Option(default=True, description="Логировать модерацию"),
                           voice: bool = commands.Option(default=True, description="Логировать голосовые"),
                           members: bool = commands.Option(default=True, description="Логировать участников"),
                           tickets: bool = commands.Option(default=True, description="Логировать тикеты")):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""INSERT OR REPLACE INTO logs 
                             (guild_id, log_messages, log_moderation, log_voice, log_members, log_tickets) 
                             VALUES (?, ?, ?, ?, ?, ?)""", 
                           (ctx.guild.id, int(messages), int(moderation), int(voice), int(members), int(tickets)))
            await db.commit()
        
        embed = discord.Embed(title="⚙️ Настройки логов", color=0x00ff00)
        embed.add_field(name="Сообщения", value="✅" if messages else "❌")
        embed.add_field(name="Модерация", value="✅" if moderation else "❌")
        embed.add_field(name="Голосовые", value="✅" if voice else "❌")
        embed.add_field(name="Участники", value="✅" if members else "❌")
        embed.add_field(name="Тикеты", value="✅" if tickets else "❌")
        await ctx.respond(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if await self.get_log_settings(guild.id, "log_moderation") == 0:
            return
        
        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=5):
            if entry.target.id == user.id:
                moderator = entry.user
                reason = entry.reason or "Не указана"
                break
        else:
            moderator = self.bot.user
            reason = "Неизвестно"
        
        embed = discord.Embed(title="🚫 Бан", color=0xff0000, timestamp=datetime.now())
        embed.add_field(name="Пользователь", value=f"{user} ({user.id})", inline=False)
        embed.add_field(name="Модератор", value=f"{moderator.mention} ({moderator.id})", inline=False)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.set_footer(text="ID пользователя")
        await self.log_event(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if await self.get_log_settings(guild.id, "log_moderation") == 0:
            return
        
        async for entry in guild.audit_logs(action=discord.AuditLogAction.unban, limit=5):
            if entry.target.id == user.id:
                moderator = entry.user
                reason = entry.reason or "Не указана"
                break
        else:
            moderator = self.bot.user
            reason = "Неизвестно"
        
        embed = discord.Embed(title="✅ Разбан", color=0x00ff00, timestamp=datetime.now())
        embed.add_field(name="Пользователь", value=f"{user} ({user.id})", inline=False)
        embed.add_field(name="Модератор", value=f"{moderator.mention} ({moderator.id})", inline=False)
        embed.add_field(name="Причина", value=reason, inline=False)
        await self.log_event(guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if await self.get_log_settings(member.guild.id, "log_members") == 0:
            return
        
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=5):
            if entry.target.id == member.id:
                if await self.get_log_settings(member.guild.id, "log_moderation") == 0:
                    return
                
                moderator = entry.user
                reason = entry.reason or "Не указана"
                
                embed = discord.Embed(title="👢 Кик", color=0xff9900, timestamp=datetime.now())
                embed.add_field(name="Пользователь", value=f"{member} ({member.id})", inline=False)
                embed.add_field(name="Модератор", value=f"{moderator.mention} ({moderator.id})", inline=False)
                embed.add_field(name="Причина", value=reason, inline=False)
                embed.set_thumbnail(url=member.display_avatar.url)
                await self.log_event(member.guild, embed)
                return
        
        embed = discord.Embed(title="👋 Участник вышел", color=0xff9900, timestamp=datetime.now())
        embed.add_field(name="Пользователь", value=f"{member} ({member.id})", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.log_event(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.timed_out_until != after.timed_out_until:
            if await self.get_log_settings(after.guild.id, "log_moderation") == 0:
                return
            
            async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_update, limit=10):
                if entry.target.id == after.id and hasattr(entry.after, 'timed_out_until'):
                    moderator = entry.user
                    reason = entry.reason or "Не указана"
                    
                    embed = discord.Embed(
                        title="🔇 Мьют" if after.timed_out_until else "🔊 Размьют",
                        color=0xff9900 if after.timed_out_until else 0x00ff00,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Пользователь", value=f"{after.mention} ({after.id})", inline=False)
                    embed.add_field(name="Модератор", value=f"{moderator.mention} ({moderator.id})", inline=False)
                    embed.add_field(name="Причина", value=reason, inline=False)
                    
                    if after.timed_out_until:
                        duration = after.timed_out_until - datetime.now(datetime.timezone.utc)
                        hours = int(duration.total_seconds() // 3600)
                        minutes = int((duration.total_seconds() % 3600) // 60)
                        embed.add_field(name="Длительность", value=f"{hours}ч {minutes}м", inline=False)
                    
                    await self.log_event(after.guild, embed)
                    break

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if await self.get_log_settings(member.guild.id, "log_members") == 0:
            return
        
        embed = discord.Embed(title="👋 Участник присоединился", color=0x00ff00, timestamp=datetime.now())
        embed.add_field(name="Пользователь", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Аккаунт создан", value=member.created_at.strftime("%d.%m.%Y %H:%M"), inline=False)
        
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=5):
            if entry.target.id == member.id:
                embed.add_field(name="Приглашен", value="через интеграцию", inline=False)
                break
        
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.log_event(member.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
        
        if await self.get_log_settings(message.guild.id, "log_messages") == 0:
            return
        
        async for entry in message.guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=5):
            if hasattr(entry.extra, 'channel') and entry.extra.channel.id == message.channel.id:
                if (datetime.now() - entry.created_at).total_seconds() < 2:
                    moderator = entry.user
                    break
        else:
            moderator = message.author
        
        embed = discord.Embed(title="🗑️ Сообщение удалено", color=0xff0000, timestamp=datetime.now())
        embed.add_field(name="Автор", value=f"{message.author.mention} ({message.author.id})", inline=False)
        embed.add_field(name="Канал", value=message.channel.mention, inline=False)
        
        if moderator != message.author:
            embed.add_field(name="Удалил", value=f"{moderator.mention} ({moderator.id})", inline=False)
        
        if message.content:
            content = message.content[:1000] + "..." if len(message.content) > 1000 else message.content
            embed.add_field(name="Содержимое", value=content, inline=False)
        
        if message.attachments:
            files = "\n".join([f"[{att.filename}]({att.url})" for att in message.attachments[:3]])
            embed.add_field(name="Вложения", value=files, inline=False)
        
        await self.log_event(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content or not before.guild:
            return
        
        if await self.get_log_settings(before.guild.id, "log_messages") == 0:
            return
        
        embed = discord.Embed(title="📝 Сообщение изменено", color=0xffff00, timestamp=datetime.now())
        embed.add_field(name="Автор", value=f"{before.author.mention} ({before.author.id})", inline=False)
        embed.add_field(name="Канал", value=before.channel.mention, inline=False)
        
        before_content = before.content[:500] or "Пусто"
        after_content = after.content[:500] or "Пусто"
        
        embed.add_field(name="Было", value=before_content, inline=False)
        embed.add_field(name="Стало", value=after_content, inline=False)
        embed.add_field(name="Ссылка", value=f"[Перейти]({after.jump_url})", inline=False)
        
        await self.log_event(before.guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild:
            return
            
        if await self.get_log_settings(member.guild.id, "log_voice") == 0:
            return
        
        if before.channel != after.channel:
            embed = discord.Embed(title="🔊 Голосовой статус", color=0x00aaff, timestamp=datetime.now())
            embed.add_field(name="Участник", value=f"{member.mention} ({member.id})", inline=False)
            
            if before.channel and not after.channel:
                embed.description = "🔇 Вышел из голосового"
                embed.add_field(name="Канал", value=before.channel.name, inline=False)
            elif not before.channel and after.channel:
                embed.description = "🎤 Вошел в голосовой"
                embed.add_field(name="Канал", value=after.channel.name, inline=False)
            elif before.channel and after.channel:
                embed.description = "🔄 Перешел в другой канал"
                embed.add_field(name="Из канала", value=before.channel.name, inline=False)
                embed.add_field(name="В канал", value=after.channel.name, inline=False)
            
            await self.log_event(member.guild, embed)

async def setup(bot):
    await bot.add_cog(Logs(bot))
