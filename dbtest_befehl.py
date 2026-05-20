import discord
from discord import app_commands
from database import db


# ===========================================================================
# KONFIGURATION – Rollen
# ===========================================================================

ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]


# ===========================================================================
# FUNKTION: register_dbtest_command
# Registriert den /dbtest Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Moderator tippt /dbtest
#   2. Bot prüft die Datenbankverbindung
#   3. Bot zeigt wie viele Voice- und Chat-Einträge in der DB sind
#   4. Bot zeigt die letzten 3 Einträge beider Tabellen zur Kontrolle
# ===========================================================================

def register_dbtest_command(tree: app_commands.CommandTree):

    @tree.command(
        name="dbtest",
        description="Datenbankverbindung und Tracking prüfen",
    )
    async def dbtest_command(interaction: discord.Interaction):

        # --- Berechtigungsprüfung ---
        hat_berechtigung = any(
            rolle.id in ERLAUBTE_ROLLEN_IDS
            for rolle in interaction.user.roles
        )
        if not hat_berechtigung:
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung, den Befehl `/dbtest` auszuführen.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # --- 1. Verbindung prüfen ---
        if not db.pool:
            await interaction.followup.send(
                "❌ **Keine Datenbankverbindung!**\n"
                "Die DATABASE_URL ist nicht gesetzt oder die Verbindung ist fehlgeschlagen.\n"
                "Bitte die Railway-Logs prüfen.",
                ephemeral=True,
            )
            return

        # --- 2. Anzahl der Einträge abrufen ---
        try:
            voice_gesamt = await db.pool.fetchval("SELECT COUNT(*) FROM user_voice_activity")
            chat_gesamt  = await db.pool.fetchval("SELECT COUNT(*) FROM user_text_activity")

            voice_heute  = await db.pool.fetchval(
                "SELECT COUNT(*) FROM user_voice_activity WHERE start_time >= NOW() - INTERVAL '24 hours'"
            )
            chat_heute   = await db.pool.fetchval(
                "SELECT COUNT(*) FROM user_text_activity WHERE timestamp >= NOW() - INTERVAL '24 hours'"
            )
        except Exception as exc:
            await interaction.followup.send(
                f"❌ Fehler beim Abfragen der Datenbank:\n```{exc}```",
                ephemeral=True,
            )
            return

        # --- 3. Letzte 3 Voice-Einträge ---
        try:
            letzte_voice = await db.pool.fetch(
                """
                SELECT user_id, channel_id, start_time, end_time, duration_minutes
                  FROM user_voice_activity
                 ORDER BY start_time DESC
                 LIMIT 3
                """
            )
        except Exception:
            letzte_voice = []

        # --- 4. Letzte 3 Chat-Einträge ---
        try:
            letzte_chat = await db.pool.fetch(
                """
                SELECT user_id, channel_id, timestamp
                  FROM user_text_activity
                 ORDER BY timestamp DESC
                 LIMIT 3
                """
            )
        except Exception:
            letzte_chat = []

        # --- 5. Ergebnis zusammenbauen ---
        embed = discord.Embed(
            title="🔍 Datenbank-Test",
            colour=discord.Colour.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        # Verbindungsstatus
        embed.add_field(
            name="✅ Verbindung",
            value="Datenbankverbindung ist aktiv.",
            inline=False,
        )

        # Statistiken
        embed.add_field(
            name="🎙️ Voice-Tracking",
            value=(
                f"Einträge gesamt: **{voice_gesamt}**\n"
                f"Letzte 24h: **{voice_heute}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="💬 Chat-Tracking",
            value=(
                f"Einträge gesamt: **{chat_gesamt}**\n"
                f"Letzte 24h: **{chat_heute}**"
            ),
            inline=True,
        )

        # Letzte Voice-Einträge
        if letzte_voice:
            voice_zeilen = []
            for row in letzte_voice:
                guild = interaction.guild
                member = guild.get_member(row["user_id"])
                name = member.display_name if member else f"ID {row['user_id']}"
                start = row["start_time"].strftime("%d.%m. %H:%M")
                if row["duration_minutes"]:
                    dm = row["duration_minutes"]
                    dauer = f"{int(dm // 60)} Std. {int(dm % 60)} Min." if dm >= 60 else f"{dm:.1f} Min."
                else:
                    dauer = "läuft noch"
                voice_zeilen.append(f"• {name} – {start} ({dauer})")
            embed.add_field(
                name="🕐 Letzte Voice-Einträge",
                value="\n".join(voice_zeilen),
                inline=False,
            )
        else:
            embed.add_field(
                name="🕐 Letzte Voice-Einträge",
                value="Noch keine Einträge vorhanden.\n"
                      "➡️ Betritt kurz einen Sprachkanal und verlasse ihn wieder,\n"
                      "dann nochmal `/dbtest` ausführen.",
                inline=False,
            )

        # Letzte Chat-Einträge
        if letzte_chat:
            chat_zeilen = []
            for row in letzte_chat:
                guild = interaction.guild
                member = guild.get_member(row["user_id"])
                name = member.display_name if member else f"ID {row['user_id']}"
                zeit = row["timestamp"].strftime("%d.%m. %H:%M")
                chat_zeilen.append(f"• {name} – {zeit}")
            embed.add_field(
                name="🕐 Letzte Chat-Einträge",
                value="\n".join(chat_zeilen),
                inline=False,
            )
        else:
            embed.add_field(
                name="🕐 Letzte Chat-Einträge",
                value="Noch keine Einträge vorhanden.\n"
                      "➡️ Schreib eine Testnachricht in einen Kanal,\n"
                      "dann nochmal `/dbtest` ausführen.",
                inline=False,
            )

        embed.set_footer(text=f"Angefragt von {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)
