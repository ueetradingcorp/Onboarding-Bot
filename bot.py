import discord
from discord import app_commands
import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Funktionen des Bots importieren
from onboarding import OnboardingHandler
from neu_befehl import register_neu_command
from hallo_befehl import register_hallo_command
from livestream_manager import LivestreamManager
from aufnahme_befehl import register_aufnahme_command
from ablehnung_befehl import register_ablehnung_command
from help_befehl import register_help_command

# Weitere Funktionen können hier importiert werden, z.B.:
# from sos import register_sos_command
from database import db
from activity_tracker import ActivityTracker
from voice_befehl import register_voice_command, VoiceZeitraumView
from chat_befehl import register_chat_command, ChatZeitraumView
from dbtest_befehl import register_dbtest_command


# ===========================================================================
# KONFIGURATION
# ===========================================================================

TOKEN               = os.environ.get("DISCORD_TOKEN")
INTERESSENT_ROLE_ID = 915601784343498793
PORT                = int(os.environ.get("PORT", 8000))
GUILD_ID            = 915532597306753044

EVENT_MANAGER_ROLE_ID = 1447575016278458420
NOTIFY_ME_ROLE_ID     = 1447575016278458420
NOTIFY_CHANNEL_ID     = 1374030788709843024
EVENT_NEWS_ROLE_ID    = 1493240689985585152


# ===========================================================================
# KLASSE: HealthHandler + HealthServer
# Kleiner HTTP-Server, damit UptimeRobot den Bot als "online" erkennt.
# ===========================================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


class HealthServer:

    def __init__(self, port):
        self.port = port

    def start(self):
        server = HTTPServer(("0.0.0.0", self.port), HealthHandler)
        print(f"🔹 Health-Server läuft auf Port {self.port}")
        threading.Thread(target=server.serve_forever, daemon=True).start()


# ===========================================================================
# KLASSE: OnboardingBot
# Der Discord-Bot. Hier werden alle Handler und Slash-Commands eingebunden.
#
# Neues Feature hinzufügen:
#   1. Neue Datei anlegen, z.B. sos.py mit register_sos_command()
#   2. Oben importieren:           from sos import register_sos_command
#   3. In setup_hook registrieren: register_sos_command(self.tree)
# ===========================================================================

