import discord
from discord import app_commands


# ===========================================================================
# KONFIGURATION
# ===========================================================================

NOTIFY_CHANNEL_ID = 1374030788709843024


# ===========================================================================
# FUNKTION: register_hallo_command
# Registriert den /hallo Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. User tippt /hallo
#   2. Bot postet "Hallo! Der Bot funktioniert!" in den Kanal, wo der Befehl ausgeführt wurde
#   3. User bekommt eine ephemere Bestätigung
# ===========================================================================

def register_hallo_command(tree: app_commands.CommandTree):

    @tree.command(name="hallo", description="Testnachricht in diesen Kanal posten")
    async def hallo_command(interaction: discord.Interaction):

        channel = interaction.channel

        if channel is None:
            await interaction.response.send_message(
                "❌ Kanal nicht gefunden.",
                ephemeral=True,
            )
            return

        try:
            await channel.send("Hallo! Der Bot funktioniert!")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Ich habe keine Berechtigung, in diesen Kanal zu schreiben.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Fehler beim Senden der Nachricht: {e}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ Nachricht in diesem Kanal gepostet!",
            ephemeral=True,
        )
