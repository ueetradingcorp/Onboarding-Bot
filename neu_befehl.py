import discord
from discord import app_commands
import aiohttp
import asyncio
import re
import os


# ===========================================================================
# KONFIGURATION – Rollen & Kanal IDs
# ===========================================================================

# Star Citizen API Key (von https://starcitizen-api.com)
# Als Environment Variable setzen: STARCITIZEN_API_KEY
STARCITIZEN_API_KEY = os.environ.get("STARCITIZEN_API_KEY", "")

# Rollen, die den /neu Befehl ausführen dürfen
ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]

# Rollen, die dem neuen User zugewiesen werden
INTERESSENT_ROLLE_ID = 915601784343498793
FREUND_ROLLE_ID      = 966290443090407464

# Rolle, die beim Aufnehmen entfernt wird
GAST_ROLLE_ID        = 915546303113596949

# Personalakten-Forum
FORUM_KANAL_ID = 1046482975879073912

# Forum-Tags
TAG_INTERESSENT    = 1046483317433847899
TAG_FREUND         = 1046483373146787841
TAG_NOCH_OFFEN     = 1050445275619135538
TAG_ERLEDIGT       = 1050445079170519110
TAG_BOT            = 1491928901423857775
TAG_KEIN_INTERVIEW = 1434285332471484478


# ===========================================================================
# HILFSFUNKTIONEN
# ===========================================================================

async def get_sc_handle_from_input(eingabe: str) -> tuple[str, str]:
    """
    Versucht, aus der Eingabe (URL oder Handle) das Star Citizen Handle zu ermitteln.

    Returns:
        tuple: (handle, fehler_nachricht)
        - Bei Erfolg: (handle, "")
        - Bei Fehler: ("", fehler_nachricht)
    """
    eingabe = eingabe.strip()

    # Prüfen, ob es eine URL ist
    url_pattern = r'robertsspaceindustries\.com(?:/[a-z]{2})?/citizens/([A-Za-z0-9_-]+)'
    url_match = re.search(url_pattern, eingabe)

    if url_match:
        handle = url_match.group(1)
        print(f"🔹 SC-Handle aus URL extrahiert: {handle}")
    else:
        # Direkte Eingabe → ungeprüft übernehmen, keine API-Abfrage
        handle = eingabe
        print(f"🔹 SC-Handle direkt eingegeben (ungeprüft): {handle}")
        return (handle, "")

    # Nur bei URL-Eingabe: Handle per API verifizieren
    if STARCITIZEN_API_KEY:
        try:
            async with aiohttp.ClientSession() as session:
                # Korrekte Host-URL laut Doku: api.starcitizen-api.com
                # Modus "auto": prüft zuerst Cache, dann live – zuverlässiger als "cache" allein
                # Timeout auf 10s, da live-Abfragen länger dauern können
                api_url = f"https://api.starcitizen-api.com/{STARCITIZEN_API_KEY}/v1/auto/user/{handle}"
                print(f"🔹 SC-API Anfrage: {api_url}")

                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    print(f"🔹 SC-API Status: {response.status}")

                    if response.status == 200:
                        data = await response.json()
                        print(f"🔹 SC-API Antwort: success={data.get('success')}, source={data.get('source')}")

                        if data.get("success") == 1:
                            verified_handle = data["data"]["profile"]["handle"]
                            print(f"✅ SC-Handle verifiziert: {verified_handle}")
                            return (verified_handle, "")
                        else:
                            print(f"❌ SC-API: Handle nicht gefunden. Antwort: {data}")
                            return ("", f"❌ Star Citizen Handle **{handle}** wurde nicht gefunden.\nBitte prüfe die Schreibweise oder gib den RSI-Profillink ein.")
                    elif response.status == 404:
                        print(f"❌ SC-API: 404 für Handle '{handle}'")
                        return ("", f"❌ Star Citizen Handle **{handle}** existiert nicht.")
                    else:
                        # Unerwarteter Statuscode → Handle ungeprüft durchlassen
                        print(f"⚠️ SC-API: Statuscode {response.status} – Handle wird ungeprüft verwendet.")
                        return (handle, "")

        except asyncio.TimeoutError:
            print(f"⚠️ SC-API Timeout für '{handle}' – Handle wird ungeprüft verwendet.")
            return (handle, "")
        except Exception as e:
            print(f"⚠️ SC-API Fehler für '{handle}': {e}")
            return (handle, "")

    # Ohne API-Key: Handle ungeprüft zurückgeben
    print("⚠️ Kein STARCITIZEN_API_KEY gesetzt – Handle wird ungeprüft verwendet.")
    return (handle, "")


