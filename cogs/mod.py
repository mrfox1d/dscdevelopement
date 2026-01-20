# mod.py
import discord
from discord.ext import commands
import aiosqlite
import datetime
from datetime import timedelta
import asyncio

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.path = "v1rago/dbs/file.db"

    async def init_db(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT,
                    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active TEXT DEFAULT "true"
                )""")
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS punishments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    duration TEXT,
                    reason TEXT,
                    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    guild_id INTEGER NOT NULL
                )""")
            await db.commit()

    async def warn_user(self, user_id: int, moderator_id: int, reason: str = None):
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO warnings (user_id, moderator_id, reason) VALUES (?, ?, ?)", 
                (user_id, moderator_id, reason)
            )
            await db.commit()
            return cursor.lastrowid

    async def log_punishment(self, guild_id: int, user_id: int, moderator_id: int, action_type: str, duration: str = None, reason: str = None):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO punishments (guild_id, user_id, moderator_id, action_type, duration, reason) 
                VALUES (?, ?, ?, ?, ?, ?)""",
                (guild_id, user_id, moderator_id, action_type, duration, reason)
            )
            await db.commit()

    async def unwarn_user(self, user_id: int, by_moderator: bool = False, warn_id: int = None):
        async with aiosqlite.connect(self.path) as db:
            if by_moderator:
                if warn_id:
                    await db.execute("UPDATE warnings SET active = 'false' WHERE id = ? AND user_id = ?", 
                                    (warn_id, user_id))
                else:
                    await db.execute("UPDATE warnings SET active = 'false' WHERE user_id = ? AND active = 'true'", 
                                    (user_id,))
                await db.commit()
                return True
            return False

    async def get_warnings_count(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            count = await db.execute(
                "SELECT COUNT(*) FROM warnings WHERE user_id = ? AND active = 'true'", 
                (user_id,)
            ).fetchone()
            return count[0] if count else 0

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_db()

    @commands.slash_command(name="mute", description="Выдать мьют пользователю на сервере.")
    @commands.has_permissions(mute_members=True)
    async def mute(self, ctx,
                   user: discord.Member = commands.Option(description="Выберите пользователя."),
                   duration: str = commands.Option(description="Время (пример: 1ч, 30м, 1д). Макс: 28д", default="1ч"),
                   reason: str = commands.Option(description="Причина", default="Не указана")):
        
        if user.top_role >= ctx.author.top_role:
            await ctx.respond("❌ Вы не можете замутить этого пользователя.", ephemeral=True)
            return
        
        time_multipliers = {
            'с': 1,
            'м': 60,
            'ч': 3600,
            'д': 86400,
            'н': 604800
        }
        
        try:
            time_value = int(duration[:-1])
            time_unit = duration[-1].lower()
            
            if time_unit not in time_multipliers:
                raise ValueError
            
            seconds = time_value * time_multipliers[time_unit]
            
            if seconds > 2419200:
                await ctx.respond("❌ Максимальное время мьюта - 28 суток.", ephemeral=True)
                return
            
            await user.timeout(discord.utils.utcnow() + timedelta(seconds=seconds), reason=f"{reason} | Модератор: {ctx.author}")
            
            await self.log_punishment(
                ctx.guild.id, user.id, ctx.author.id, "mute", duration, reason
            )
            
            embed = discord.Embed(
                title="🔇 Мьют выдан",
                description=f"**Пользователь:** {user.mention}\n**Время:** {duration}\n**Причина:** {reason}",
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"Модератор: {ctx.author}")
            
            await ctx.respond(embed=embed)
            
            try:
                await user.send(f"🔇 Вы получили мьют на сервере **{ctx.guild.name}** на **{duration}**.\n**Причина:** {reason}\n**Модератор:** {ctx.author}")
            except:
                pass
                
        except ValueError:
            await ctx.respond("❌ Неверный формат времени. Используйте: 1ч, 30м, 2д и т.д.", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ Ошибка: {str(e)}", ephemeral=True)

    @commands.slash_command(name="unmute", description="Снять мьют с пользователя.")
    @commands.has_permissions(mute_members=True)
    async def unmute(self, ctx,
                     user: discord.Member = commands.Option(description="Выберите пользователя."),
                     reason: str = commands.Option(description="Причина", default="Не указана")):
        
        try:
            await user.timeout(None, reason=f"{reason} | Модератор: {ctx.author}")
            
            await self.log_punishment(
                ctx.guild.id, user.id, ctx.author.id, "unmute", None, reason
            )
            
            embed = discord.Embed(
                title="🔊 Мьют снят",
                description=f"**Пользователь:** {user.mention}\n**Причина:** {reason}",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Модератор: {ctx.author}")
            
            await ctx.respond(embed=embed)
            
            try:
                await user.send(f"🔊 Ваш мьют был снят на сервере **{ctx.guild.name}**.\n**Причина:** {reason}\n**Модератор:** {ctx.author}")
            except:
                pass
                
        except Exception as e:
            await ctx.respond(f"❌ Ошибка: {str(e)}", ephemeral=True)

    @commands.slash_command(name="kick", description="Выдать кик пользователю.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx,
                   user: discord.Member = commands.Option(description="Выберите пользователя."),
                   reason: str = commands.Option(description="Причина", default="Не указана")):
        
        if user.top_role >= ctx.author.top_role:
            await ctx.respond("❌ Вы не можете кикнуть этого пользователя.", ephemeral=True)
            return
        
        try:
            await user.kick(reason=f"{reason} | Модератор: {ctx.author}")
            
            await self.log_punishment(
                ctx.guild.id, user.id, ctx.author.id, "kick", None, reason
            )
            
            embed = discord.Embed(
                title="👢 Кик",
                description=f"**Пользователь:** {user.mention}\n**Причина:** {reason}",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Модератор: {ctx.author}")
            
            await ctx.respond(embed=embed)
            
            try:
                await user.send(f"👢 Вы были кикнуты с сервера **{ctx.guild.name}**.\n**Причина:** {reason}\n**Модератор:** {ctx.author}")
            except:
                pass
                
        except Exception as e:
            await ctx.respond(f"❌ Ошибка: {str(e)}", ephemeral=True)

    @commands.slash_command(name="ban", description="Выдать бан пользователю.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx,
                  user: discord.Member = commands.Option(description="Выберите пользователя."),
                  reason: str = commands.Option(description="Причина", default="Не указана"),
                  delete_days: int = commands.Option(default=0, description="Удалить сообщения за N дней", min_value=0, max_value=7)):
        
        if user.top_role >= ctx.author.top_role:
            await ctx.respond("❌ Вы не можете забанить этого пользователя.", ephemeral=True)
            return
        
        try:
            await user.ban(reason=f"{reason} | Модератор: {ctx.author}", delete_message_days=delete_days)
            
            await self.log_punishment(
                ctx.guild.id, user.id, ctx.author.id, "ban", None, reason
            )
            
            embed = discord.Embed(
                title="🚫 Бан",
                description=f"**Пользователь:** {user.mention}\n**Причина:** {reason}\n**Удалено сообщений:** {delete_days} дней",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text=f"Модератор: {ctx.author}")
            
            await ctx.respond(embed=embed)
            
            try:
                await user.send(f"🚫 Вы были забанены на сервере **{ctx.guild.name}**.\n**Причина:** {reason}\n**Модератор:** {ctx.author}")
            except:
                pass
                
        except Exception as e:
            await ctx.respond(f"❌ Ошибка: {str(e)}", ephemeral=True)

    @commands.slash_command(name="unban", description="Снять бан с пользователя.")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx,
                    user_id: str = commands.Option(description="ID пользователя для разбана."),
                    reason: str = commands.Option(description="Причина", default="Не указана")):
        
        try:
            user_id_int = int(user_id)
            user = await self.bot.fetch_user(user_id_int)
            
            await ctx.guild.unban(user, reason=f"{reason} | Модератор: {ctx.author}")
            
            await self.log_punishment(
                ctx.guild.id, user.id, ctx.author.id, "unban", None, reason
            )
            
            embed = discord.Embed(
                title="✅ Разбан",
                description=f"**Пользователь:** {user.mention}\n**Причина:** {reason}",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Модератор: {ctx.author}")
            
            await ctx.respond(embed=embed)
            
            try:
                await user.send(f"✅ Вы были разбанены на сервере **{ctx.guild.name}**.\n**Причина:** {reason}\n**Модератор:** {ctx.author}")
            except:
                pass
                
        except ValueError:
            await ctx.respond("❌ Неверный ID пользователя.", ephemeral=True)
        except discord.NotFound:
            await ctx.respond("❌ Пользователь не найден или не забанен.", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ Ошибка: {str(e)}", ephemeral=True)

    @commands.slash_command(name="clear", description="Очистить сообщения в канале.")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx,
                    amount: int = commands.Option(description="Количество сообщений (1-100)", min_value=1, max_value=100)):
        
        await ctx.defer(ephemeral=True)
        
        try:
            deleted = await ctx.channel.purge(limit=amount)
            
            await self.log_punishment(
                ctx.guild.id, 0, ctx.author.id, "clear", str(amount), f"Очистка в #{ctx.channel.name}"
            )
            
            embed = discord.Embed(
                title="🗑️ Очистка сообщений",
                description=f"Удалено **{len(deleted)}** сообщений в {ctx.channel.mention}",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Модератор: {ctx.author}")
            
            await ctx.respond(embed=embed, ephemeral=True)
            
            await asyncio.sleep(5)
            await ctx.message.delete()
            
        except Exception as e:
            await ctx.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

    @commands.slash_command(name="warn", description="Выдать предупреждение пользователю.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx,
                   user: discord.Member = commands.Option(description="Выберите пользователя."),
                   reason: str = commands.Option(description="Укажите причину.", default="Не указана")):
        
        if user.top_role >= ctx.author.top_role:
            await ctx.respond("❌ Вы не можете выдать предупреждение этому пользователю.", ephemeral=True)
            return
        
        warn_id = await self.warn_user(user.id, ctx.author.id, reason)
        warnings_count = await self.get_warnings_count(user.id)
        
        await self.log_punishment(
            ctx.guild.id, user.id, ctx.author.id, "warn", None, reason
        )
        
        embed = discord.Embed(
            title="⚠️ Предупреждение выдано",
            description=f"**Пользователь:** {user.mention}\n**Причина:** {reason}\n**Всего предупреждений:** {warnings_count}",
            color=discord.Color.yellow()
        )
        embed.set_footer(text=f"ID предупреждения: {warn_id} | Модератор: {ctx.author}")
        
        await ctx.respond(embed=embed)
        
        try:
            await user.send(f"⚠️ Вы получили предупреждение на сервере **{ctx.guild.name}**.\n**Причина:** {reason}\n**Всего предупреждений:** {warnings_count}\n**Модератор:** {ctx.author}")
        except:
            pass

    @commands.slash_command(name="unwarn", description="Снять предупреждение с пользователя.")
    @commands.has_permissions(manage_messages=True)
    async def unwarn(self, ctx,
                     user: discord.Member = commands.Option(description="Выберите пользователя."),
                     warn_id: int = commands.Option(description="ID предупреждения (оставьте пустым для всех)", default=None),
                     reason: str = commands.Option(description="Причина", default="Не указана")):
        
        success = await self.unwarn_user(user.id, True, warn_id)
        
        if success:
            await self.log_punishment(
                ctx.guild.id, user.id, ctx.author.id, "unwarn", None, f"{reason} | Warn ID: {warn_id or 'all'}"
            )
            
            embed = discord.Embed(
                title="✅ Предупреждение снято",
                description=f"**Пользователь:** {user.mention}\n**Причина:** {reason}",
                color=discord.Color.green()
            )
            if warn_id:
                embed.add_field(name="ID предупреждения", value=str(warn_id))
            embed.set_footer(text=f"Модератор: {ctx.author}")
            
            await ctx.respond(embed=embed)
        else:
            await ctx.respond("❌ Не удалось снять предупреждение.", ephemeral=True)

    @commands.slash_command(name="warnings", description="Посмотреть предупреждения пользователя.")
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx,
                       user: discord.Member = commands.Option(description="Выберите пользователя.")):
        
        async with aiosqlite.connect(self.path) as db:
            warnings = await db.execute(
                """SELECT id, moderator_id, reason, time FROM warnings 
                WHERE user_id = ? AND active = 'true' ORDER BY time DESC""", 
                (user.id,)
            ).fetchall()
        
        if not warnings:
            embed = discord.Embed(
                title=f"Предупреждения {user.display_name}",
                description="✅ Нет активных предупреждений",
                color=discord.Color.green()
            )
            await ctx.respond(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"Предупреждения {user.display_name}",
            description=f"Всего активных предупреждений: **{len(warnings)}**",
            color=discord.Color.orange()
        )
        
        for warn_id, moderator_id, reason, time in warnings[:10]:
            moderator = ctx.guild.get_member(moderator_id) or f"ID: {moderator_id}"
            embed.add_field(
                name=f"ID: {warn_id} | {time}",
                value=f"**Модератор:** {moderator}\n**Причина:** {reason}",
                inline=False
            )
        
        await ctx.respond(embed=embed)

    @commands.slash_command(name="punishments", description="История наказаний пользователя.")
    @commands.has_permissions(manage_messages=True)
    async def punishments(self, ctx,
                          user: discord.Member = commands.Option(description="Выберите пользователя.")):
        
        async with aiosqlite.connect(self.path) as db:
            punishments = await db.execute(
                """SELECT action_type, moderator_id, duration, reason, time FROM punishments 
                WHERE user_id = ? AND guild_id = ? ORDER BY time DESC LIMIT 20""", 
                (user.id, ctx.guild.id)
            ).fetchall()
        
        if not punishments:
            embed = discord.Embed(
                title=f"Наказания {user.display_name}",
                description="📝 Нет записей о наказаниях",
                color=discord.Color.blue()
            )
            await ctx.respond(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"Наказания {user.display_name}",
            description=f"Всего записей: **{len(punishments)}**",
            color=discord.Color.blue()
        )
        
        for action_type, moderator_id, duration, reason, time in punishments:
            moderator = ctx.guild.get_member(moderator_id) or f"ID: {moderator_id}"
            action_emoji = {
                "mute": "🔇", "unmute": "🔊", "kick": "👢", 
                "ban": "🚫", "unban": "✅", "warn": "⚠️", 
                "unwarn": "✅", "clear": "🗑️"
            }.get(action_type, "📝")
            
            value = f"**Модератор:** {moderator}\n**Причина:** {reason}"
            if duration:
                value += f"\n**Длительность:** {duration}"
            
            embed.add_field(
                name=f"{action_emoji} {action_type.upper()} | {time}",
                value=value,
                inline=False
            )
        
        await ctx.respond(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        if message.content.lower() == "-смс" and message.reference:
            if message.channel.permissions_for(message.author).manage_messages:
                try:
                    replied_message = await message.channel.fetch_message(message.reference.message_id)
                    await replied_message.delete()
                    await message.delete()
                except:
                    pass

async def setup(bot):
    await bot.add_cog(Moderation(bot))
