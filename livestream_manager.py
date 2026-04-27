import asyncio
import discord

# ===========================================================================
# KONFIGURATION
# ===========================================================================

SOCIAL_MEDIA_AGENT_ROLE_ID = 1386251560907964456
LIVESTREAM_CHANNEL_IDS     = {1494358599151915008, 1494358673349411067}
STREAM_NEWS_CHANNEL_ID     = 1494370889842557180
STREAMNEWS_ROLE_ID         = 1493240942897926287

ANNOUNCEMENT_DELAY_SECONDS = 900  # 15 Minuten


# ===========================================================================
# KLASSE: LivestreamManager
# Überwacht Livestream-Sprachkanäle und kündigt an, wenn ein Social Media
# Agent einen der Kanäle betritt und nach 15 Minuten noch dort ist.
# ===========================================================================

class LivestreamManager:

    def __init__(self):
        # Aktive Timer: member_id -> asyncio.Task
        # Verhindert doppelte Timer, wenn ein User den Kanal wechselt.
        self._pending: dict[int, asyncio.Task] = {}

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
        bot: discord.Client,
    ) -> None:
        # Prüfen ob der User die Social-Media-Agent-Rolle hat
        if not any(role.id == SOCIAL_MEDIA_AGENT_ROLE_ID for role in member.roles):
            return

        joined_livestream = (
            after.channel is not None
            and after.channel.id in LIVESTREAM_CHANNEL_IDS
            and (before.channel is None or before.channel.id != after.channel.id)
        )

        left_or_switched = (
            before.channel is not None
            and before.channel.id in LIVESTREAM_CHANNEL_IDS
            and (after.channel is None or after.channel.id != before.channel.id)
        )

        # Wenn der User einen Livestream-Kanal verlässt oder wechselt:
        # laufenden Timer abbrechen, damit keine veraltete Ankündigung gepostet wird.
        if left_or_switched and member.id in self._pending:
            self._pending.pop(member.id).cancel()
            print(f"ℹ️  Livestream-Timer für {member} abgebrochen (Kanal verlassen).")

        # Wenn der User einen Livestream-Kanal betritt: Timer starten
        if joined_livestream:
            # Eventuell noch laufenden alten Timer ersetzen
            if member.id in self._pending:
                self._pending[member.id].cancel()

            channel_id = after.channel.id  # type: ignore[union-attr]
            task = asyncio.create_task(
                self._announce_after_delay(member, channel_id, bot)
            )
            self._pending[member.id] = task
            print(
                f"⏳ Livestream-Timer gestartet für {member} "
                f"in Kanal {channel_id} ({ANNOUNCEMENT_DELAY_SECONDS // 60} Min.)."
            )

    async def _announce_after_delay(
        self,
        member: discord.Member,
        channel_id: int,
        bot: discord.Client,
    ) -> None:
        try:
            await asyncio.sleep(ANNOUNCEMENT_DELAY_SECONDS)

            # Prüfen ob der User noch im selben Livestream-Kanal ist
            current_voice = member.voice
            if (
                current_voice is None
                or current_voice.channel is None
                or current_voice.channel.id != channel_id
            ):
                print(f"ℹ️  {member} hat den Livestream-Kanal verlassen – keine Ankündigung.")
                return

            # Ankündigung im StreamNews-Kanal posten
            stream_news_channel = bot.get_channel(STREAM_NEWS_CHANNEL_ID)
            if stream_news_channel is None:
                print(f"❌ StreamNews-Kanal {STREAM_NEWS_CHANNEL_ID} nicht gefunden!")
                return

            role_mention   = f"<@&{STREAMNEWS_ROLE_ID}>"
            member_mention = member.mention
            message = (
                f"{role_mention} {member_mention} beginnt gerade seinen Livestream. "
                f"Schaltet doch ein."
            )

            try:
                await stream_news_channel.send(message)  # type: ignore[union-attr]
                print(f"✅ Livestream-Ankündigung für {member} gepostet.")
            except discord.Forbidden as exc:
                print(f"❌ Keine Berechtigung zum Posten in StreamNews-Kanal: {exc}")
            except discord.HTTPException as exc:
                print(f"❌ Fehler beim Posten der Livestream-Ankündigung: {exc}")

        except asyncio.CancelledError:
            # Timer wurde abgebrochen (User hat Kanal verlassen) – kein Problem
            pass
        finally:
            # Aufräumen: Task aus dem Dict entfernen, falls noch vorhanden
            self._pending.pop(member.id, None)