# ===========================================================================
# KLASSE: NeuModal
# Das Popup-Fenster mit den restlichen Feldern.
# Der User wurde bereits per Autocomplete ausgewählt und wird
# als Parameter übergeben – kein Tippfehler möglich.
# ===========================================================================

class NeuModal(discord.ui.Modal, title="Neues Mitglied aufnehmen"):

    # Star Citizen In-Game Name oder RSI-Profillink
    sc_handle_input = discord.ui.TextInput(
        label="Star Citizen Handle oder RSI-Profil-Link",
        placeholder="z.B. StarPilot42 oder https://robertsspaceindustries.com/citizens/StarPilot42",
        required=False,
    )

    # Rufname, mit dem die Person angesprochen werden möchte
    nickname = discord.ui.TextInput(
        label="Wie soll die Person angesprochen werden?",
        placeholder="z.B. Max (bei Bot leer lassen)",
        required=False,
    )

    # Status: Interessent oder Freund
    status = discord.ui.TextInput(
        label="Status: Interessent oder Freund?",
        placeholder="i = Interessent  /  f = Freund  /  Bot = Bot",
        required=True,
    )

    # Notizen und Datum aus dem Erstgespräch
    notizen = discord.ui.TextInput(
        label="Notizen zum Erstgespräch",
        placeholder="z.B. 06.04.2026 – Positives Gespräch, interessiert an...",
        style=discord.TextStyle.paragraph,
        required=True,
    )

    def __init__(self, ziel_user: discord.Member):
        super().__init__()
        self.ziel_user = ziel_user

    # Wird aufgerufen, wenn das Modal abgesendet wird
    async def on_submit(self, interaction: discord.Interaction):
        # Sofort bestätigen, damit Discord kein Timeout meldet
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild

        # --- 0. Star Citizen Handle ermitteln ---
        status_eingabe = self.status.value.strip().lower()
        ist_bot        = (status_eingabe == "bot")

        if ist_bot:
            sc_handle = ""
            fehler    = ""
        else:
            # Handle und Nickname sind bei echten Mitgliedern Pflicht
            if not self.sc_handle_input.value.strip():
                await interaction.followup.send(
                    "❌ Bitte einen Star Citizen Handle oder RSI-Profillink eintragen.",
                    ephemeral=True
                )
                return
            if not self.nickname.value.strip():
                await interaction.followup.send(
                    "❌ Bitte einen Rufnamen eintragen.",
                    ephemeral=True
                )
                return
            sc_handle, fehler = await get_sc_handle_from_input(self.sc_handle_input.value)

        if fehler:
            await interaction.followup.send(fehler, ephemeral=True)
            return

        # --- 1. Status auswerten ---
        if status_eingabe in ("i", "interessent"):
            mitglieds_rolle_id = INTERESSENT_ROLLE_ID
            forum_tag_ids      = [TAG_INTERESSENT, TAG_NOCH_OFFEN]
            status_anzeige     = "Interessent"
        elif status_eingabe in ("f", "freund"):
            mitglieds_rolle_id = FREUND_ROLLE_ID
            forum_tag_ids      = [TAG_FREUND, TAG_ERLEDIGT]
            status_anzeige     = "Freund"
        elif status_eingabe == "bot":
            mitglieds_rolle_id = None
            forum_tag_ids      = [TAG_BOT, TAG_KEIN_INTERVIEW, TAG_ERLEDIGT]
            status_anzeige     = "Bot"
        else:
            await interaction.followup.send(
                "❌ Status nicht erkannt. Bitte **Interessent**, **Freund** oder **Bot** eintragen.",
                ephemeral=True
            )
            return

        # --- 2. Neue Rolle zuweisen & Gast-Rolle entfernen (nur bei echten Mitgliedern) ---
        if not ist_bot:
            try:
                neue_rolle = guild.get_role(mitglieds_rolle_id)
                await self.ziel_user.add_roles(neue_rolle)
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ Ich habe keine Berechtigung, Rollen zu vergeben.",
                    ephemeral=True
                )
                return

            gast_rolle = guild.get_role(GAST_ROLLE_ID)
            if gast_rolle and gast_rolle in self.ziel_user.roles:
                try:
                    await self.ziel_user.remove_roles(gast_rolle)
                except discord.Forbidden:
                    await interaction.followup.send(
                        "⚠️ Gast-Rolle konnte nicht entfernt werden (fehlende Berechtigung).",
                        ephemeral=True
                    )

        # --- 3. Nickname & Titel bestimmen ---
        if ist_bot:
            # Kein Nickname setzen; Titel der Personalakte: "Bot | Discord-Handle"
            voller_name  = f"{sc_handle} | {self.nickname.value.strip()}"
            forum_titel  = f"Bot | {self.ziel_user.name}"
        else:
            voller_name = f"{sc_handle} | {self.nickname.value.strip()}"
            forum_titel = voller_name
            try:
                await self.ziel_user.edit(nick=voller_name)
            except discord.Forbidden:
                await interaction.followup.send(
                    "⚠️ Nickname konnte nicht gesetzt werden (fehlende Berechtigung oder Serverbesitzer).",
                    ephemeral=True
                )

        # --- 4. Forum-Post erstellen ---
        forum_kanal = guild.get_channel(FORUM_KANAL_ID)

        if forum_kanal is None:
            await interaction.followup.send(
                "❌ Personalakten-Forum nicht gefunden. Bitte die Kanal-ID prüfen.",
                ephemeral=True
            )
            return

        # RSI-Profillink nur anzeigen, wenn eine URL eingegeben wurde
        sc_eingabe = self.sc_handle_input.value.strip()
        url_match  = re.search(r'robertsspaceindustries\.com(?:/[a-z]{2})?/citizens/[A-Za-z0-9_-]+', sc_eingabe)
        rsi_link_zeile = f"**RSI-Profil:** {sc_eingabe}\n" if url_match else ""

        # Inhalt des Forum-Posts
        post_inhalt = (
            f"## Personalakte – {forum_titel}\n\n"
            f"**Discord-Handle:** {self.ziel_user.name}\n"
            f"**Discord-ID:** {self.ziel_user.id}\n"
            f"**Star Citizen Handle:** {sc_handle}\n"
            f"{rsi_link_zeile}"
            f"**Status:** {status_anzeige}\n\n"
            f"**Notizen & Datum des Erstgesprächs:**\n{self.notizen.value.strip()}\n\n"
            f"*Eintrag erstellt von {interaction.user.mention}*"
        )

        # Passende Tags aus dem Forum holen
        verfuegbare_tags = forum_kanal.available_tags
        gesetzte_tags = [tag for tag in verfuegbare_tags if tag.id in forum_tag_ids]

        # Forum-Post erstellen
        try:
            await forum_kanal.create_thread(
                name=forum_titel,
                content=post_inhalt,
                applied_tags=gesetzte_tags,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Ich habe keine Berechtigung, im Personalakten-Forum zu posten.",
                ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Fehler beim Erstellen des Forum-Posts: {e}",
                ephemeral=True
            )
            return

        # --- 5. Bot kicken (nach Erstellung der Personalakte) ---
        if ist_bot:
            kick_begruendung = "Da du nicht antwortest, bist du vermutlich ein Bot und daher hier unerwünscht. Bye!"

            # DM senden, bevor der User vom Server geworfen wird
            try:
                await self.ziel_user.send(kick_begruendung)
            except discord.Forbidden:
                # DMs deaktiviert oder blockiert – kein Abbruch
                pass

            try:
                await self.ziel_user.kick(reason=kick_begruendung)
            except discord.Forbidden:
                await interaction.followup.send(
                    "⚠️ Bot-Account konnte nicht gekickt werden (fehlende Berechtigung).",
                    ephemeral=True
                )
                return

            await interaction.followup.send(
                f"🤖 **{voller_name}** wurde als Bot identifiziert!\n"
                f"• Personalakte im Forum erstellt\n"
                f"• Account vom Server gekickt",
                ephemeral=True
            )
            print(f"🤖 Bot gekickt: {voller_name} – gemeldet von {interaction.user.name}")
            return

        # --- 6. Erfolgsmeldung (nur für den Recruiter sichtbar) ---
        await interaction.followup.send(
            f"✅ **{voller_name}** wurde erfolgreich aufgenommen!\n"
            f"• Rolle **{status_anzeige}** vergeben\n"
            f"• Gast-Rolle entfernt\n"
            f"• Nickname gesetzt\n"
            f"• Personalakte im Forum erstellt",
            ephemeral=True
        )

        print(f"✅ Neuer Eintrag: {voller_name} ({status_anzeige}) – erstellt von {interaction.user.name}")


