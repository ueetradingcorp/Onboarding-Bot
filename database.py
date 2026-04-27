import os
import asyncpg


# ===========================================================================
# KONFIGURATION
# ===========================================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


# ===========================================================================
# KLASSE: Database
# Verwaltet die PostgreSQL-Verbindung und stellt Funktionen zum Lesen und
# Schreiben von Aktivitätsdaten bereit.
#
# Tabellen:
#   user_voice_activity  – Sprachkanal-Sitzungen (Join/Leave + Dauer)
#   user_text_activity   – Textnachrichten (aggregiert pro User/Kanal/Tag)
# ===========================================================================

class Database:

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    # -----------------------------------------------------------------------
    # Verbindung aufbauen und Tabellen anlegen
    # -----------------------------------------------------------------------

    async def connect(self):
        """Verbindungspool öffnen und Tabellen erstellen (falls nicht vorhanden)."""
        if not DATABASE_URL:
            print("⚠️  DATABASE_URL ist nicht gesetzt – Aktivitätstracking deaktiviert.")
            return

        try:
            self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
            await self._create_tables()
            print("✅ Datenbankverbindung hergestellt und Tabellen geprüft.")
        except Exception as exc:
            print(f"❌ Datenbankverbindung fehlgeschlagen: {exc}")
            self.pool = None

    async def _create_tables(self):
        """Erstellt die benötigten Tabellen, falls sie noch nicht existieren."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_voice_activity (
                    id               SERIAL PRIMARY KEY,
                    user_id          BIGINT      NOT NULL,
                    channel_id       BIGINT      NOT NULL,
                    start_time       TIMESTAMPTZ NOT NULL,
                    end_time         TIMESTAMPTZ,
                    duration_minutes FLOAT
                );
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_voice_user_start
                    ON user_voice_activity (user_id, start_time);
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_text_activity (
                    id            SERIAL PRIMARY KEY,
                    user_id       BIGINT      NOT NULL,
                    channel_id    BIGINT      NOT NULL,
                    timestamp     TIMESTAMPTZ NOT NULL,
                    message_count INTEGER     NOT NULL DEFAULT 1
                );
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_text_user_timestamp
                    ON user_text_activity (user_id, timestamp);
            """)

    # -----------------------------------------------------------------------
    # Voice-Aktivität
    # -----------------------------------------------------------------------

    async def insert_voice_session_start(
        self,
        user_id: int,
        channel_id: int,
        start_time,
    ) -> int | None:
        """
        Legt eine neue Voice-Sitzung an (end_time und duration noch NULL).
        Gibt die ID des neuen Eintrags zurück.
        """
        if not self.pool:
            return None
        try:
            row = await self.pool.fetchrow(
                """
                INSERT INTO user_voice_activity (user_id, channel_id, start_time)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                user_id, channel_id, start_time,
            )
            return row["id"] if row else None
        except Exception as exc:
            print(f"❌ DB insert_voice_session_start: {exc}")
            return None

    async def update_voice_session_end(
        self,
        session_id: int,
        end_time,
        duration_minutes: float,
    ):
        """Schließt eine Voice-Sitzung ab (end_time + duration setzen)."""
        if not self.pool:
            return
        try:
            await self.pool.execute(
                """
                UPDATE user_voice_activity
                   SET end_time         = $1,
                       duration_minutes = $2
                 WHERE id = $3
                """,
                end_time, duration_minutes, session_id,
            )
        except Exception as exc:
            print(f"❌ DB update_voice_session_end: {exc}")

    async def get_voice_activity(
        self,
        user_id: int,
        days: int,
    ) -> list[asyncpg.Record]:
        """
        Gibt alle abgeschlossenen Voice-Sitzungen eines Users der letzten
        `days` Tage zurück, sortiert nach start_time aufsteigend.
        """
        if not self.pool:
            return []
        try:
            rows = await self.pool.fetch(
                """
                SELECT start_time, end_time, duration_minutes, channel_id
                  FROM user_voice_activity
                 WHERE user_id  = $1
                   AND end_time IS NOT NULL
                   AND start_time >= NOW() - ($2 || ' days')::INTERVAL
                 ORDER BY start_time ASC
                """,
                user_id, str(days),
            )
            return rows
        except Exception as exc:
            print(f"❌ DB get_voice_activity: {exc}")
            return []

    # -----------------------------------------------------------------------
    # Text-Aktivität
    # -----------------------------------------------------------------------

    async def insert_text_message(
        self,
        user_id: int,
        channel_id: int,
        timestamp,
    ):
        """Speichert eine einzelne Textnachricht."""
        if not self.pool:
            return
        try:
            await self.pool.execute(
                """
                INSERT INTO user_text_activity (user_id, channel_id, timestamp)
                VALUES ($1, $2, $3)
                """,
                user_id, channel_id, timestamp,
            )
        except Exception as exc:
            print(f"❌ DB insert_text_message: {exc}")

    async def get_text_activity(
        self,
        user_id: int,
        days: int,
    ) -> list[asyncpg.Record]:
        """
        Gibt die tägliche Nachrichtenanzahl eines Users der letzten `days`
        Tage zurück (aggregiert nach Datum), sortiert aufsteigend.
        """
        if not self.pool:
            return []
        try:
            rows = await self.pool.fetch(
                """
                SELECT DATE(timestamp AT TIME ZONE 'UTC') AS day,
                       COUNT(*)                           AS message_count
                  FROM user_text_activity
                 WHERE user_id   = $1
                   AND timestamp >= NOW() - ($2 || ' days')::INTERVAL
                 GROUP BY day
                 ORDER BY day ASC
                """,
                user_id, str(days),
            )
            return rows
        except Exception as exc:
            print(f"❌ DB get_text_activity: {exc}")
            return []

    # -----------------------------------------------------------------------
    # Verbindung schließen
    # -----------------------------------------------------------------------

    async def close(self):
        """Verbindungspool schließen."""
        if self.pool:
            await self.pool.close()
            print("🔹 Datenbankverbindung geschlossen.")


# Globale Singleton-Instanz – wird von allen Modulen importiert
db = Database()
