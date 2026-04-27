import discord
from discord import app_commands


# ===========================================================================
# FUNKTION: register_help_command
# Registriert den /help Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. User tippt /help
#   2. Bot antwortet mit einem Embed, das alle verfügbaren Befehle auflistet
#   3. Antwort ist nur für den anfragenden User sichtbar (ephemeral)
# ===========================================================================

def register_help_command(tree: app_commands.CommandTree):

    @tree.command(name="help", description="Alle verfügbaren Bot-Befehle anzeigen")
    async def help_command(interaction: discord.Interaction):

        embed = discord.Embed(
            title="📖 Onboarding-Bot – Befehlsübersicht",
            description=(
                "Hier findest du alle verfügbaren Befehle und ihre Funktionen.\n"
                "Befehle mit 🔒 sind auf bestimmte Rollen beschränkt."
            ),
            colour=discord.Colour.blurple(),
        )

        # ------------------------------------------------------------------
        # /neu
        # ------------------------------------------------------------------
        embed.add_field(
            name="🆕  `/neu`  🔒",
            value=(
                "Nimmt ein neues Mitglied nach dem Erstgespräch auf.\n"
                "Öffnet ein Formular für Star Citizen Handle, Rufname, Status "
                "(*Interessent / Freund / Bot*) und Gesprächsnotizen.\n"
                "Der Bot vergibt die passende Rolle, entfernt die Gast-Rolle, "
                "setzt den Nickname und legt eine Personalakte im Forum an.\n"
                "**Berechtigung:** Recruiter · Moderatoren · Direktoren"
            ),
            inline=False,
        )

        # ------------------------------------------------------------------
        # /aufnahme
        # ------------------------------------------------------------------
        embed.add_field(
            name="✅  `/aufnahme`  🔒",
            value=(
                "Nimmt einen Interessenten offiziell als Mitglied auf.\n"
                "Muss **in der Personalakte** (Forum-Post) des Interessenten "
                "ausgeführt werden. Öffnet ein Formular für Bemerkungen zur Aufnahme.\n"
                "Der Bot entfernt die Interessent-Rolle, vergibt die Mitglied-Rolle "
                "und aktualisiert die Forum-Tags sowie die Personalakte.\n"
                "**Berechtigung:** Recruiter · Moderatoren · Direktoren"
            ),
            inline=False,
        )

        # ------------------------------------------------------------------
        # /ablehnung
        # ------------------------------------------------------------------
        embed.add_field(
            name="❌  `/ablehnung`  🔒",
            value=(
                "Lehnt einen Interessenten ab und entfernt ihn vom Server.\n"
                "Muss **in der Personalakte** (Forum-Post) des Interessenten "
                "ausgeführt werden. Öffnet ein Formular für die Ablehnungsbegründung.\n"
                "Der Bot aktualisiert die Forum-Tags, trägt die Begründung in die "
                "Personalakte ein, sendet dem User eine DM und kickt ihn vom Server.\n"
                "**Berechtigung:** Recruiter · Moderatoren · Direktoren"
            ),
            inline=False,
        )

        # ------------------------------------------------------------------
        # /hallo
        # ------------------------------------------------------------------
        embed.add_field(
            name="👋  `/hallo`",
            value=(
                "Testbefehl – prüft, ob der Bot erreichbar ist und in den "
                "aktuellen Kanal schreiben darf.\n"
                "Der Bot postet *„Hallo! Der Bot funktioniert!"* in den Kanal.\n"
                "**Berechtigung:** Alle Mitglieder"
            ),
            inline=False,
        )

        # ------------------------------------------------------------------
        # Automatische Livestream-Ankündigungen
        # ------------------------------------------------------------------
        embed.add_field(
            name="📡  Automatische Livestream-Ankündigungen",
            value=(
                "Kein Befehl – läuft vollautomatisch im Hintergrund.\n"
                "Sobald ein **Social Media Agent** einen der Livestream-Sprachkanäle "
                "betritt und nach **15 Minuten** noch dort ist, postet der Bot "
                "automatisch eine Ankündigung im StreamNews-Kanal.\n"
                "Verlässt der Agent den Kanal vorher, wird die Ankündigung abgebrochen."
            ),
            inline=False,
        )

        embed.set_footer(text="🔒 = Nur für autorisierte Rollen  •  Alle anderen Befehle sind für jeden nutzbar")

        await interaction.response.send_message(embed=embed, ephemeral=True)
