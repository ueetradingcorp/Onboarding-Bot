import discord
from datetime import datetime, timezone

from database import db


# ===========================================================================
# KLASSE: ActivityTracker
# Lauscht auf Voice- und Text-Events und schreibt die Daten in die Datenbank.
#
# Einbindung in bot.py:
#   tracker = ActivityTracker()
#   await tracker.on_voice_state_update(member, before, after)
#   await tracker.on_message(message)
#
# DESIGN-ENTSCHEIDUNG – kein reiner In-Memory-State:
#   Bei jedem Railway-Neustart geht der Dict `_active_sessions` verloren.
#   Deshalb wird beim Leave-Event ZUERST die Datenbank nach einer offenen
#   Session für diesen User befragt, bevor der In-Memory-Fallback greift.
#   So überlebt das Tracking auch Neustarts zuverlässig.
# ===========================================================================

class ActivityTracker:

    def __init__(self):
        # Laufende Voice-Sitzungen: {user_id: {"session_id": int, "start": datetime}}
        # Dient als schneller Cache – DB ist die einzige Quelle der Wahrheit.
        self._active_sessions: dict[int, dict] = {}

    # -----------------------------------------------------------------------
    # Voice-Tracking
    # -----------------------------------------------------------------------

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """
        Wird aufgerufen, wenn sich der Voice-Status eines Mitglieds ändert.

        Fälle:
          • Kanal betreten  → Sitzung starten
          • Kanal verlassen → Sitzung beenden und Dauer speichern
          • Kanal wechseln  → alte Sitzung beenden, neue starten

        Robustheit gegen Bot-Neustarts:
          Ist der User nicht im In-Memory-Dict (weil der Bot neu gestartet
          wurde), wird die offene Session direkt aus der DB geladen und
          korrekt abgeschlossen.
        """
        if member.bot:
            return

        user_id = member.id
        now     = datetime.now(timezone.utc)

        # --- Kanal verlassen oder gewechselt → Session beenden ---
        if before.channel is not None and before.channel != after.channel:
            await self._session_beenden(member, before.channel.name, now)

        # --- Kanal betreten oder gewechselt → neue Session starten ---
        if after.channel is not None and before.channel != after.channel:
            await self._session_starten_intern(member, after.channel, now)

    async def _session_beenden(
        self,
        member: discord.Member,
        kanal_name: str,
        now: datetime,
    ):
        """
        Beendet die laufende Session eines Users.

        Strategie:
          1. In-Memory-Cache prüfen (Normalfall).
          2. Falls nicht im Cache (nach Neustart): offene Session aus DB laden.
          3. Dauer berechnen und Session in DB abschließen.
        """
        user_id = member.id
        session = self._active_sessions.pop(user_id, None)

        if session is None:
            # Nach einem Bot-Neustart: offene Session aus der DB holen
            session = await db.get_open_session(user_id)
            if session is None:
                # Kein offener Eintrag → nichts zu tun
                print(
                    f"⚠️  Voice-Ende ohne offene Session: {member.display_name} "
                    f"(#{kanal_name}) – kein DB-Eintrag gefunden."
                )
                return
            print(
                f"🔄 Session aus DB wiederhergestellt für {member.display_name} "
                f"(#{kanal_name})"
            )

        duration = (now - session["start"]).total_seconds() / 60.0

        # Mindestdauer 0.01 min (~0,6 Sek.) um sinnlose Null-Einträge zu vermeiden
        if duration < 0.01:
            print(
                f"⏩ Voice-Session zu kurz (<0,6 s), wird verworfen: "
                f"{member.display_name} (#{kanal_name})"
            )
            await db.delete_voice_session(session["session_id"])
            return

        await db.update_voice_session_end(
            session_id       = session["session_id"],
            end_time         = now,
            duration_minutes = round(duration, 2),
        )
        print(
            f"🎙️  Voice-Ende: {member.display_name} "
            f"({duration:.1f} min in #{kanal_name})"
        )

    async def _session_starten_intern(
        self,
        member: discord.Member,
        channel,
        now: datetime,
    ):
        """
        Startet eine neue Voice-Session und schreibt sie in die DB.
        Stellt sicher, dass nie zwei offene Sessions für denselben User
        gleichzeitig existieren.
        """
        user_id = member.id

        # Sicherheitscheck: offene Sessions aus vorherigem Lauf bereinigen
        # (passiert z.B. wenn cleanup_open_sessions beim Start nicht ausgeführt wurde)
        await db.close_dangling_sessions_for_user(user_id, now)

        session_id = await db.insert_voice_session_start(
            user_id    = user_id,
            channel_id = channel.id,
            start_time = now,
        )
        if session_id is not None:
            self._active_sessions[user_id] = {
                "session_id": session_id,
                "start":      now,
            }
            print(
                f"🎙️  Voice-Start: {member.display_name} "
                f"→ #{channel.name}"
            )

    async def session_starten(self, member: discord.Member, channel):
        """
        Startet eine neue Voice-Session direkt – ohne ein Voice-State-Event.
        Wird beim Bot-Start in on_ready() verwendet, für User die bereits
        im Voice sitzen.
        """
        now = datetime.now(timezone.utc)
        await self._session_starten_intern(member, channel, now)

    # -----------------------------------------------------------------------
    # Text-Tracking
    # -----------------------------------------------------------------------

    async def on_message(self, message: discord.Message):
        """
        Wird aufgerufen, wenn eine neue Nachricht empfangen wird.
        Bots und DMs werden ignoriert.
        """
        if message.author.bot:
            return
        if not message.guild:
            return

        await db.insert_text_message(
            user_id    = message.author.id,
            channel_id = message.channel.id,
            timestamp  = message.created_at,
        )
