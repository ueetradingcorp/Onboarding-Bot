import discord
from discord import app_commands


# ===========================================================================
# KONFIGURATION – Rollen & Tag IDs
# ===========================================================================

# Rollen, die den /aufnahme Befehl ausführen dürfen
ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]

# Rolle, die entfernt wird
INTERESSENT_ROLLE_ID = 915601784343498793

# Rolle, die vergeben wird
MITGLIED_ROLLE_ID = 915572343600992296

# Forum-Tags
TAG_NOCH_OFFEN  = 1050445275619135538
TAG_ERLEDIGT    = 1050445079170519110
TAG_INTERESSENT = 1046483317433847899
TAG_MITGLIED    = 1046483453534818354


# ===========================================================================
# KLASSE: AufnahmeModal
# Popup-Fenster für Bemerkungen zur Aufnahme (z.B. RSI-Einladung gesendet).
# Wird im Kontext des Forum-Posts ausgeführt, in dem der Befehl aufgerufen
# wurde – dadurch weiß der Bot, welche Personalakte angepasst werden soll.
# ===========================================================================

class AufnahmeModal(discord.ui.Modal, title="Interessent als Mitglied aufnehmen"):

    bemerkung = discord.ui.TextInput(
        label="Bemerkungen zur Aufnahme",
        placeholder="z.B. Aufnahme durchgeführt, RSI-Einladung gesendet und angenommen.",
        style=discord.TextStyle.paragraph,
        required=True,
    )

    def __init__(self, ziel_user: discord.Member, thread: discord.Thread):
        super().__init__()
        self.ziel_user = ziel_user
        self.thread    = thread

    async def on_submit(self, interaction: discord.Interaction):
        # Sofort bestätigen, damit Discord kein Timeout meldet
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild

        # --- 1. Interessent-Rolle entfernen & Mitglied-Rolle vergeben ---
        interessent_rolle = guild.get_role(INTERESSENT_ROLLE_ID)
        mitglied_rolle    = guild.get_role(MITGLIED_ROLLE_ID)

        if interessent_rolle and interessent_rolle in self.ziel_user.roles:
            try:
                await self.ziel_user.remove_roles(interessent_rolle)
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ Ich habe keine Berechtigung, die Interessent-Rolle zu entfernen.",
                    ephemeral=True,
                )
                return

        if mitglied_rolle is None:
            await interaction.followup.send(
                "❌ Mitglied-Rolle nicht gefunden. Bitte die Rollen-ID prüfen.",
                ephemeral=True,
            )
            return

        try:
            await self.ziel_user.add_roles(mitglied_rolle)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Ich habe keine Berechtigung, die Mitglied-Rolle zu vergeben.",
                ephemeral=True,
            )
            return

        # --- 2. Forum-Tags des Threads aktualisieren ---
        # Alle bisherigen Tags beibehalten, außer den zu ersetzenden
        ersetze_tags = {TAG_NOCH_OFFEN, TAG_INTERESSENT}
        neue_tag_ids = {TAG_ERLEDIGT, TAG_MITGLIED}

        # Aktuelle Tags des Threads filtern und neue hinzufügen
        aktuelle_tag_ids = {tag.id for tag in self.thread.applied_tags}
        ziel_tag_ids     = (aktuelle_tag_ids - ersetze_tags) | neue_tag_ids

        # Tag-Objekte aus dem übergeordneten Forum-Kanal holen
        forum_kanal = self.thread.parent
        if forum_kanal is None or not isinstance(forum_kanal, discord.ForumChannel):
            await interaction.followup.send(
                "❌ Übergeordneter Forum-Kanal nicht gefunden.",
                ephemeral=True,
            )
            return

        gesetzte_tags = [tag for tag in forum_kanal.available_tags if tag.id in ziel_tag_ids]

        try:
            await self.thread.edit(applied_tags=gesetzte_tags)
        except discord.Forbidden:
            await interaction.followup.send(
                "⚠️ Forum-Tags konnten nicht aktualisiert werden (fehlende Berechtigung).",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"⚠️ Fehler beim Aktualisieren der Forum-Tags: {e}",
                ephemeral=True,
            )

        # --- 3. Eintrag in der Personalakte posten ---
        eintrag = (
            f"## ✅ Aufnahme als Mitglied\n\n"
            f"**{self.ziel_user.mention}** wurde als **Mitglied** aufgenommen.\n\n"
            f"**Bemerkungen:**\n{self.bemerkung.value.strip()}\n\n"
            f"*Eingetragen von {interaction.user.mention}*"
        )

        try:
            await self.thread.send(eintrag)
        except discord.Forbidden:
            await interaction.followup.send(
                "⚠️ Konnte keinen Eintrag in der Personalakte erstellen (fehlende Berechtigung).",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"⚠️ Fehler beim Erstellen des Personalakten-Eintrags: {e}",
                ephemeral=True,
            )

        # --- 4. Erfolgsmeldung (nur für den ausführenden User sichtbar) ---
        await interaction.followup.send(
            f"✅ **{self.ziel_user.display_name}** wurde erfolgreich als Mitglied aufgenommen!\n"
            f"• Interessent-Rolle entfernt\n"
            f"• Mitglied-Rolle vergeben\n"
            f"• Forum-Tags aktualisiert (→ Erledigt / Mitglied)\n"
            f"• Eintrag in der Personalakte erstellt",
            ephemeral=True,
        )

        print(
            f"✅ Aufnahme: {self.ziel_user.display_name} → Mitglied "
            f"– durchgeführt von {interaction.user.name}"
        )