class OnboardingBot(discord.Client):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # CommandTree verwaltet alle Slash-Commands
        self.tree = app_commands.CommandTree(self)

        # Handler für Events einbinden
        self.onboarding = OnboardingHandler(INTERESSENT_ROLE_ID)
        self.livestream = LivestreamManager()
        self.activity_tracker = ActivityTracker()

        # Slash-Commands registrieren
        register_neu_command(self.tree)
        register_hallo_command(self.tree)
        register_aufnahme_command(self.tree)
        register_ablehnung_command(self.tree)
        register_help_command(self.tree)
        register_voice_command(self.tree)
        register_chat_command(self.tree)
        register_dbtest_command(self.tree)
        # register_sos_command(self.tree)

        # Zustand für den Event-Manager
        self.new_events = []
        self.posting_lock = asyncio.Lock()

    # Wird aufgerufen, wenn der Bot erfolgreich verbunden ist
    async def on_ready(self):
        print(f"✅ Bot ist online als {self.user}")
        print(f"🔍 Intents: {self.intents}")

        # Alle User-IDs ermitteln die gerade in einem Voicekanal sitzen
        aktive_user_ids = set()
        for guild in self.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        aktive_user_ids.add(member.id)

        # Offene Sessions bereinigen – aktive User bekommen neue saubere Sessions
        await db.cleanup_open_sessions(aktive_user_ids)

        # Für User die noch im Voice sind: neue Sessions starten
        for guild in self.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        await self.activity_tracker.session_starten(
                            member=member,
                            channel=channel,
                        )

    # setup_hook wird einmalig beim Start aufgerufen
    # Hier werden die Slash-Commands bei Discord angemeldet und die DB verbunden
    async def setup_hook(self):
        await db.connect()
        GUILD = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=GUILD)
        await self.tree.sync(guild=GUILD)
        print("✅ Slash-Commands wurden bei Discord registriert.")

        # Persistent Views registrieren – damit Buttons nach einem Neustart
        # weiterhin funktionieren. Platzhalter-IDs reichen für die Registrierung.
        self.add_view(VoiceZeitraumView(user_id=0, aktueller_zeitraum=30))
        self.add_view(ChatZeitraumView(user_id=0, aktueller_zeitraum=30))
        print("✅ Persistent Views registriert.")

    # Wird aufgerufen, wenn sich Rollen eines Mitglieds ändern
    async def on_member_update(self, before, after):
        await self.onboarding.on_member_update(before, after)

    # Wird aufgerufen, wenn sich der Voice-Status eines Mitglieds ändert
    async def on_voice_state_update(self, member, before, after):
        print(f"🔍 Voice-Event: {member.display_name} | vorher={before.channel} | nachher={after.channel}")
        await self.livestream.on_voice_state_update(member, before, after, self)
        await self.activity_tracker.on_voice_state_update(member, before, after)

    # Wird aufgerufen, wenn eine neue Nachricht empfangen wird
    async def on_message(self, message: discord.Message):
        await self.activity_tracker.on_message(message)

    # Debug-Listener: helfen zu isolieren, ob der Bot überhaupt Gateway-Events
    # für geplante Events empfängt. Wenn UPDATE/DELETE ankommen, aber CREATE
    # nicht, liegt das Problem spezifisch am CREATE-Dispatch von Discord.
    async def on_scheduled_event_update(self, before, after):
        print(f"🔍 DEBUG: on_scheduled_event_update aufgerufen - Event: {after.name}")

    async def on_scheduled_event_delete(self, event):
        print(f"🔍 DEBUG: on_scheduled_event_delete aufgerufen - Event: {event.name}")

    # Wird aufgerufen, wenn ein neues geplantes Event erstellt wird
    async def on_scheduled_event_create(self, event):
        guild = event.guild

        # event.creator_id is always available; event.creator may be None if
        # the user is not in the internal cache.
        creator_id = event.creator_id
        print(f"🔍 Event erkannt: {event.name} | Creator ID: {creator_id}")

        if creator_id is None:
            print("⚠️  creator_id ist None – Event wird ignoriert.")
            return

        # Try cache first, fall back to an API fetch so the member's roles are
        # always available even when the cache is cold.
        creator = guild.get_member(creator_id)
        if creator is None:
            try:
                creator = await guild.fetch_member(creator_id)
            except discord.NotFound:
                print(f"⚠️  Member {creator_id} nicht gefunden – Event wird ignoriert.")
                return
            except discord.HTTPException as exc:
                print(f"⚠️  Fehler beim Laden des Members {creator_id}: {exc}")
                return

        role_ids = [role.id for role in creator.roles]
        print(f"🔍 Rollen von {creator}: {role_ids}")

        if not any(role.id == EVENT_MANAGER_ROLE_ID for role in creator.roles):
            print(f"ℹ️  {creator} hat keine Event-Manager-Rolle – Event wird ignoriert.")
            return

        print(f"✅ Event gespeichert: {event.name}")
        self.new_events.append(event)

        # Only the coroutine that added the very first event starts the timer.
        # We check inside the lock so that concurrent creates don't each start
        # their own sleep.
        async with self.posting_lock:
            if len(self.new_events) == 1:
                await asyncio.sleep(900)  # 15 Minuten
                await self._post_event_notifications(guild)

    async def _post_event_notifications(self, guild):
        if not self.new_events:
            return

        channel = guild.get_channel(NOTIFY_CHANNEL_ID)
        if not channel:
            print("❌ Kanal nicht gefunden!")
            self.new_events = []
            return

        role_mention = f"<@&{EVENT_NEWS_ROLE_ID}>"
        messages = []
        content = f"{role_mention} Neue Events wurden erstellt:\n"

        for ev in self.new_events:
            event_line = f"- {ev.name} ({ev.url})\n"
            content += event_line

            if len(content) > 1800:
                messages.append(content)
                content = ""

        if content:
            messages.append(content)

        try:
            for msg in messages:
                await channel.send(msg)
        except discord.Forbidden as exc:
            print(f"❌ Fehler beim Posten in Kanal {NOTIFY_CHANNEL_ID}: {exc}")
            print(f"❌ Fehlertyp: {type(exc).__name__} – Bot hat keine Berechtigung, in diesen Kanal zu schreiben.")
            self.new_events = []
            return
        except discord.HTTPException as exc:
            print(f"❌ Fehler beim Posten in Kanal {NOTIFY_CHANNEL_ID}: {exc}")
            print(f"❌ Fehlertyp: {type(exc).__name__} (HTTP-Status: {exc.status}, Code: {exc.code})")
            self.new_events = []
            return

        print(f"✅ {len(self.new_events)} Events gepostet und {role_mention} einmal gepingt.")
        self.new_events = []


# ===========================================================================
# EINSTIEGSPUNKT
# ===========================================================================

if __name__ == "__main__":

    HealthServer(PORT).start()

    intents = discord.Intents.default()
    intents.members = True                  # Für Onboarding & Mitgliederliste im Autocomplete
    intents.guilds = True
    intents.guild_scheduled_events = True   # Für Event-Manager-Feature
    intents.voice_states = True             # Für Livestream-Ankündigungs-Feature & Voice-Tracking
    intents.message_content = True          # Für Text-Aktivitätstracking

    print("🔹 Onboarding-Bot startet...")

    if not TOKEN:
        print("❌ DISCORD_TOKEN ist nicht gesetzt! Bitte als Secret hinterlegen.")
    else:
        bot = OnboardingBot(intents=intents)
        bot.run(TOKEN)
