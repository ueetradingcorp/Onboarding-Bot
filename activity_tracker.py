import discord
from datetime import datetime, timezone

from database import db


# ===========================================================================
# KLASSE: ActivityTracker
# Lauscht auf Voice- und Text-Events und schreibt die Daten in die Datenbank.
#
# Einbindung in bot.py:
#   tracker = ActivityTracker()
#   # Voice-Event weiterleiten:
#   await tracker.on_voice_state_update(member, before, after)
#   # Text-Event weiterleiten:
#   await tracker.on_message(message)
# ===========================================================================

class ActivityTracker:

    def __init__(self):
        # Laufende Voice-Sitzungen: {user_id: {"session_id": int, "start": datetime}}
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
        """
        if member.bot:
            return

        user_id = member.id
        now     = datetime.now(timezone.utc)

        # --- Kanal verlassen oder gewechselt ---
        if before.channel is not None and before.channel != after.channel:
            session = self._active_sessions.pop(user_id, None)
            if session:
                duration = (now - session["start"]).total_seconds() / 60.0
                await db.update_voice_session_end(
                    session_id       = session["session_id"],
                    end_time         = now,
                    duration_minutes = round(duration, 2),
                )
                print(
                    f"🎙️  Voice-Ende: {member.display_name} "
                    f"({duration:.1f} min in #{before.channel.name})"
                )

        # --- Kanal betreten oder gewechselt ---
        if after.channel is not None and before.channel != after.channel:
            session_id = await db.insert_voice_session_start(
                user_id    = user_id,
                channel_id = after.channel.id,
                start_time = now,
            )
            if session_id is not None:
                self._active_sessions[user_id] = {
                    "session_id": session_id,
                    "start":      now,
                }
                print(
                    f"🎙️  Voice-Start: {member.display_name} "
                    f"→ #{after.channel.name}"
                )

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