# ===========================================================================
# FUNKTION: register_aufnahme_command
# Registriert den /aufnahme Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Recruiter öffnet die Personalakte des Interessenten im Forum
#   2. Recruiter tippt /aufnahme und wählt den Interessenten per Autocomplete
#   3. Modal öffnet sich für Bemerkungen
#   4. Bot entfernt Interessent-Rolle, vergibt Mitglied-Rolle,
#      aktualisiert die Forum-Tags und postet einen Eintrag in der Akte
# ===========================================================================

def register_aufnahme_command(tree: app_commands.CommandTree):

    # Autocomplete: nur Mitglieder mit Interessent-Rolle vorschlagen
    async def interessent_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:

        vorschlaege = []

        for member in interaction.guild.members:
            if member.bot:
                continue

            # Nur Mitglieder mit Interessent-Rolle anzeigen
            hat_interessent_rolle = any(r.id == INTERESSENT_ROLLE_ID for r in member.roles)
            if not hat_interessent_rolle:
                continue

            name = member.display_name
            if current.lower() in name.lower():
                vorschlaege.append(
                    app_commands.Choice(name=name, value=str(member.id))
                )

            if len(vorschlaege) >= 25:
                break

        return vorschlaege

    @tree.command(
        name="aufnahme",
        description="Interessent nach der Interessentenphase als Mitglied aufnehmen",
    )
    @app_commands.autocomplete(user=interessent_autocomplete)
    async def aufnahme_command(interaction: discord.Interaction, user: str):

        # --- Berechtigungsprüfung ---
        hat_berechtigung = any(
            rolle.id in ERLAUBTE_ROLLEN_IDS
            for rolle in interaction.user.roles
        )

        if not hat_berechtigung:
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung, den Befehl `/aufnahme` auszuführen.\n"
                "Dieser Befehl ist nur für Moderatoren, Direktoren und Recruiter verfügbar.",
                ephemeral=True,
            )
            return

        # --- Prüfen ob der Befehl in einem Forum-Thread ausgeführt wird ---
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "❌ Dieser Befehl muss direkt in der Personalakte des Interessenten "
                "(einem Forum-Post) ausgeführt werden.",
                ephemeral=True,
            )
            return

        # --- Ausgewählten User laden ---
        ziel_user = interaction.guild.get_member(int(user))

        if ziel_user is None:
            await interaction.response.send_message(
                "❌ User nicht gefunden. Bitte erneut versuchen.",
                ephemeral=True,
            )
            return

        # --- Modal öffnen ---
        await interaction.response.send_modal(
            AufnahmeModal(ziel_user=ziel_user, thread=interaction.channel)
        )
