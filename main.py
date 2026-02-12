"""
🤖 UltraBot - Bot Discord Complet et Hautement Configurable
Auteur: v0
Version: 2.0.0

Fonctionnalités:
- Système de tickets avancé avec menus déroulants
- Modération complète (ban, kick, mute, warn, clear)
- Système de niveaux et XP
- Économie avec shop et inventaire
- Giveaways automatiques
- Logs détaillés
- Bienvenue/Au revoir personnalisables
- Auto-modération
- Commandes personnalisées
- Sondages interactifs
- Et bien plus...

Installation:
pip install discord.py aiosqlite python-dotenv
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import asyncio
import json
import random
import datetime
from typing import Optional, Literal
import re
from collections import defaultdict
import os

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION PAR DÉFAUT
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "prefix": "!",
    "language": "fr",
    "welcome": {
        "enabled": False,
        "channel_id": None,
        "message": "Bienvenue {user} sur {server} ! Tu es le membre n°{count} !",
        "dm_enabled": False,
        "dm_message": "Bienvenue sur {server} ! N'hésite pas à lire les règles.",
        "auto_role": None
    },
    "goodbye": {
        "enabled": False,
        "channel_id": None,
        "message": "{user} nous a quittés... Nous étions {count} membres."
    },
    "leveling": {
        "enabled": True,
        "xp_min": 15,
        "xp_max": 25,
        "xp_cooldown": 60,
        "level_up_channel": None,
        "level_up_message": "GG {user} ! Tu viens de passer au niveau **{level}** !",
        "role_rewards": {}
    },
    "economy": {
        "enabled": True,
        "currency_name": "coins",
        "currency_symbol": "🪙",
        "daily_amount": 100,
        "work_min": 50,
        "work_max": 200,
        "work_cooldown": 3600
    },
    "moderation": {
        "log_channel": None,
        "mute_role": None,
        "auto_mod": {
            "enabled": False,
            "anti_spam": True,
            "anti_links": False,
            "anti_caps": False,
            "caps_threshold": 70,
            "max_mentions": 5,
            "banned_words": []
        }
    },
    "tickets": {
        "enabled": True,
        "category_id": None,
        "log_channel": None,
        "support_role": None,
        "categories": [
            {"name": "General Support | Support Général", "emoji": "❓", "description": "General questions | Questions générales"},
            {"name": "Report | Signalement ", "emoji": "🚨", "description": "Report a member | Signaler un problème"},
            {"name": "Buy | Achat", "emoji": "🛒", "description": "Make a purchase | Demande de service"},
            {"name": "Bug Report", "emoji": "🐛", "description": "Report a bug | Signaler un bug"}
        ]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ═══════════════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self, db_path: str = "ultrabot.db"):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        await self.create_tables()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def create_tables(self):
        queries = [
            """CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                config TEXT DEFAULT '{}'
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                balance INTEGER DEFAULT 0,
                bank INTEGER DEFAULT 0,
                daily_timestamp INTEGER DEFAULT 0,
                work_timestamp INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '{}',
                PRIMARY KEY (user_id, guild_id)
            )""",
            """CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                timestamp INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                guild_id INTEGER,
                user_id INTEGER,
                category TEXT,
                status TEXT DEFAULT 'open',
                created_at INTEGER,
                closed_at INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                channel_id INTEGER,
                guild_id INTEGER,
                prize TEXT,
                winners INTEGER DEFAULT 1,
                end_time INTEGER,
                ended INTEGER DEFAULT 0,
                host_id INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS custom_commands (
                guild_id INTEGER,
                name TEXT,
                response TEXT,
                creator_id INTEGER,
                uses INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, name)
            )""",
            """CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                name TEXT,
                description TEXT,
                price INTEGER,
                role_id INTEGER,
                stock INTEGER DEFAULT -1
            )"""
        ]
        for query in queries:
            await self.conn.execute(query)
        await self.conn.commit()

    # Guild Config
    async def get_guild_config(self, guild_id: int) -> dict:
        async with self.conn.execute(
            "SELECT config FROM guilds WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                config = DEFAULT_CONFIG.copy()
                saved = json.loads(row[0])
                self._deep_update(config, saved)
                return config
            return DEFAULT_CONFIG.copy()

    async def set_guild_config(self, guild_id: int, config: dict):
        await self.conn.execute(
            """INSERT INTO guilds (guild_id, config) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET config = ?""",
            (guild_id, json.dumps(config), json.dumps(config))
        )
        await self.conn.commit()

    def _deep_update(self, base: dict, update: dict):
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    # User Data
    async def get_user(self, user_id: int, guild_id: int) -> dict:
        async with self.conn.execute(
            "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "user_id": row[0], "guild_id": row[1], "xp": row[2],
                    "level": row[3], "messages": row[4], "balance": row[5],
                    "bank": row[6], "daily_timestamp": row[7], "work_timestamp": row[8],
                    "inventory": json.loads(row[9])
                }
            await self.conn.execute(
                "INSERT INTO users (user_id, guild_id) VALUES (?, ?)",
                (user_id, guild_id)
            )
            await self.conn.commit()
            return await self.get_user(user_id, guild_id)

    async def update_user(self, user_id: int, guild_id: int, **kwargs):
        sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [user_id, guild_id]
        await self.conn.execute(
            f"UPDATE users SET {sets} WHERE user_id = ? AND guild_id = ?",
            values
        )
        await self.conn.commit()

    # Warnings
    async def add_warning(self, user_id: int, guild_id: int, mod_id: int, reason: str):
        await self.conn.execute(
            """INSERT INTO warnings (user_id, guild_id, moderator_id, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)""",
            (user_id, guild_id, mod_id, reason, int(datetime.datetime.now().timestamp()))
        )
        await self.conn.commit()

    async def get_warnings(self, user_id: int, guild_id: int) -> list:
        async with self.conn.execute(
            "SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY timestamp DESC",
            (user_id, guild_id)
        ) as cursor:
            return await cursor.fetchall()

    async def clear_warnings(self, user_id: int, guild_id: int):
        await self.conn.execute(
            "DELETE FROM warnings WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        await self.conn.commit()

    # Tickets
    async def create_ticket(self, channel_id: int, guild_id: int, user_id: int, category: str) -> int:
        cursor = await self.conn.execute(
            """INSERT INTO tickets (channel_id, guild_id, user_id, category, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (channel_id, guild_id, user_id, category, int(datetime.datetime.now().timestamp()))
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def close_ticket(self, channel_id: int):
        await self.conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?",
            (int(datetime.datetime.now().timestamp()), channel_id)
        )
        await self.conn.commit()

    async def get_ticket(self, channel_id: int):
        async with self.conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        ) as cursor:
            return await cursor.fetchone()

    # Giveaways
    async def create_giveaway(self, message_id: int, channel_id: int, guild_id: int,
                              prize: str, winners: int, end_time: int, host_id: int):
        await self.conn.execute(
            """INSERT INTO giveaways (message_id, channel_id, guild_id, prize, winners, end_time, host_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (message_id, channel_id, guild_id, prize, winners, end_time, host_id)
        )
        await self.conn.commit()

    async def get_active_giveaways(self):
        async with self.conn.execute(
            "SELECT * FROM giveaways WHERE ended = 0"
        ) as cursor:
            return await cursor.fetchall()

    async def end_giveaway(self, message_id: int):
        await self.conn.execute(
            "UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,)
        )
        await self.conn.commit()

    # Custom Commands
    async def add_custom_command(self, guild_id: int, name: str, response: str, creator_id: int):
        await self.conn.execute(
            """INSERT INTO custom_commands (guild_id, name, response, creator_id)
            VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, name) DO UPDATE SET response = ?""",
            (guild_id, name.lower(), response, creator_id, response)
        )
        await self.conn.commit()

    async def get_custom_command(self, guild_id: int, name: str):
        async with self.conn.execute(
            "SELECT * FROM custom_commands WHERE guild_id = ? AND name = ?",
            (guild_id, name.lower())
        ) as cursor:
            return await cursor.fetchone()

    async def get_all_custom_commands(self, guild_id: int):
        async with self.conn.execute(
            "SELECT * FROM custom_commands WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            return await cursor.fetchall()

    async def delete_custom_command(self, guild_id: int, name: str):
        await self.conn.execute(
            "DELETE FROM custom_commands WHERE guild_id = ? AND name = ?",
            (guild_id, name.lower())
        )
        await self.conn.commit()

    # Shop
    async def add_shop_item(self, guild_id: int, name: str, description: str,
                            price: int, role_id: int = None, stock: int = -1):
        await self.conn.execute(
            """INSERT INTO shop_items (guild_id, name, description, price, role_id, stock)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (guild_id, name, description, price, role_id, stock)
        )
        await self.conn.commit()

    async def get_shop_items(self, guild_id: int):
        async with self.conn.execute(
            "SELECT * FROM shop_items WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            return await cursor.fetchall()

    async def get_shop_item(self, item_id: int):
        async with self.conn.execute(
            "SELECT * FROM shop_items WHERE id = ?", (item_id,)
        ) as cursor:
            return await cursor.fetchone()

    # Leaderboard
    async def get_leaderboard(self, guild_id: int, category: str = "xp", limit: int = 10):
        column = "xp" if category == "xp" else "balance + bank"
        async with self.conn.execute(
            f"SELECT user_id, {column} as total FROM users WHERE guild_id = ? ORDER BY total DESC LIMIT ?",
            (guild_id, limit)
        ) as cursor:
            return await cursor.fetchall()


# ═══════════════════════════════════════════════════════════════════════════════
# BOT PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class UltraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=self.get_prefix, intents=intents)
        self.db = Database()
        self.xp_cooldowns = defaultdict(dict)
        self.spam_tracker = defaultdict(list)

    async def get_prefix(self, message: discord.Message):
        if not message.guild:
            return "!"
        config = await self.db.get_guild_config(message.guild.id)
        return commands.when_mentioned_or(config["prefix"])(self, message)

    async def setup_hook(self):
        await self.db.connect()
        self.check_giveaways.start()
        await self.tree.sync()
        print(f"✅ Commandes synchronisées!")

    async def on_ready(self):
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    🤖 ULTRABOT v2.0                          ║
╠══════════════════════════════════════════════════════════════╣
║  Bot connecté: {self.user.name:<43} ║
║  ID: {self.user.id:<53} ║
║  Serveurs: {len(self.guilds):<48} ║
║  Utilisateurs: {sum(g.member_count for g in self.guilds):<44} ║
╚══════════════════════════════════════════════════════════════╝
        """)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} serveurs | /help"
            )
        )
        print(f"✅ Bot prêt et commandes slash synchronisées !")

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        """Vérifie et termine les giveaways expirés"""
        giveaways = await self.db.get_active_giveaways()
        now = int(datetime.datetime.now().timestamp())

        for giveaway in giveaways:
            if giveaway[6] <= now:  # end_time
                try:
                    channel = self.get_channel(giveaway[2])
                    if channel:
                        message = await channel.fetch_message(giveaway[1])
                        reaction = discord.utils.get(message.reactions, emoji="🎉")

                        if reaction:
                            users = [u async for u in reaction.users() if not u.bot]
                            winners_count = min(giveaway[5], len(users))

                            if winners_count > 0:
                                winners = random.sample(users, winners_count)
                                winners_text = ", ".join(w.mention for w in winners)

                                embed = discord.Embed(
                                    title="🎉 GIVEAWAY TERMINÉ 🎉",
                                    description=f"**Prix:** {giveaway[4]}\n**Gagnant(s):** {winners_text}",
                                    color=discord.Color.gold()
                                )
                                await message.edit(embed=embed)
                                await channel.send(f"🎊 Félicitations {winners_text} ! Vous avez gagné **{giveaway[4]}** !")
                            else:
                                embed = discord.Embed(
                                    title="🎉 GIVEAWAY TERMINÉ 🎉",
                                    description=f"**Prix:** {giveaway[4]}\n**Aucun participant** 😢",
                                    color=discord.Color.red()
                                )
                                await message.edit(embed=embed)

                    await self.db.end_giveaway(giveaway[1])
                except Exception as e:
                    print(f"Erreur giveaway: {e}")
                    await self.db.end_giveaway(giveaway[1])


bot = UltraBot()

# 1. On crée la commande /help
@bot.tree.command(name="aide", description="Affiche la liste des commandes")
async def aide(interaction: discord.Interaction):
    # On prépare le message
    embed = discord.Embed(title="Aide", description="Choisis une catégorie", color=0x00ff00)
    # On envoie le message avec le menu déroulant que TU as déjà créé
    await interaction.response.send_message(embed=embed, view=HelpView(), ephemeral=True)

# 2. On crée la commande /ping
@bot.tree.command(name="ping", description="Teste la latence")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong ! {round(bot.latency * 1000)}ms")


# ═══════════════════════════════════════════════════════════════════════════════
# VUES ET MENUS INTERACTIFS
# ═══════════════════════════════════════════════════════════════════════════════

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories: list):
        options = [
            discord.SelectOption(
                label=cat["name"],
                emoji=cat["emoji"],
                description=cat["description"],
                value=cat["name"]
            ) for cat in categories
        ]
        super().__init__(
            placeholder="📝 Select a category...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        config = await bot.db.get_guild_config(interaction.guild.id)
        category_name = self.values[0]

        # Vérifier si l'utilisateur a déjà un ticket ouvert
        existing = await bot.db.conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? AND guild_id = ? AND status = 'open'",
            (interaction.user.id, interaction.guild.id)
        )
        if await existing.fetchone():
            return await interaction.response.send_message(
                "❌ Vous avez déjà un ticket ouvert!", ephemeral=True
            )

        # Créer le salon du ticket
        category = None
        if config["tickets"]["category_id"]:
            category = interaction.guild.get_channel(config["tickets"]["category_id"])

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            )
        }

        if config["tickets"]["support_role"]:
            support_role = interaction.guild.get_role(config["tickets"]["support_role"])
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket de {interaction.user.name} | Catégorie: {category_name}"
        )

        ticket_id = await bot.db.create_ticket(
            ticket_channel.id, interaction.guild.id, interaction.user.id, category_name
        )

        # Embed de bienvenue dans le ticket
        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_id}",
            description=f"""
Bienvenue {interaction.user.mention} !
Welcome {interaction.user.mention}!

**Catégorie:** {category_name}
**Category:** {category_name}
**Créé le:** {discord.utils.format_dt(datetime.datetime.now())}
**Creation date:** {discord.utils.format_dt(datetime.datetime.now())}

Décrivez votre problème et un membre du staff vous répondra rapidement.
Explain your problem and a staff member will respond fast.
            """,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Use the buttons below to manage the ticket.\nUtilisez les boutons ci-dessous pour gérer le ticket.")

        view = TicketControlView()
        await ticket_channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Votre ticket a été créé: {ticket_channel.mention}",
            ephemeral=True
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, categories: list):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(categories))


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fermer", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("Ce n'est pas un ticket!", ephemeral=True)

        embed = discord.Embed(
            title="⚠️ Confirmation",
            description="Êtes-vous sûr de vouloir fermer ce ticket?",
            color=discord.Color.orange()
        )
        view = TicketCloseConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Claim", emoji="✋", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description=f"🎫 Ce ticket est maintenant pris en charge par {interaction.user.mention}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Transcript", emoji="📜", style=discord.ButtonStyle.secondary, custom_id="transcript_ticket")
    async def transcript_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        # 1. Récupérer la config pour trouver le salon de logs
        config = await bot.db.get_guild_config(interaction.guild.id)
        log_channel_id = config["tickets"].get("log_channel")
        log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None

        # 2. Générer le texte du transcript
        messages = []
        async for msg in interaction.channel.history(limit=1000, oldest_first=True):
            timestamp = msg.created_at.strftime("%d/%m/%Y %H:%M")
            content = msg.content if msg.content else "[Fichier/Embed]"
            messages.append(f"[{timestamp}] {msg.author}: {content}")
        
        transcript_text = "\n".join(messages)

        # 3. Créer le fichier en mémoire
        import io
        buffer = io.BytesIO(transcript_text.encode('utf-8'))
        file = discord.File(fp=buffer, filename=f"transcript-{interaction.channel.name}.txt")

        # 4. Envoyer dans le salon de logs si configuré
        if log_channel:
            embed_log = discord.Embed(
                title="📜 Nouveau Transcript",
                description=f"Ticket: **{interaction.channel.name}**\nFermé par: {interaction.user.mention}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            await log_channel.send(embed=embed_log, file=file)
            await interaction.followup.send(f"✅ Transcript envoyé dans {log_channel.mention}", ephemeral=True)
        else:
            # Si pas de salon de log, on l'envoie juste ici en privé
            await interaction.followup.send(
                content="⚠️ Aucun salon de logs configuré. Voici le transcript ici :",
                file=file,
                ephemeral=True
            )


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirmer", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await bot.db.close_ticket(interaction.channel.id)

        embed = discord.Embed(
            title="🔒 Ticket Fermé",
            description=f"Ce ticket sera supprimé dans 5 secondes...",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Annuler", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Action annulée.", ephemeral=True)


class ShopView(discord.ui.View):
    def __init__(self, items: list, user_balance: int):
        super().__init__(timeout=120)
        self.items = items

        options = []
        for item in items[:25]:  # Max 25 options
            stock_text = f" (Stock: {item[6]})" if item[6] > 0 else " (Illimité)" if item[6] == -1 else " (Rupture)"
            options.append(discord.SelectOption(
                label=item[2][:50],
                description=f"{item[4]} coins{stock_text}"[:100],
                value=str(item[0])
            ))

        if options:
            select = discord.ui.Select(
                placeholder="🛒 Sélectionnez un article...",
                options=options
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        item_id = int(interaction.data["values"][0])
        item = await bot.db.get_shop_item(item_id)

        if not item:
            return await interaction.response.send_message("Article introuvable!", ephemeral=True)

        user = await bot.db.get_user(interaction.user.id, interaction.guild.id)

        if user["balance"] < item[4]:
            return await interaction.response.send_message(
                f"❌ Vous n'avez pas assez de coins! (Vous avez: {user['balance']})",
                ephemeral=True
            )

        if item[6] == 0:
            return await interaction.response.send_message("❌ Article en rupture de stock!", ephemeral=True)

        # Effectuer l'achat
        await bot.db.update_user(interaction.user.id, interaction.guild.id, balance=user["balance"] - item[4])

        # Donner le rôle si c'est un article de rôle
        if item[5]:
            role = interaction.guild.get_role(item[5])
            if role:
                await interaction.user.add_roles(role)

        # Mettre à jour le stock
        if item[6] > 0:
            await bot.db.conn.execute(
                "UPDATE shop_items SET stock = stock - 1 WHERE id = ?", (item_id,)
            )
            await bot.db.conn.commit()

        embed = discord.Embed(
            title="✅ Achat effectué!",
            description=f"Vous avez acheté **{item[2]}** pour **{item[4]}** coins!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PollView(discord.ui.View):
    def __init__(self, options: list, poll_id: str):
        super().__init__(timeout=None)
        self.votes = {opt: set() for opt in options}
        self.poll_id = poll_id

        for i, option in enumerate(options[:5]):
            button = discord.ui.Button(
                label=option,
                style=discord.ButtonStyle.primary,
                custom_id=f"poll_{poll_id}_{i}"
            )
            button.callback = self.make_callback(option)
            self.add_item(button)

    def make_callback(self, option: str):
        async def callback(interaction: discord.Interaction):
            user_id = interaction.user.id

            # Retirer le vote précédent
            for opt, voters in self.votes.items():
                voters.discard(user_id)

            # Ajouter le nouveau vote
            self.votes[option].add(user_id)

            # Mettre à jour l'embed
            embed = interaction.message.embeds[0]
            results = []
            total_votes = sum(len(v) for v in self.votes.values())

            for opt, voters in self.votes.items():
                count = len(voters)
                percentage = (count / total_votes * 100) if total_votes > 0 else 0
                bar = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))
                results.append(f"**{opt}**\n{bar} {count} votes ({percentage:.1f}%)")

            embed.description = "\n\n".join(results)
            embed.set_footer(text=f"Total: {total_votes} votes")

            await interaction.response.edit_message(embed=embed)

        return callback


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        placeholder="📚 Sélectionnez une catégorie...",
        options=[
            discord.SelectOption(label="Modération", emoji="🛡️", value="moderation"),
            discord.SelectOption(label="Économie", emoji="💰", value="economy"),
            discord.SelectOption(label="Niveaux", emoji="📊", value="leveling"),
            discord.SelectOption(label="Tickets", emoji="🎫", value="tickets"),
            discord.SelectOption(label="Utilitaires", emoji="🔧", value="utility"),
            discord.SelectOption(label="Fun", emoji="🎮", value="fun"),
            discord.SelectOption(label="Configuration", emoji="⚙️", value="config")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        category = select.values[0]

        embeds = {
            "moderation": discord.Embed(
                title="🛡️ Commandes de Modération",
                description="""
`/ban` - Bannir un membre
`/kick` - Expulser un membre
`/mute` - Rendre muet un membre
`/unmute` - Rendre la parole à un membre
`/warn` - Avertir un membre
`/warnings` - Voir les avertissements
`/clear` - Supprimer des messages
`/slowmode` - Définir le slowmode
`/lock` - Verrouiller un salon
`/unlock` - Déverrouiller un salon
                """,
                color=discord.Color.red()
            ),
            "economy": discord.Embed(
                title="💰 Commandes d'Économie",
                description="""
`/balance` - Voir votre solde
`/daily` - Récompense quotidienne
`/work` - Travailler pour gagner des coins
`/pay` - Payer quelqu'un
`/deposit` - Déposer en banque
`/withdraw` - Retirer de la banque
`/shop` - Voir la boutique
`/buy` - Acheter un article
`/inventory` - Voir votre inventaire
`/leaderboard economy` - Classement économie
                """,
                color=discord.Color.gold()
            ),
            "leveling": discord.Embed(
                title="📊 Commandes de Niveaux",
                description="""
`/rank` - Voir votre niveau
`/leaderboard xp` - Classement XP
`/setxp` - Définir l'XP (admin)
`/setlevel` - Définir le niveau (admin)
                """,
                color=discord.Color.blue()
            ),
            "tickets": discord.Embed(
                title="🎫 Commandes de Tickets",
                description="""
`/ticket setup` - Créer un panel de tickets
`/ticket close` - Fermer un ticket
`/ticket add` - Ajouter quelqu'un au ticket
`/ticket remove` - Retirer quelqu'un du ticket
                """,
                color=discord.Color.purple()
            ),
            "utility": discord.Embed(
                title="🔧 Commandes Utilitaires",
                description="""
`/userinfo` - Infos sur un membre
`/serverinfo` - Infos sur le serveur
`/avatar` - Voir l'avatar d'un membre
`/poll` - Créer un sondage
`/giveaway` - Lancer un giveaway
`/remind` - Créer un rappel
                """,
                color=discord.Color.teal()
            ),
            "fun": discord.Embed(
                title="🎮 Commandes Fun",
                description="""
`/8ball` - Poser une question au 8ball
`/coinflip` - Pile ou face
`/roll` - Lancer un dé
`/rps` - Pierre papier ciseaux
`/joke` - Une blague aléatoire
                """,
                color=discord.Color.magenta()
            ),
            "config": discord.Embed(
                title="⚙️ Configuration",
                description="""
`/config prefix` - Changer le préfixe
`/config welcome` - Configurer les bienvenues
`/config goodbye` - Configurer les au revoirs
`/config leveling` - Configurer les niveaux
`/config logs` - Configurer les logs
`/config automod` - Configurer l'auto-modération
`/customcmd add` - Ajouter une commande custom
`/customcmd delete` - Supprimer une commande custom
`/customcmd list` - Lister les commandes custom
                """,
                color=discord.Color.dark_gray()
            )
        }

        embed = embeds.get(category)
        embed.set_footer(text="UltraBot v2.0 | Utilisez les commandes slash (/)")
        await interaction.response.edit_message(embed=embed)


class ConfirmView(discord.ui.View):
    def __init__(self, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.value = None

    @discord.ui.button(label="Confirmer", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # On récupère les données
        ticket_data = await bot.db.get_ticket(interaction.channel.id)
        config = await bot.db.get_guild_config(interaction.guild.id)
        
        # ÉTAPE A : Retirer l'utilisateur (Il ne verra plus le salon)
        if ticket_data:
            user_id = ticket_data[3]
            member = interaction.guild.get_member(user_id)
            if member:
                # On supprime sa permission spécifique -> Le salon disparaît de sa liste
                await interaction.channel.set_permissions(member, overwrite=None)

        # ÉTAPE B : Configurer pour le Staff uniquement
        support_role_id = config["tickets"].get("support_role")
        support_role = interaction.guild.get_role(support_role_id) if support_role_id else None

        # On crée les nouvelles permissions
        new_overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
        if support_role:
            # Le staff voit le ticket mais ne peut plus écrire dedans (Lecture seule)
            new_overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)

        # ÉTAPE C : Déplacer et renommer
        archive_cat_id = config["tickets"].get("archive_category_id")
        archive_cat = interaction.guild.get_channel(archive_cat_id)

        await interaction.channel.edit(
            name=f"🔒-{interaction.channel.name}",
            category=archive_cat,
            overwrites=new_overwrites
        )

        await bot.db.close_ticket(interaction.channel.id)
        await interaction.followup.send("✅ Ticket archivé : l'utilisateur a été retiré.", ephemeral=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_member_join(member: discord.Member):
    config = await bot.db.get_guild_config(member.guild.id)

    # Auto-role
    if config["welcome"]["auto_role"]:
        role = member.guild.get_role(config["welcome"]["auto_role"])
        if role:
            try:
                await member.add_roles(role)
            except:
                pass

    # Message de bienvenue
    if config["welcome"]["enabled"] and config["welcome"]["channel_id"]:
        channel = member.guild.get_channel(config["welcome"]["channel_id"])
        if channel:
            message = config["welcome"]["message"].format(
                user=member.mention,
                username=member.name,
                server=member.guild.name,
                count=member.guild.member_count
            )

            embed = discord.Embed(
                title="👋 Nouveau membre!",
                description=message,
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"ID: {member.id}")

            await channel.send(embed=embed)

    # DM de bienvenue
    if config["welcome"]["dm_enabled"]:
        try:
            message = config["welcome"]["dm_message"].format(
                user=member.name,
                server=member.guild.name
            )
            await member.send(message)
        except:
            pass


@bot.event
async def on_member_remove(member: discord.Member):
    config = await bot.db.get_guild_config(member.guild.id)

    if config["goodbye"]["enabled"] and config["goodbye"]["channel_id"]:
        channel = member.guild.get_channel(config["goodbye"]["channel_id"])
        if channel:
            message = config["goodbye"]["message"].format(
                user=member.name,
                server=member.guild.name,
                count=member.guild.member_count
            )

            embed = discord.Embed(
                title="👋 Au revoir...",
                description=message,
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=member.display_avatar.url)

            await channel.send(embed=embed)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    config = await bot.db.get_guild_config(message.guild.id)

    # Auto-modération
    if config["moderation"]["auto_mod"]["enabled"]:
        should_delete = False
        reason = ""

        # Anti-spam
        if config["moderation"]["auto_mod"]["anti_spam"]:
            now = datetime.datetime.now().timestamp()
            user_messages = bot.spam_tracker[message.author.id]
            user_messages.append(now)
            user_messages = [t for t in user_messages if now - t < 5]
            bot.spam_tracker[message.author.id] = user_messages

            if len(user_messages) >= 5:
                should_delete = True
                reason = "Spam détecté"

        # Anti-liens
        if config["moderation"]["auto_mod"]["anti_links"]:
            if re.search(r'https?://\S+', message.content):
                if not message.author.guild_permissions.manage_messages:
                    should_delete = True
                    reason = "Liens non autorisés"

        # Anti-majuscules
        if config["moderation"]["auto_mod"]["anti_caps"]:
            if len(message.content) > 10:
                caps_ratio = sum(1 for c in message.content if c.isupper()) / len(message.content) * 100
                if caps_ratio > config["moderation"]["auto_mod"]["caps_threshold"]:
                    should_delete = True
                    reason = "Trop de majuscules"

        # Anti-mentions
        if len(message.mentions) > config["moderation"]["auto_mod"]["max_mentions"]:
            should_delete = True
            reason = "Trop de mentions"

        # Mots interdits
        for word in config["moderation"]["auto_mod"]["banned_words"]:
            if word.lower() in message.content.lower():
                should_delete = True
                reason = "Mot interdit détecté"
                break

        if should_delete:
            await message.delete()
            await message.channel.send(
                f"⚠️ {message.author.mention} - {reason}",
                delete_after=5
            )
            return

    # Système de niveaux
    if config["leveling"]["enabled"]:
        user_id = message.author.id
        now = datetime.datetime.now().timestamp()
        last_xp = bot.xp_cooldowns[message.guild.id].get(user_id, 0)

        if now - last_xp >= config["leveling"]["xp_cooldown"]:
            bot.xp_cooldowns[message.guild.id][user_id] = now

            user_data = await bot.db.get_user(user_id, message.guild.id)
            xp_gain = random.randint(config["leveling"]["xp_min"], config["leveling"]["xp_max"])
            new_xp = user_data["xp"] + xp_gain
            new_messages = user_data["messages"] + 1

            # Calcul du niveau (formule: niveau = sqrt(xp/100))
            new_level = int((new_xp / 100) ** 0.5)

            await bot.db.update_user(user_id, message.guild.id, xp=new_xp, messages=new_messages, level=new_level)

            # Level up!
            if new_level > user_data["level"]:
                # Récompenses de rôle
                role_rewards = config["leveling"]["role_rewards"]
                if str(new_level) in role_rewards:
                    role = message.guild.get_role(role_rewards[str(new_level)])
                    if role:
                        try:
                            await message.author.add_roles(role)
                        except:
                            pass

                # Message de level up
                level_up_msg = config["leveling"]["level_up_message"].format(
                    user=message.author.mention,
                    level=new_level
                )

                channel = message.channel
                if config["leveling"]["level_up_channel"]:
                    ch = message.guild.get_channel(config["leveling"]["level_up_channel"])
                    if ch:
                        channel = ch

                embed = discord.Embed(
                    title="🎉 Level Up!",
                    description=level_up_msg,
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=message.author.display_avatar.url)
                await channel.send(embed=embed)

    # Commandes personnalisées
    prefix = config["prefix"]
    if message.content.startswith(prefix):
        cmd_name = message.content[len(prefix):].split()[0].lower()
        custom_cmd = await bot.db.get_custom_command(message.guild.id, cmd_name)
        if custom_cmd:
            response = custom_cmd[2].format(
                user=message.author.mention,
                username=message.author.name,
                server=message.guild.name
            )
            await message.channel.send(response)

    await bot.process_commands(message)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES SLASH - MODÉRATION
# ═══════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="ban", description="Bannir un membre du serveur")
@app_commands.describe(member="Le membre à bannir", reason="Raison du bannissement", delete_days="Jours de messages à supprimer")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison", delete_days: int = 0):
    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("❌ Vous ne pouvez pas bannir ce membre!", ephemeral=True)

    await member.ban(reason=f"{reason} (par {interaction.user})", delete_message_days=min(delete_days, 7))

    embed = discord.Embed(
        title="🔨 Membre banni",
        description=f"**Membre:** {member.mention}\n**Raison:** {reason}\n**Par:** {interaction.user.mention}",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="kick", description="Expulser un membre du serveur")
@app_commands.describe(member="Le membre à expulser", reason="Raison de l'expulsion")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("❌ Vous ne pouvez pas expulser ce membre!", ephemeral=True)

    await member.kick(reason=f"{reason} (par {interaction.user})")

    embed = discord.Embed(
        title="👢 Membre expulsé",
        description=f"**Membre:** {member.mention}\n**Raison:** {reason}\n**Par:** {interaction.user.mention}",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="mute", description="Rendre muet un membre")
@app_commands.describe(member="Le membre à rendre muet", duration="Durée (ex: 1h, 30m, 1d)", reason="Raison")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Aucune raison"):
    # Parser la durée
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = re.match(r"(\d+)([smhd])", duration.lower())
    if not match:
        return await interaction.response.send_message("❌ Format de durée invalide! Ex: 30m, 1h, 1d", ephemeral=True)

    amount = int(match.group(1))
    unit = match.group(2)
    seconds = amount * time_units[unit]

    if seconds > 2419200:  # 28 jours max
        return await interaction.response.send_message("❌ Durée maximum: 28 jours!", ephemeral=True)

    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    await member.timeout(until, reason=f"{reason} (par {interaction.user})")

    embed = discord.Embed(
        title="🔇 Membre rendu muet",
        description=f"**Membre:** {member.mention}\n**Durée:** {duration}\n**Raison:** {reason}\n**Par:** {interaction.user.mention}",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="unmute", description="Rendre la parole à un membre")
@app_commands.describe(member="Le membre à unmute")
@app_commands.default_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)

    embed = discord.Embed(
        title="🔊 Membre unmute",
        description=f"{member.mention} peut à nouveau parler!",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="warn", description="Avertir un membre")
@app_commands.describe(member="Le membre à avertir", reason="Raison de l'avertissement")
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
    await bot.db.add_warning(member.id, interaction.guild.id, interaction.user.id, reason)
    warnings = await bot.db.get_warnings(member.id, interaction.guild.id)

    embed = discord.Embed(
        title="⚠️ Avertissement",
        description=f"**Membre:** {member.mention}\n**Raison:** {reason}\n**Par:** {interaction.user.mention}\n\n**Total d'avertissements:** {len(warnings)}",
        color=discord.Color.yellow()
    )
    await interaction.response.send_message(embed=embed)

    # Avertir le membre en DM
    try:
        dm_embed = discord.Embed(
            title=f"⚠️ Avertissement sur {interaction.guild.name}",
            description=f"**Raison:** {reason}\n**Total:** {len(warnings)} avertissement(s)",
            color=discord.Color.yellow()
        )
        await member.send(embed=dm_embed)
    except:
        pass


@bot.tree.command(name="warnings", description="Voir les avertissements d'un membre")
@app_commands.describe(member="Le membre dont voir les avertissements")
async def warnings(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    warns = await bot.db.get_warnings(member.id, interaction.guild.id)

    if not warns:
        return await interaction.response.send_message(f"✅ {member.mention} n'a aucun avertissement!", ephemeral=True)

    embed = discord.Embed(
        title=f"⚠️ Avertissements de {member.name}",
        color=discord.Color.yellow()
    )

    for i, warn in enumerate(warns[:10], 1):
        mod = interaction.guild.get_member(warn[3])
        mod_name = mod.name if mod else "Inconnu"
        timestamp = datetime.datetime.fromtimestamp(warn[5])
        embed.add_field(
            name=f"#{i} - {timestamp.strftime('%d/%m/%Y')}",
            value=f"**Raison:** {warn[4]}\n**Par:** {mod_name}",
            inline=False
        )

    embed.set_footer(text=f"Total: {len(warns)} avertissement(s)")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clearwarns", description="Effacer les avertissements d'un membre")
@app_commands.describe(member="Le membre dont effacer les avertissements")
@app_commands.default_permissions(moderate_members=True)
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    await bot.db.clear_warnings(member.id, interaction.guild.id)

    embed = discord.Embed(
        title="✅ Avertissements effacés",
        description=f"Tous les avertissements de {member.mention} ont été supprimés.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clear", description="Supprimer des messages")
@app_commands.describe(amount="Nombre de messages à supprimer", member="Supprimer uniquement les messages de ce membre")
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int, member: discord.Member = None):
    if amount > 100:
        return await interaction.response.send_message("❌ Maximum 100 messages!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    def check(msg):
        if member:
            return msg.author == member
        return True

    deleted = await interaction.channel.purge(limit=amount, check=check)

    await interaction.followup.send(f"✅ {len(deleted)} message(s) supprimé(s)!", ephemeral=True)


@bot.tree.command(name="slowmode", description="Définir le slowmode d'un salon")
@app_commands.describe(seconds="Délai en secondes (0 pour désactiver)")
@app_commands.default_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    if seconds > 21600:
        return await interaction.response.send_message("❌ Maximum 6 heures (21600 secondes)!", ephemeral=True)

    await interaction.channel.edit(slowmode_delay=seconds)

    if seconds == 0:
        await interaction.response.send_message("✅ Slowmode désactivé!")
    else:
        await interaction.response.send_message(f"✅ Slowmode défini à {seconds} seconde(s)!")


@bot.tree.command(name="lock", description="Verrouiller un salon")
@app_commands.describe(channel="Le salon à verrouiller")
@app_commands.default_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False)

    embed = discord.Embed(
        title="🔒 Salon verrouillé",
        description=f"{channel.mention} a été verrouillé par {interaction.user.mention}",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="unlock", description="Déverrouiller un salon")
@app_commands.describe(channel="Le salon à déverrouiller")
@app_commands.default_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=None)

    embed = discord.Embed(
        title="🔓 Salon déverrouillé",
        description=f"{channel.mention} a été déverrouillé par {interaction.user.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES SLASH - ÉCONOMIE
# ═══════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="balance", description="Voir votre solde")
@app_commands.describe(member="Le membre dont voir le solde")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user = await bot.db.get_user(member.id, interaction.guild.id)
    config = await bot.db.get_guild_config(interaction.guild.id)

    symbol = config["economy"]["currency_symbol"]
    name = config["economy"]["currency_name"]

    embed = discord.Embed(
        title=f"💰 Solde de {member.name}",
        color=discord.Color.gold()
    )
    embed.add_field(name="Portefeuille", value=f"{symbol} {user['balance']:,} {name}")
    embed.add_field(name="Banque", value=f"{symbol} {user['bank']:,} {name}")
    embed.add_field(name="Total", value=f"{symbol} {user['balance'] + user['bank']:,} {name}")
    embed.set_thumbnail(url=member.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="daily", description="Réclamer votre récompense quotidienne")
async def daily(interaction: discord.Interaction):
    user = await bot.db.get_user(interaction.user.id, interaction.guild.id)
    config = await bot.db.get_guild_config(interaction.guild.id)

    now = int(datetime.datetime.now().timestamp())
    last_daily = user["daily_timestamp"]

    if now - last_daily < 86400:
        remaining = 86400 - (now - last_daily)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        return await interaction.response.send_message(
            f"⏰ Revenez dans **{hours}h {minutes}m** pour votre récompense quotidienne!",
            ephemeral=True
        )

    amount = config["economy"]["daily_amount"]
    await bot.db.update_user(
        interaction.user.id, interaction.guild.id,
        balance=user["balance"] + amount,
        daily_timestamp=now
    )

    embed = discord.Embed(
        title="🎁 Récompense quotidienne!",
        description=f"Vous avez reçu **{config['economy']['currency_symbol']} {amount}** {config['economy']['currency_name']}!",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="work", description="Travailler pour gagner de l'argent")
async def work(interaction: discord.Interaction):
    user = await bot.db.get_user(interaction.user.id, interaction.guild.id)
    config = await bot.db.get_guild_config(interaction.guild.id)

    now = int(datetime.datetime.now().timestamp())
    last_work = user["work_timestamp"]
    cooldown = config["economy"]["work_cooldown"]

    if now - last_work < cooldown:
        remaining = cooldown - (now - last_work)
        minutes = remaining // 60
        return await interaction.response.send_message(
            f"⏰ Vous êtes fatigué! Revenez dans **{minutes}** minutes.",
            ephemeral=True
        )

    amount = random.randint(config["economy"]["work_min"], config["economy"]["work_max"])
    await bot.db.update_user(
        interaction.user.id, interaction.guild.id,
        balance=user["balance"] + amount,
        work_timestamp=now
    )

    jobs = [
        "développeur", "designer", "streamer", "livreur", "serveur",
        "mécanicien", "jardinier", "photographe", "DJ", "coach"
    ]

    embed = discord.Embed(
        title="💼 Travail terminé!",
        description=f"Vous avez travaillé comme **{random.choice(jobs)}** et gagné **{config['economy']['currency_symbol']} {amount}** {config['economy']['currency_name']}!",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pay", description="Payer quelqu'un")
@app_commands.describe(member="Le membre à payer", amount="Montant à payer")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: int):
    if member.bot or member == interaction.user:
        return await interaction.response.send_message("❌ Transaction invalide!", ephemeral=True)

    if amount <= 0:
        return await interaction.response.send_message("❌ Montant invalide!", ephemeral=True)

    user = await bot.db.get_user(interaction.user.id, interaction.guild.id)

    if user["balance"] < amount:
        return await interaction.response.send_message("❌ Fonds insuffisants!", ephemeral=True)

    target = await bot.db.get_user(member.id, interaction.guild.id)

    await bot.db.update_user(interaction.user.id, interaction.guild.id, balance=user["balance"] - amount)
    await bot.db.update_user(member.id, interaction.guild.id, balance=target["balance"] + amount)

    config = await bot.db.get_guild_config(interaction.guild.id)
    symbol = config["economy"]["currency_symbol"]

    embed = discord.Embed(
        title="💸 Transfert effectué!",
        description=f"{interaction.user.mention} a envoyé **{symbol} {amount}** à {member.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="addcash", description="Ajouter de l'argent à un membre (Admin)")
@app_commands.describe(member="Le membre", amount="Montant")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction: discord.Interaction, member: discord.Member, amount: int):
    user_data = await bot.db.get_user(member.id, interaction.guild.id)
    new_balance = user_data["balance"] + amount
    await bot.db.update_user(member.id, interaction.guild.id, balance=new_balance)
    await interaction.response.send_message(f"✅ Ajout de **{amount}** coins à {member.mention}.")

@bot.tree.command(name="removecash", description="Retirer de l'argent à un membre (Admin)")
@app_commands.describe(member="Le membre", amount="Montant")
@app_commands.default_permissions(administrator=True)
async def removecash(interaction: discord.Interaction, member: discord.Member, amount: int):
    user_data = await bot.db.get_user(member.id, interaction.guild.id)
    new_balance = max(0, user_data["balance"] - amount)
    await bot.db.update_user(member.id, interaction.guild.id, balance=new_balance)
    await interaction.response.send_message(f"✅ Retrait de **{amount}** coins à {member.mention}.")


@bot.tree.command(name="deposit", description="Déposer de l'argent en banque")
@app_commands.describe(amount="Montant à déposer (ou 'all' pour tout)")
async def deposit(interaction: discord.Interaction, amount: str):
    user = await bot.db.get_user(interaction.user.id, interaction.guild.id)

    if amount.lower() == "all":
        amount = user["balance"]
    else:
        try:
            amount = int(amount)
        except:
            return await interaction.response.send_message("❌ Montant invalide!", ephemeral=True)

    if amount <= 0 or amount > user["balance"]:
        return await interaction.response.send_message("❌ Montant invalide ou fonds insuffisants!", ephemeral=True)

    await bot.db.update_user(
        interaction.user.id, interaction.guild.id,
        balance=user["balance"] - amount,
        bank=user["bank"] + amount
    )

    config = await bot.db.get_guild_config(interaction.guild.id)
    embed = discord.Embed(
        title="🏦 Dépôt effectué!",
        description=f"Vous avez déposé **{config['economy']['currency_symbol']} {amount}** en banque.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="withdraw", description="Retirer de l'argent de la banque")
@app_commands.describe(amount="Montant à retirer (ou 'all' pour tout)")
async def withdraw(interaction: discord.Interaction, amount: str):
    user = await bot.db.get_user(interaction.user.id, interaction.guild.id)

    if amount.lower() == "all":
        amount = user["bank"]
    else:
        try:
            amount = int(amount)
        except:
            return await interaction.response.send_message("❌ Montant invalide!", ephemeral=True)

    if amount <= 0 or amount > user["bank"]:
        return await interaction.response.send_message("❌ Montant invalide ou fonds insuffisants!", ephemeral=True)

    await bot.db.update_user(
        interaction.user.id, interaction.guild.id,
        balance=user["balance"] + amount,
        bank=user["bank"] - amount
    )

    config = await bot.db.get_guild_config(interaction.guild.id)
    embed = discord.Embed(
        title="🏦 Retrait effectué!",
        description=f"Vous avez retiré **{config['economy']['currency_symbol']} {amount}** de la banque.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="shop", description="Voir la boutique du serveur")
async def shop(interaction: discord.Interaction):
    items = await bot.db.get_shop_items(interaction.guild.id)
    user = await bot.db.get_user(interaction.user.id, interaction.guild.id)
    config = await bot.db.get_guild_config(interaction.guild.id)

    if not items:
        return await interaction.response.send_message("🏪 La boutique est vide!", ephemeral=True)

    embed = discord.Embed(
        title="🏪 Boutique du serveur",
        description=f"Votre solde: **{config['economy']['currency_symbol']} {user['balance']}**\n\nSélectionnez un article ci-dessous pour l'acheter.",
        color=discord.Color.blue()
    )

    for item in items[:10]:
        stock_text = f"Stock: {item[6]}" if item[6] > 0 else "Illimité" if item[6] == -1 else "Rupture"
        embed.add_field(
            name=f"{item[2]} - {config['economy']['currency_symbol']} {item[4]}",
            value=f"{item[3]}\n*{stock_text}*",
            inline=False
        )

    view = ShopView(items, user["balance"])
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="addshopitem", description="Ajouter un article à la boutique")
@app_commands.describe(name="Nom de l'article", description="Description", price="Prix", role="Rôle à donner (optionnel)", stock="Stock (-1 pour illimité)")
@app_commands.default_permissions(administrator=True)
async def addshopitem(interaction: discord.Interaction, name: str, description: str, price: int, role: discord.Role = None, stock: int = -1):
    await bot.db.add_shop_item(
        interaction.guild.id, name, description, price,
        role.id if role else None, stock
    )

    embed = discord.Embed(
        title="✅ Article ajouté!",
        description=f"**{name}** a été ajouté à la boutique pour **{price}** coins.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="removeshopitem", description="Supprimer un article de la boutique")
@app_commands.describe(item_id="ID de l'article à supprimer")
@app_commands.default_permissions(administrator=True)
async def removeshopitem(interaction: discord.Interaction, item_id: int):
    """Supprimer un article du shop"""
    # Récupérer l'article pour vérifier qu'il existe
    async with bot.db.conn.execute(
        "SELECT name FROM shop_items WHERE id = ? AND guild_id = ?",
        (item_id, interaction.guild.id)
    ) as cursor:
        row = await cursor.fetchone()
        
    if not row:
        return await interaction.response.send_message(
            "❌ Cet article n'existe pas dans la boutique!",
            ephemeral=True
        )
    
    item_name = row[0]
    
    # Supprimer l'article
    await bot.db.conn.execute(
        "DELETE FROM shop_items WHERE id = ? AND guild_id = ?",
        (item_id, interaction.guild.id)
    )
    await bot.db.conn.commit()
    
    embed = discord.Embed(
        title="🗑️ Article supprimé",
        description=f"L'article **{item_name}** (ID: {item_id}) a été supprimé de la boutique.",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES SLASH - NIVEAUX
# ═══════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="rank", description="Voir votre niveau et XP")
@app_commands.describe(member="Le membre dont voir le niveau")
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user = await bot.db.get_user(member.id, interaction.guild.id)

    # Calcul XP requis pour prochain niveau
    current_level = user["level"]
    next_level = current_level + 1
    xp_for_next = (next_level ** 2) * 100
    xp_for_current = (current_level ** 2) * 100
    xp_needed = xp_for_next - xp_for_current
    xp_progress = user["xp"] - xp_for_current

    # Barre de progression
    progress = int((xp_progress / xp_needed) * 20) if xp_needed > 0 else 20
    progress_bar = "█" * progress + "░" * (20 - progress)

    # Classement
    leaderboard = await bot.db.get_leaderboard(interaction.guild.id, "xp", 1000)
    rank_pos = next((i for i, (uid, _) in enumerate(leaderboard, 1) if uid == member.id), "?")

    embed = discord.Embed(
        title=f"📊 Niveau de {member.name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Niveau", value=f"**{current_level}**", inline=True)
    embed.add_field(name="XP Total", value=f"**{user['xp']:,}**", inline=True)
    embed.add_field(name="Classement", value=f"**#{rank_pos}**", inline=True)
    embed.add_field(
        name=f"Progression vers niveau {next_level}",
        value=f"{progress_bar}\n{xp_progress:,} / {xp_needed:,} XP",
        inline=False
    )
    embed.add_field(name="Messages", value=f"**{user['messages']:,}**", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="Voir le classement")
@app_commands.describe(category="Type de classement")
async def leaderboard(interaction: discord.Interaction, category: Literal["xp", "economy"] = "xp"):
    data = await bot.db.get_leaderboard(interaction.guild.id, category, 10)
    config = await bot.db.get_guild_config(interaction.guild.id)

    if not data:
        return await interaction.response.send_message("📊 Pas de données disponibles!", ephemeral=True)

    embed = discord.Embed(
        title=f"🏆 Classement {'XP' if category == 'xp' else 'Économie'}",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]
    description = []

    for i, (user_id, value) in enumerate(data, 1):
        member = interaction.guild.get_member(user_id)
        name = member.name if member else f"User#{user_id}"
        medal = medals[i-1] if i <= 3 else f"**{i}.**"

        if category == "xp":
            description.append(f"{medal} {name} - **{value:,}** XP")
        else:
            description.append(f"{medal} {name} - **{config['economy']['currency_symbol']} {value:,}**")

    embed.description = "\n".join(description)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="setxp", description="Définir l'XP d'un membre")
@app_commands.describe(member="Le membre", xp="Nouvelle valeur d'XP")
@app_commands.default_permissions(administrator=True)
async def setxp(interaction: discord.Interaction, member: discord.Member, xp: int):
    new_level = int((xp / 100) ** 0.5)
    await bot.db.update_user(member.id, interaction.guild.id, xp=xp, level=new_level)

    embed = discord.Embed(
        title="✅ XP modifié",
        description=f"**{member.mention}** a maintenant **{xp:,}** XP (niveau {new_level})",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    

@bot.tree.command(name="setlevel", description="Définir le niveau d'un membre")
@app_commands.describe(member="Le membre", level="Nouveau niveau")
@app_commands.default_permissions(administrator=True)
async def setlevel(interaction: discord.Interaction, member: discord.Member, level: int):
    xp = (level ** 2) * 100
    await bot.db.update_user(member.id, interaction.guild.id, xp=xp, level=level)

    embed = discord.Embed(
        title="✅ Niveau modifié",
        description=f"**{member.mention}** est maintenant niveau **{level}** ({xp:,} XP)",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES SLASH - TICKETS
# ═══════════════════════════════════════════════════════════════════════════════

ticket_group = app_commands.Group(name="ticket", description="Commandes de tickets")


@ticket_group.command(name="setup", description="Créer un panel de tickets")
@app_commands.describe(channel="Salon où envoyer le panel")
@app_commands.default_permissions(administrator=True)
async def ticket_setup(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    config = await bot.db.get_guild_config(interaction.guild.id)

    embed = discord.Embed(
        title="🎫 Support - Ouvrir un Ticket",
        description="""
🇬🇧 Welcome in our ticket support!

Please select a category below to open a ticket.
Our equip will answer to your ticket in short time. We are located in France, so please, don't be in a hurry if it's 3 or 4am in France.

--------------------------------------------------------------------------------

🇫🇷 Bienvenue dans notre support de tickets !

Merci de sélectionner une catégorie ci-dessous afin d'ouvrir un ticket.
Notre staff vous répondra dans les plus brefs délais. Nous sommes en France, donc, attendez-vous à ne pas avoir de réponse aux horaires inhabituels.

--------------------------------------------------------------------------------

        """,
        color=discord.Color.blue()
    )
    print(config["tickets"]["categories"])
    for cat in config["tickets"]["categories"]:
        embed.add_field(
            name=f"{cat['emoji']} {cat['name']}",
            value=cat["description"],
            inline=False
        )

    view = TicketPanelView(config["tickets"]["categories"])
    await channel.send(embed=embed, view=view)

    await interaction.response.send_message(f"✅ Panel de tickets créé dans {channel.mention}!", ephemeral=True)


@ticket_group.command(name="close", description="Fermer le ticket actuel")
async def ticket_close(interaction: discord.Interaction):
    ticket = await bot.db.get_ticket(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message("❌ Ce n'est pas un ticket!", ephemeral=True)

    embed = discord.Embed(
        title="⚠️ Confirmation",
        description="Are you sure you would like to close this ticket?\nÊtes-vous sûr de vouloir fermer ce ticket?",
        color=discord.Color.orange()
    )
    view = TicketCloseConfirmView()
    await interaction.response.send_message(embed=embed, view=view)


@ticket_group.command(name="add", description="Ajouter quelqu'un au ticket")
@app_commands.describe(member="Le membre à ajouter")
async def ticket_add(interaction: discord.Interaction, member: discord.Member):
    ticket = await bot.db.get_ticket(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message("❌ Ce n'est pas un ticket!", ephemeral=True)

    await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)

    embed = discord.Embed(
        description=f"✅ {member.mention} a été ajouté au ticket.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@ticket_group.command(name="remove", description="Retirer quelqu'un du ticket")
@app_commands.describe(member="Le membre à retirer")
async def ticket_remove(interaction: discord.Interaction, member: discord.Member):
    ticket = await bot.db.get_ticket(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message("❌ Ce n'est pas un ticket!", ephemeral=True)

    await interaction.channel.set_permissions(member, overwrite=None)

    embed = discord.Embed(
        description=f"✅ {member.mention} a été retiré du ticket.",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


bot.tree.add_command(ticket_group)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES SLASH - UTILITAIRES
# ═══════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="help", description="Afficher l'aide du bot")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 UltraBot - Aide",
        description="""
Bienvenue! Je suis **UltraBot**, un bot Discord complet et hautement configurable.

**Fonctionnalités principales:**
• 🛡️ **Modération** - Ban, kick, mute, warn, clear...
• 💰 **Économie** - Daily, work, shop, bank...
• 📊 **Niveaux** - Système d'XP et de niveaux
• 🎫 **Tickets** - Système de support avancé
• 🎉 **Giveaways** - Créez des concours
• ⚙️ **Configuration** - Personnalisez tout!

Sélectionnez une catégorie ci-dessous pour plus de détails.
        """,
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="UltraBot v2.0 | Créé avec ❤️")

    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="userinfo", description="Informations sur un membre")
@app_commands.describe(member="Le membre dont voir les infos")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user

    roles = [r.mention for r in member.roles[1:]][:10]
    roles_text = ", ".join(roles) if roles else "Aucun"

    embed = discord.Embed(
        title=f"👤 Informations sur {member.name}",
        color=member.color if member.color != discord.Color.default() else discord.Color.blue()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Surnom", value=member.nick or "Aucun", inline=True)
    embed.add_field(name="Bot", value="Oui" if member.bot else "Non", inline=True)
    embed.add_field(name="Compte créé", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
    embed.add_field(name="A rejoint", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
    embed.add_field(name="Plus haut rôle", value=member.top_role.mention, inline=True)
    embed.add_field(name=f"Rôles ({len(member.roles)-1})", value=roles_text, inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="Informations sur le serveur")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild

    embed = discord.Embed(
        title=f"🏠 {guild.name}",
        color=discord.Color.blue()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="Propriétaire", value=guild.owner.mention, inline=True)
    embed.add_field(name="Créé le", value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
    embed.add_field(name="Membres", value=f"{guild.member_count:,}", inline=True)
    embed.add_field(name="Salons", value=f"{len(guild.channels)}", inline=True)
    embed.add_field(name="Rôles", value=f"{len(guild.roles)}", inline=True)
    embed.add_field(name="Emojis", value=f"{len(guild.emojis)}", inline=True)
    embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count} (Niveau {guild.premium_tier})", inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="Voir l'avatar d'un membre")
@app_commands.describe(member="Le membre dont voir l'avatar")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user

    embed = discord.Embed(
        title=f"🖼️ Avatar de {member.name}",
        color=discord.Color.blue()
    )
    embed.set_image(url=member.display_avatar.url)

    # Boutons pour différentes tailles
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="128px", url=member.display_avatar.with_size(128).url))
    view.add_item(discord.ui.Button(label="256px", url=member.display_avatar.with_size(256).url))
    view.add_item(discord.ui.Button(label="512px", url=member.display_avatar.with_size(512).url))
    view.add_item(discord.ui.Button(label="1024px", url=member.display_avatar.with_size(1024).url))

    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="poll", description="Créer un sondage")
@app_commands.describe(question="La question du sondage", options="Options séparées par des virgules (max 5)")
async def poll(interaction: discord.Interaction, question: str, options: str):
    options_list = [o.strip() for o in options.split(",")][:5]

    if len(options_list) < 2:
        return await interaction.response.send_message("❌ Minimum 2 options requises!", ephemeral=True)

    poll_id = str(random.randint(1000, 9999))

    embed = discord.Embed(
        title=f"📊 {question}",
        description="Cliquez sur un bouton pour voter!",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Créé par {interaction.user.name}")

    view = PollView(options_list, poll_id)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="giveaway", description="Créer un giveaway")
@app_commands.describe(duration="Durée (ex: 1h, 1d)", winners="Nombre de gagnants", prize="Le prix à gagner")
@app_commands.default_permissions(manage_guild=True)
async def giveaway(interaction: discord.Interaction, duration: str, prize: str, winners: int = 1):
    # Parser la durée
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = re.match(r"(\d+)([smhd])", duration.lower())
    if not match:
        return await interaction.response.send_message("❌ Format de durée invalide!", ephemeral=True)

    seconds = int(match.group(1)) * time_units[match.group(2)]
    end_time = int(datetime.datetime.now().timestamp()) + seconds

    embed = discord.Embed(
        title="🎉 GIVEAWAY 🎉",
        description=f"""
**Prix:** {prize}

**Gagnant(s):** {winners}
**Fin:** {discord.utils.format_dt(datetime.datetime.fromtimestamp(end_time), 'R')}
**Organisé par:** {interaction.user.mention}

Réagissez avec 🎉 pour participer!
        """,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"ID: {interaction.id}")

    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    await message.add_reaction("🎉")

    await bot.db.create_giveaway(
        message.id, interaction.channel.id, interaction.guild.id,
        prize, winners, end_time, interaction.user.id
    )


@bot.tree.command(name="remind", description="Créer un rappel")
@app_commands.describe(time="Dans combien de temps (ex: 1h, 30m)", reminder="Ce dont vous voulez être rappelé")
async def remind(interaction: discord.Interaction, time: str, reminder: str):
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = re.match(r"(\d+)([smhd])", time.lower())
    if not match:
        return await interaction.response.send_message("❌ Format de temps invalide!", ephemeral=True)

    seconds = int(match.group(1)) * time_units[match.group(2)]

    await interaction.response.send_message(f"✅ Je vous rappellerai dans **{time}**!")

    await asyncio.sleep(seconds)

    try:
        await interaction.user.send(f"⏰ **Rappel:** {reminder}")
    except:
        await interaction.channel.send(f"⏰ {interaction.user.mention} **Rappel:** {reminder}")


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES SLASH - FUN
# ═══════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="8ball", description="Poser une question au 8ball magique")
@app_commands.describe(question="Votre question")
async def eightball(interaction: discord.Interaction, question: str):
    responses = [
        "Oui, certainement!", "C'est décidément ainsi.", "Sans aucun doute.",
        "Oui, définitivement.", "Vous pouvez compter dessus.", "Très probablement.",
        "Les perspectives sont bonnes.", "Les signes pointent vers oui.",
        "Réponse floue, réessayez.", "Redemandez plus tard.",
        "Mieux vaut ne pas vous le dire maintenant.", "Impossible de prédire maintenant.",
        "Concentrez-vous et redemandez.", "N'y comptez pas.", "Ma réponse est non.",
        "Mes sources disent non.", "Les perspectives ne sont pas si bonnes.", "Très douteux."
    ]

    embed = discord.Embed(
        title="🎱 8Ball",
        color=discord.Color.purple()
    )
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Réponse", value=random.choice(responses), inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="coinflip", description="Lancer une pièce")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Pile", "Face"])
    emoji = "🪙"

    embed = discord.Embed(
        title=f"{emoji} Pile ou Face",
        description=f"La pièce tombe sur... **{result}**!",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="roll", description="Lancer un dé")
@app_commands.describe(sides="Nombre de faces (défaut: 6)", count="Nombre de dés (défaut: 1)")
async def roll(interaction: discord.Interaction, sides: int = 6, count: int = 1):
    if sides < 2 or sides > 100 or count < 1 or count > 10:
        return await interaction.response.send_message("❌ Paramètres invalides!", ephemeral=True)

    results = [random.randint(1, sides) for _ in range(count)]
    total = sum(results)

    embed = discord.Embed(
        title="🎲 Lancer de dé(s)",
        color=discord.Color.blue()
    )
    embed.add_field(name="Résultat(s)", value=" + ".join(map(str, results)), inline=False)
    if count > 1:
        embed.add_field(name="Total", value=str(total), inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rps", description="Pierre, papier, ciseaux")
@app_commands.describe(choice="Votre choix")
async def rps(interaction: discord.Interaction, choice: Literal["pierre", "papier", "ciseaux"]):
    bot_choice = random.choice(["pierre", "papier", "ciseaux"])
    emojis = {"pierre": "🪨", "papier": "📄", "ciseaux": "✂️"}

    wins = {"pierre": "ciseaux", "papier": "pierre", "ciseaux": "papier"}

    if choice == bot_choice:
        result = "Égalité! 🤝"
        color = discord.Color.yellow()
    elif wins[choice] == bot_choice:
        result = "Vous avez gagné! 🎉"
        color = discord.Color.green()
    else:
        result = "Vous avez perdu! 😢"
        color = discord.Color.red()

    embed = discord.Embed(
        title="✊ Pierre, Papier, Ciseaux",
        description=f"""
**Votre choix:** {emojis[choice]} {choice.capitalize()}
**Mon choix:** {emojis[bot_choice]} {bot_choice.capitalize()}

**{result}**
        """,
        color=color
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="joke", description="Obtenir une blague aléatoire")
async def joke(interaction: discord.Interaction):
    jokes = [
        ("Pourquoi les plongeurs plongent-ils toujours en arrière?", "Parce que sinon ils tomberaient dans le bateau!"),
        ("Qu'est-ce qu'un canif?", "Un petit fien!"),
        ("Que dit un informaticien quand il s'ennuie?", "Je me fichier!"),
        ("Pourquoi le Python est-il si populaire?", "Parce qu'il n'a pas de crochets!"),
        ("Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël?", "Un chat peint de Noël!"),
        ("Qu'est-ce qu'un crocodile qui surveille?", "Un croco-vigile!"),
        ("Pourquoi les développeurs n'aiment pas la nature?", "Parce qu'il y a trop de bugs!"),
        ("Comment s'appelle un chat tombé dans un pot de chocolat?", "Un chat-colat!"),
    ]

    setup, punchline = random.choice(jokes)

    embed = discord.Embed(
        title="😂 Blague",
        color=discord.Color.orange()
    )
    embed.add_field(name="Question", value=setup, inline=False)
    embed.add_field(name="Réponse", value=f"||{punchline}||", inline=False)

    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES SLASH - CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

config_group = app_commands.Group(name="config", description="Configuration du bot")


@config_group.command(name="prefix", description="Changer le préfixe du bot")
@app_commands.describe(prefix="Le nouveau préfixe")
@app_commands.default_permissions(administrator=True)
async def config_prefix(interaction: discord.Interaction, prefix: str):
    if len(prefix) > 5:
        return await interaction.response.send_message("❌ Préfixe trop long (max 5 caractères)!", ephemeral=True)

    config = await bot.db.get_guild_config(interaction.guild.id)
    config["prefix"] = prefix
    await bot.db.set_guild_config(interaction.guild.id, config)

    await interaction.response.send_message(f"✅ Préfixe changé en `{prefix}`!")


@config_group.command(name="welcome", description="Configurer les messages de bienvenue")
@app_commands.describe(
    enabled="Activer/désactiver",
    channel="Salon des bienvenues",
    message="Message ({user}, {username}, {server}, {count})",
    auto_role="Rôle automatique"
)
@app_commands.default_permissions(administrator=True)
async def config_welcome(
    interaction: discord.Interaction,
    enabled: bool = None,
    channel: discord.TextChannel = None,
    message: str = None,
    auto_role: discord.Role = None
):
    config = await bot.db.get_guild_config(interaction.guild.id)

    if enabled is not None:
        config["welcome"]["enabled"] = enabled
    if channel:
        config["welcome"]["channel_id"] = channel.id
    if message:
        config["welcome"]["message"] = message
    if auto_role:
        config["welcome"]["auto_role"] = auto_role.id

    await bot.db.set_guild_config(interaction.guild.id, config)

    embed = discord.Embed(
        title="✅ Configuration mise à jour",
        description=f"""
**Activé:** {config['welcome']['enabled']}
**Salon:** {f"<#{config['welcome']['channel_id']}>" if config['welcome']['channel_id'] else "Non défini"}
**Auto-rôle:** {f"<@&{config['welcome']['auto_role']}>" if config['welcome']['auto_role'] else "Non défini"}
        """,
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@config_group.command(name="goodbye", description="Configurer les messages d'au revoir")
@app_commands.describe(
    enabled="Activer/désactiver",
    channel="Salon des au revoirs",
    message="Message ({user}, {server}, {count})"
)
@app_commands.default_permissions(administrator=True)
async def config_goodbye(
    interaction: discord.Interaction,
    enabled: bool = None,
    channel: discord.TextChannel = None,
    message: str = None
):
    config = await bot.db.get_guild_config(interaction.guild.id)

    if enabled is not None:
        config["goodbye"]["enabled"] = enabled
    if channel:
        config["goodbye"]["channel_id"] = channel.id
    if message:
        config["goodbye"]["message"] = message

    await bot.db.set_guild_config(interaction.guild.id, config)

    embed = discord.Embed(
        title="✅ Configuration mise à jour",
        description=f"""
**Activé:** {config['goodbye']['enabled']}
**Salon:** {f"<#{config['goodbye']['channel_id']}>" if config['goodbye']['channel_id'] else "Non défini"}
        """,
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@config_group.command(name="leveling", description="Configurer le système de niveaux")
@app_commands.describe(
    enabled="Activer/désactiver",
    xp_min="XP minimum par message",
    xp_max="XP maximum par message",
    cooldown="Cooldown en secondes",
    channel="Salon pour les level up"
)
@app_commands.default_permissions(administrator=True)
async def config_leveling(
    interaction: discord.Interaction,
    enabled: bool = None,
    xp_min: int = None,
    xp_max: int = None,
    cooldown: int = None,
    channel: discord.TextChannel = None
):
    config = await bot.db.get_guild_config(interaction.guild.id)

    if enabled is not None:
        config["leveling"]["enabled"] = enabled
    if xp_min is not None:
        config["leveling"]["xp_min"] = xp_min
    if xp_max is not None:
        config["leveling"]["xp_max"] = xp_max
    if cooldown is not None:
        config["leveling"]["xp_cooldown"] = cooldown
    if channel:
        config["leveling"]["level_up_channel"] = channel.id

    await bot.db.set_guild_config(interaction.guild.id, config)

    embed = discord.Embed(
        title="✅ Configuration des niveaux",
        description=f"""
**Activé:** {config['leveling']['enabled']}
**XP par message:** {config['leveling']['xp_min']}-{config['leveling']['xp_max']}
**Cooldown:** {config['leveling']['xp_cooldown']}s
**Salon level up:** {f"<#{config['leveling']['level_up_channel']}>" if config['leveling']['level_up_channel'] else "Salon du message"}
        """,
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@config_group.command(name="levelrole", description="Ajouter une récompense de niveau")
@app_commands.describe(level="Niveau requis", role="Rôle à donner")
@app_commands.default_permissions(administrator=True)
async def config_levelrole(interaction: discord.Interaction, level: int, role: discord.Role):
    config = await bot.db.get_guild_config(interaction.guild.id)
    config["leveling"]["role_rewards"][str(level)] = role.id
    await bot.db.set_guild_config(interaction.guild.id, config)

    await interaction.response.send_message(f"✅ Le rôle {role.mention} sera donné au niveau **{level}**!")


@config_group.command(name="logs", description="Configurer le salon de logs")
@app_commands.describe(channel="Salon de logs")
@app_commands.default_permissions(administrator=True)
async def config_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    config = await bot.db.get_guild_config(interaction.guild.id)
    config["moderation"]["log_channel"] = channel.id
    await bot.db.set_guild_config(interaction.guild.id, config)

    await interaction.response.send_message(f"✅ Salon de logs défini sur {channel.mention}!")


@config_group.command(name="automod", description="Configurer l'auto-modération")
@app_commands.describe(
    enabled="Activer/désactiver",
    anti_spam="Bloquer le spam",
    anti_links="Bloquer les liens",
    anti_caps="Bloquer les majuscules excessives",
    max_mentions="Nombre max de mentions"
)
@app_commands.default_permissions(administrator=True)
async def config_automod(
    interaction: discord.Interaction,
    enabled: bool = None,
    anti_spam: bool = None,
    anti_links: bool = None,
    anti_caps: bool = None,
    max_mentions: int = None
):
    config = await bot.db.get_guild_config(interaction.guild.id)

    if enabled is not None:
        config["moderation"]["auto_mod"]["enabled"] = enabled
    if anti_spam is not None:
        config["moderation"]["auto_mod"]["anti_spam"] = anti_spam
    if anti_links is not None:
        config["moderation"]["auto_mod"]["anti_links"] = anti_links
    if anti_caps is not None:
        config["moderation"]["auto_mod"]["anti_caps"] = anti_caps
    if max_mentions is not None:
        config["moderation"]["auto_mod"]["max_mentions"] = max_mentions

    await bot.db.set_guild_config(interaction.guild.id, config)

    embed = discord.Embed(
        title="✅ Auto-modération configurée",
        description=f"""
**Activé:** {config['moderation']['auto_mod']['enabled']}
**Anti-spam:** {config['moderation']['auto_mod']['anti_spam']}
**Anti-liens:** {config['moderation']['auto_mod']['anti_links']}
**Anti-majuscules:** {config['moderation']['auto_mod']['anti_caps']}
**Max mentions:** {config['moderation']['auto_mod']['max_mentions']}
        """,
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@config_group.command(name="bannedword", description="Ajouter/retirer un mot interdit")
@app_commands.describe(action="Ajouter ou retirer", word="Le mot")
@app_commands.default_permissions(administrator=True)
async def config_bannedword(interaction: discord.Interaction, action: Literal["add", "remove"], word: str):
    config = await bot.db.get_guild_config(interaction.guild.id)

    if action == "add":
        if word.lower() not in config["moderation"]["auto_mod"]["banned_words"]:
            config["moderation"]["auto_mod"]["banned_words"].append(word.lower())
            msg = f"✅ `{word}` ajouté aux mots interdits."
        else:
            msg = "❌ Ce mot est déjà interdit."
    else:
        if word.lower() in config["moderation"]["auto_mod"]["banned_words"]:
            config["moderation"]["auto_mod"]["banned_words"].remove(word.lower())
            msg = f"✅ `{word}` retiré des mots interdits."
        else:
            msg = "❌ Ce mot n'est pas dans la liste."

    await bot.db.set_guild_config(interaction.guild.id, config)
    await interaction.response.send_message(msg, ephemeral=True)


@config_group.command(name="tickets", description="Configurer le système de tickets")
@app_commands.describe(
    category="Catégorie pour les tickets",
    support_role="Rôle support",
    log_channel="Salon de logs des tickets"
)
@app_commands.default_permissions(administrator=True)
async def config_tickets(
    interaction: discord.Interaction,
    category: discord.CategoryChannel = None,
    support_role: discord.Role = None,
    log_channel: discord.TextChannel = None
):
    config = await bot.db.get_guild_config(interaction.guild.id)

    if category:
        config["tickets"]["category_id"] = category.id
    if support_role:
        config["tickets"]["support_role"] = support_role.id
    if log_channel:
        config["tickets"]["log_channel"] = log_channel.id

    await bot.db.set_guild_config(interaction.guild.id, config)

    embed = discord.Embed(
        title="✅ Configuration des tickets",
        description=f"""
**Catégorie:** {f"<#{config['tickets']['category_id']}>" if config['tickets']['category_id'] else "Non définie"}
**Rôle support:** {f"<@&{config['tickets']['support_role']}>" if config['tickets']['support_role'] else "Non défini"}
**Logs:** {f"<#{config['tickets']['log_channel']}>" if config['tickets']['log_channel'] else "Non défini"}
        """,
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@config_group.command(name="economy", description="Configurer l'économie")
@app_commands.describe(
    currency_name="Nom de la monnaie",
    currency_symbol="Emoji de la monnaie",
    daily_amount="Montant quotidien"
)
@app_commands.default_permissions(administrator=True)
async def config_economy(
    interaction: discord.Interaction,
    currency_name: str = None,
    currency_symbol: str = None,
    daily_amount: int = None
):
    config = await bot.db.get_guild_config(interaction.guild.id)

    if currency_name:
        config["economy"]["currency_name"] = currency_name
    if currency_symbol:
        config["economy"]["currency_symbol"] = currency_symbol
    if daily_amount:
        config["economy"]["daily_amount"] = daily_amount

    await bot.db.set_guild_config(interaction.guild.id, config)

    embed = discord.Embed(
        title="✅ Configuration de l'économie",
        description=f"""
**Nom:** {config['economy']['currency_name']}
**Symbole:** {config['economy']['currency_symbol']}
**Daily:** {config['economy']['daily_amount']}
        """,
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@config_group.command(name="view", description="Voir la configuration actuelle")
@app_commands.default_permissions(administrator=True)
async def config_view(interaction: discord.Interaction):
    config = await bot.db.get_guild_config(interaction.guild.id)

    embed = discord.Embed(
        title=f"⚙️ Configuration de {interaction.guild.name}",
        color=discord.Color.blue()
    )

    # Général
    embed.add_field(
        name="📌 Général",
        value=f"Préfixe: `{config['prefix']}`",
        inline=True
    )

    # Bienvenue
    welcome = config['welcome']
    embed.add_field(
        name="👋 Bienvenue",
        value=f"Activé: {'✅' if welcome['enabled'] else '❌'}\nSalon: {f'<#{welcome['channel_id']}>' if welcome['channel_id'] else 'Non défini'}",
        inline=True
    )

    # Niveaux
    leveling = config['leveling']
    embed.add_field(
        name="📊 Niveaux",
        value=f"Activé: {'✅' if leveling['enabled'] else '❌'}\nXP: {leveling['xp_min']}-{leveling['xp_max']}",
        inline=True
    )

    # Économie
    economy = config['economy']
    embed.add_field(
        name="💰 Économie",
        value=f"Monnaie: {economy['currency_symbol']} {economy['currency_name']}\nDaily: {economy['daily_amount']}",
        inline=True
    )

    # Auto-mod
    automod = config['moderation']['auto_mod']
    embed.add_field(
        name="🛡️ Auto-modération",
        value=f"Activé: {'✅' if automod['enabled'] else '❌'}\nSpam: {'✅' if automod['anti_spam'] else '❌'} | Liens: {'✅' if automod['anti_links'] else '❌'}",
        inline=True
    )

    # Tickets
    tickets = config['tickets']
    embed.add_field(
        name="🎫 Tickets",
        value=f"Activé: {'✅' if tickets['enabled'] else '❌'}\n{len(tickets['categories'])} catégories",
        inline=True
    )

    await interaction.response.send_message(embed=embed)


bot.tree.add_command(config_group)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDES PERSONNALISÉES
# ═══════════════════════════════════════════════════════════════════════════════

customcmd_group = app_commands.Group(name="customcmd", description="Gestion des commandes personnalisées")


@customcmd_group.command(name="add", description="Ajouter une commande personnalisée")
@app_commands.describe(name="Nom de la commande", response="Réponse ({user}, {username}, {server})")
@app_commands.default_permissions(manage_guild=True)
async def customcmd_add(interaction: discord.Interaction, name: str, response: str):
    await bot.db.add_custom_command(interaction.guild.id, name, response, interaction.user.id)

    config = await bot.db.get_guild_config(interaction.guild.id)
    embed = discord.Embed(
        title="✅ Commande créée",
        description=f"Utilisez `{config['prefix']}{name}` pour déclencher cette commande.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@customcmd_group.command(name="delete", description="Supprimer une commande personnalisée")
@app_commands.describe(name="Nom de la commande")
@app_commands.default_permissions(manage_guild=True)
async def customcmd_delete(interaction: discord.Interaction, name: str):
    await bot.db.delete_custom_command(interaction.guild.id, name)
    await interaction.response.send_message(f"✅ Commande `{name}` supprimée!")


@customcmd_group.command(name="list", description="Lister les commandes personnalisées")
async def customcmd_list(interaction: discord.Interaction):
    commands = await bot.db.get_all_custom_commands(interaction.guild.id)

    if not commands:
        return await interaction.response.send_message("❌ Aucune commande personnalisée!", ephemeral=True)

    config = await bot.db.get_guild_config(interaction.guild.id)

    embed = discord.Embed(
        title="📝 Commandes personnalisées",
        color=discord.Color.blue()
    )

    for cmd in commands[:25]:
        embed.add_field(
            name=f"{config['prefix']}{cmd[1]}",
            value=f"{cmd[2][:50]}..." if len(cmd[2]) > 50 else cmd[2],
            inline=False
        )

    await interaction.response.send_message(embed=embed)


bot.tree.add_command(customcmd_group)


# ═══════════════════════════════════════════════════════════════════════════════
# DÉMARRAGE DU BOT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Chargez votre token depuis les variables d'environnement ou un fichier .env
    TOKEN = os.getenv("DISCORD_TOKEN")

    if not TOKEN:
        print("""
╔══════════════════════════════════════════════════════════════╗
║  ⚠️  TOKEN DISCORD NON TROUVÉ!                               ║
╠══════════════════════════════════════════════════════════════╣
║  Pour démarrer le bot:                                       ║
║                                                              ║
║  1. Créez un fichier .env avec:                              ║
║     DISCORD_TOKEN=votre_token_ici                            ║
║                                                              ║
║  2. Ou définissez la variable d'environnement:               ║
║     export DISCORD_TOKEN=votre_token_ici                     ║
║                                                              ║
║  3. Ou remplacez directement dans le code (non recommandé)   ║
╚══════════════════════════════════════════════════════════════╝
        """)
    else:
        bot.run(TOKEN)