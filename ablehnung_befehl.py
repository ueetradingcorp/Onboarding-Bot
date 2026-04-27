import discord
from discord import app_commands


# ===========================================================================
# KONFIGURATION – Rollen & Tag IDs
# ===========================================================================

# Rollen, die den /ablehnung Befehl ausführen dürfen
ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]

# Rolle, die entfernt wird
INTERESSENT_ROLLE_ID = 915601784343498793

# Forum-Tags
TAG_INTERESSENT = 1046483317433847899
TAG_NOCH_OFFEN  = 1050445275619135538
TAG_ABGELEHNT   = 1046483704819761152
TAG_ERLEDIGT    = 1050445079170519110


# ===========================================================================
# KLASSE: AblehungModal
# Popup-Fenster für die Ablehnungsbegründung.
# Wird im Kontext des Forum-Posts ausgeführt, in dem der Befehl aufgerufen
# wurde – dadurch weiß der Bot, welche Personalakte angepasst werden soll.
# ===========================================================================

class AblehungModal(discord.ui.Modal, title="Interessent ablehnen"):

    ablehnungsbegruendung = discord.ui.TextInput(
        label="Ablehnungsbegründung",
        placeholder="z.B. Nicht geeignet für die Gruppe, fehlende Aktivität, etc.",
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

        # --- 1. Forum-Tags des Threads aktualisieren ---
        # TAG_INTERESSENT und TAG_NOCH_OFFEN entfernen, TAG_ABGELEHNT und TAG_ERLEDIGT setzen
        ersetze_tags = {TAG_INTERESSENT, TAG_NOCH_OFFEN}
        neue_tag_ids = {TAG_ABGELEHNT, TAG_ERLEDIGT}

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

        # --- 2. Eintrag in der Personalakte posten ---
        begruendung = self.ablehnungsbegruendung.value.strip()
        eintrag = (
            f"## ❌ Ablehnung\n\n"
            f"**{self.ziel_user.mention}** wurde als Interessent **abgelehnt**.\n\n"
            f"**Ablehnungsbegründung:**\n{begruendung}\n\n"
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

        # --- 3. DM mit Ablehnungsbegründung senden ---
        dm_gesendet = False
        try:
            await self.ziel_user.send(
                f"Du wurdest von der UEE Trading Corp abgelehnt. Grund: {begruendung}"
            )
            dm_gesendet = True
        except (discord.Forbidden, discord.HTTPException):
            pass

        # --- 4. User vom Server kicken ---
        try:
            await self.ziel_user.kick(reason=begruendung)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Ich habe keine Berechtigung, den User vom Server zu entfernen.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"⚠️ Fehler beim Entfernen des Users vom Server: {e}",
                ephemeral=True,
            )
            return

        # --- Erfolgsmeldung (nur für den ausführenden User sichtbar) ---
        dm_zeile = "• DM mit Ablehnungsbegründung gesendet\n" if dm_gesendet else ""
        await interaction.followup.send(
            f"✅ **{self.ziel_user.display_name}** wurde erfolgreich abgelehnt und vom Server entfernt!\n"
            f"{dm_zeile}"
            f"• Forum-Tags aktualisiert (→ Erledigt / Abgelehnt)\n"
            f"• Eintrag in der Personalakte erstellt\n"
            f"• User vom Server gekickt",
            ephemeral=True,
        )

        print(
            f"❌ Ablehnung: {self.ziel_user.display_name} → abgelehnt & gekickt "
            f"– durchgeführt von {interaction.user.name}"
        )


# ===========================================================================
# FUNKTION: register_ablehnung_command
# Registriert den /ablehnung Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Recruiter öffnet die Personalakte des Interessenten im Forum
#   2. Recruiter tippt /ablehnung und wählt den Interessenten per Autocomplete
#   3. Modal öffnet sich für die Ablehnungsbegründung
#   4. Bot aktualisiert die Forum-Tags, postet einen Eintrag in der Akte,
#      sendet dem User eine DM mit der Begründung und kickt ihn vom Server
# ===========================================================================

def register_ablehnung_command(tree: app_commands.CommandTree):

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
        name="ablehnung",
        description="Interessent ablehnen und vom Server entfernen",
    )
    @app_commands.autocomplete(user=interessent_autocomplete)
    async def ablehnung_command(interaction: discord.Interaction, user: str):

        # --- Berechtigungsprüfung ---
        hat_berechtigung = any(
            rolle.id in ERLAUBTE_ROLLEN_IDS
            for rolle in interaction.user.roles
        )

        if not hat_berechtigung:
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung, den Befehl `/ablehnung` auszuführen.\n"
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
            AblehungModal(ziel_user=ziel_user, thread=interaction.channel)
        )