# ===========================================================================
# FUNKTION: register_neu_command
# Registriert den /neu Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Recruiter tippt /neu
#   2. Discord zeigt ein Textfeld "User" mit Live-Vorschlägen
#   3. Nach der Auswahl öffnet sich das Modal mit den restlichen Feldern
# ===========================================================================

def register_neu_command(tree: app_commands.CommandTree):

    # Autocomplete-Funktion: gibt passende Mitglieder als Vorschläge zurück
    async def user_autocomplete(
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:

        vorschlaege = []

        for member in interaction.guild.members:
            # Bots überspringen
            if member.bot:
                continue

            # Nur Mitglieder mit der Gast-Rolle anzeigen
            hat_gast_rolle = any(r.id == GAST_ROLLE_ID for r in member.roles)
            if not hat_gast_rolle:
                continue

            # Nur Mitglieder anzeigen, die zur Eingabe passen
            name = member.display_name  # Zeigt Nickname wenn vorhanden, sonst Username
            if current.lower() in name.lower():
                vorschlaege.append(
                    app_commands.Choice(name=name, value=str(member.id))
                )

            # Discord erlaubt maximal 25 Vorschläge
            if len(vorschlaege) >= 25:
                break

        return vorschlaege

    # Der eigentliche /neu Slash-Command
    @tree.command(name="neu", description="Neues Mitglied nach Erstgespräch aufnehmen")
    @app_commands.autocomplete(user=user_autocomplete)
    async def neu_command(interaction: discord.Interaction, user: str):

        # --- Berechtigungsprüfung ---
        hat_berechtigung = any(
            rolle.id in ERLAUBTE_ROLLEN_IDS
            for rolle in interaction.user.roles
        )

        if not hat_berechtigung:
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung, den Befehl `/neu` auszuführen.\n"
                "Dieser Befehl ist nur für Moderatoren, Direktoren und Recruiter verfügbar.",
                ephemeral=True
            )
            return

        # --- Ausgewählten User anhand der ID laden ---
        ziel_user = interaction.guild.get_member(int(user))

        if ziel_user is None:
            await interaction.response.send_message(
                "❌ User nicht gefunden. Bitte erneut versuchen.",
                ephemeral=True
            )
            return

        # --- Modal mit dem ausgewählten User öffnen ---
        await interaction.response.send_modal(NeuModal(ziel_user=ziel_user))
