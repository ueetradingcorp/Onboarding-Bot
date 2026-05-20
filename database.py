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
#   user_text_activity   – Textnachrichten (eine Zeile pro Nachricht)
#
# NULL-Schutz:
#   • UNIQUE-Index auf (user_id) WHERE end_time IS NULL verhindert
#     doppelte offene Sessions auf DB-Ebene.
#   • get_open_session() erlaubt dem ActivityTracker, Sessions nach einem
#     Bot-Neustart wiederherzustellen, ohne In-Memory-State zu brauchen.
#   • close_dangling_sessions_for_user() schließt alte offene Einträge
#     ab, bevor eine neue Session geöffnet wird.
# ===========================================================================

class Database:

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    # -----------------------------------------------------------------------
    # Verbindung aufbauen und Tabellen anlegen
    # -----------------------------------------------------------------------

    async def connect(self):
        """Verbindungspool öffnen und Tabellen/Indizes erstellen."""
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
        """Erstellt Tabellen und Indizes, falls sie noch nicht existieren."""
        async with self.pool.acquire() as conn:
            # --- Voice-Tabelle ---
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
            # UNIQUE-Partial-Index: Pro User darf es nur eine offene Session geben.
            # ON CONFLICT in insert_voice_session_start nutzt diesen Index.
            await conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_one_open_per_user
                    ON user_voice_activity (user_id)
                    WHERE end_time IS NULL;
            """)

            # --- Text-Tabelle ---
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
        Gibt die ID des neuen Eintrags zurück, oder None bei Fehler.

        ON CONFLICT DO NOTHING schützt gegen Race Conditions beim
        gleichzeitigen Einfügen (z.B. doppeltes on_ready).
        """
        if not self.pool:
            return None
        try:
            row = await self.pool.fetchrow(
                """
                INSERT INTO user_voice_activity (user_id, channel_id, start_time)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
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
                   AND end_time IS NULL
                """,
                end_time, duration_minutes, session_id,
            )
        except Exception as exc:
            print(f"❌ DB update_voice_session_end: {exc}")

    async def delete_voice_session(self, session_id: int):
        """
        Löscht eine Voice-Session komplett (z.B. wenn sie zu kurz war
        um sinnvoll zu sein, oder als veralteter offener Eintrag).
        """
        if not self.pool:
            return
        try:
            await self.pool.execute(
                "DELETE FROM user_voice_activity WHERE id = $1",
                session_id,
            )
        except Exception as exc:
            print(f"❌ DB delete_voice_session: {exc}")

    async def get_open_session(self, user_id: int) -> dict | None:
        """
        Gibt die aktuell offene Voice-Session eines Users zurück,
        oder None wenn keine existiert.

        Wird vom ActivityTracker genutzt, um nach einem Bot-Neustart
        laufende Sessions ohne In-Memory-State korrekt abschließen zu können.

        Rückgabe: {"session_id": int, "start": datetime} oder None
        """
        if not self.pool:
            return None
        try:
            row = await self.pool.fetchrow(
                """
                SELECT id, start_time
                  FROM user_voice_activity
                 WHERE user_id  = $1
                   AND end_time IS NULL
                 ORDER BY start_time DESC
                 LIMIT 1
                """,
                user_id,
            )
            if row:
                return {"session_id": row["id"], "start": row["start_time"]}
            return None
        except Exception as exc:
            print(f"❌ DB get_open_session: {exc}")
            return None

    async def close_dangling_sessions_for_user(self, user_id: int, now):
        """
        Schließt alle noch offenen Sessions eines Users ab, BEVOR eine neue
        geöffnet wird. Verhindert doppelte offene Einträge, die entstehen
        können wenn der Bot während einer aktiven Voice-Session neu startet
        und cleanup_open_sessions() den User fälschlicherweise als aktiv
        eingestuft hat.

        Offene Sessions, die älter als 16 Stunden sind, werden gelöscht
        (unrealistische Dauer → Datenmüll). Jüngere werden korrekt
        abgeschlossen.
        """
        if not self.pool:
            return
        try:
            from datetime import timedelta
            grenze = now - timedelta(hours=16)

            # Zu alte offene Sessions löschen
            deleted = await self.pool.execute(
                """
                DELETE FROM user_voice_activity
                 WHERE user_id  = $1
                   AND end_time IS NULL
                   AND start_time < $2
                """,
                user_id, grenze,
            )

            # Jüngere offene Sessions mit berechneter Dauer abschließen
            rows = await self.pool.fetch(
                """
                SELECT id, start_time
                  FROM user_voice_activity
                 WHERE user_id  = $1
                   AND end_time IS NULL
                """,
                user_id,
            )
            for row in rows:
                dauer = (now - row["start_time"]).total_seconds() / 60.0
                await self.pool.execute(
                    """
                    UPDATE user_voice_activity
                       SET end_time         = $1,
                           duration_minutes = $2
                     WHERE id = $3
                    """,
                    now, round(dauer, 2), row["id"],
                )
                print(
                    f"🧹 Dangling Session abgeschlossen: "
                    f"user_id={user_id}, id={row['id']}, {dauer:.1f} min"
                )
        except Exception as exc:
            print(f"❌ DB close_dangling_sessions_for_user: {exc}")

    async def get_voice_activity(
        self,
        user_id: int,
        days: int,
    ) -> list[asyncpg.Record]:
        """
        Gibt alle abgeschlossenen Voice-Sitzungen eines Users der letzten
        `days` Tage zurück, sortiert nach start_time aufsteigend.
        Nur Einträge mit duration_minutes > 0 werden zurückgegeben.
        """
        if not self.pool:
            return []
        try:
            rows = await self.pool.fetch(
                """
                SELECT start_time, end_time, duration_minutes, channel_id
                  FROM user_voice_activity
                 WHERE user_id          = $1
                   AND end_time         IS NOT NULL
                   AND duration_minutes  > 0
                   AND start_time       >= NOW() - ($2 || ' days')::INTERVAL
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
    # Startup-Bereinigung
    # -----------------------------------------------------------------------

    async def cleanup_open_sessions(self, aktive_user_ids: set[int]):
        """
        Bereinigt offene Voice-Sessions beim Bot-Start.

        Für jeden offenen Eintrag:
          • User ist noch im Voice  → Eintrag löschen; ActivityTracker
                                      startet gleich eine saubere neue Session.
          • User hat Voice verlassen → Session mit realer Dauer abschließen,
                                      damit die Zeit nicht verloren geht.
          • Session älter als 16 h  → Löschen (unrealistische Dauer).
        """
        if not self.pool:
            return
        try:
            from datetime import timedelta
            jetzt = __import__('datetime').datetime.now(
                __import__('datetime').timezone.utc
            )
            grenze_zu_alt = jetzt - timedelta(hours=16)

            offene = await self.pool.fetch(
                "SELECT id, user_id, start_time FROM user_voice_activity WHERE end_time IS NULL"
            )

            if not offene:
                print("✅ Keine offenen Voice-Sessions gefunden.")
                return

            abgeschlossen = 0
            geloescht     = 0

            for row in offene:
                # Zu alte Einträge direkt löschen (Datenmüll)
                if row["start_time"] < grenze_zu_alt:
                    await self.pool.execute(
                        "DELETE FROM user_voice_activity WHERE id = $1", row["id"]
                    )
                    geloescht += 1
                    print(
                        f"🗑️  Veraltete offene Session gelöscht: "
                        f"user_id={row['user_id']}, id={row['id']}"
                    )
                    continue

                if row["user_id"] in aktive_user_ids:
                    # User ist noch im Voice → Eintrag löschen,
                    # ActivityTracker startet gleich eine saubere neue Session
                    await self.pool.execute(
                        "DELETE FROM user_voice_activity WHERE id = $1", row["id"]
                    )
                    geloescht += 1
                else:
                    # User hat Voice verlassen → Dauer berechnen und abschließen
                    dauer = (jetzt - row["start_time"]).total_seconds() / 60.0
                    await self.pool.execute(
                        """
                        UPDATE user_voice_activity
                           SET end_time         = $1,
                               duration_minutes = $2
                         WHERE id = $3
                        """,
                        jetzt, round(dauer, 2), row["id"]
                    )
                    abgeschlossen += 1

            if abgeschlossen > 0:
                print(f"🧹 {abgeschlossen} unterbrochene Voice-Session(s) abgeschlossen.")
            if geloescht > 0:
                print(f"🔄 {geloescht} Session(s) bereinigt (neu gestartet oder zu alt).")

        except Exception as exc:
            print(f"❌ DB cleanup_open_sessions: {exc}")

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
