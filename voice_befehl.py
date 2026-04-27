import io
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
import matplotlib
matplotlib.use("Agg")  # Kein Display erforderlich (headless)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from database import db


# ===========================================================================
# KONFIGURATION – Rollen & Zeitbereiche
# ===========================================================================

ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]

ZEITBEREICHE = [30, 90, 365]


# ===========================================================================
# HILFSFUNKTION: Diagramm erstellen
# ===========================================================================

def _erstelle_voice_chart(
    username: str,
    days: int,
    rows: list,
) -> io.BytesIO:
    """
    Erstellt ein Liniendiagramm der täglichen Voice-Aktivität.

    Parameter:
        username – Anzeigename des Users (für den Titel)
        days     – Zeitraum in Tagen
        rows     – Datenbankzeilen mit start_time und duration_minutes

    Rückgabe:
        BytesIO-Objekt mit dem PNG-Bild
    """
    # --- Daten aggregieren: Minuten pro Tag summieren ---
    tages_daten: dict[datetime, float] = {}
    for row in rows:
        tag = row["start_time"].astimezone(timezone.utc).date()
        tages_daten[tag] = tages_daten.get(tag, 0.0) + (row["duration_minutes"] or 0.0)

    # --- Vollständige Datumsreihe (auch Tage ohne Aktivität = 0) ---
    heute    = datetime.now(timezone.utc).date()
    startdag = heute - timedelta(days=days - 1)
    alle_tage = [startdag + timedelta(days=i) for i in range(days)]
    werte     = [tages_daten.get(tag, 0.0) for tag in alle_tage]

    # --- Diagramm zeichnen ---
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#2b2d31")   # Discord-Dunkelgrau
    ax.set_facecolor("#313338")

    ax.plot(
        alle_tage, werte,
        color="#5865f2",   # Discord-Blurple
        linewidth=2,
        marker="o",
        markersize=3,
        label="Sprachminuten",
    )
    ax.fill_between(alle_tage, werte, alpha=0.15, color="#5865f2")

    # Achsen & Beschriftungen
    ax.set_title(
        f"🎙️  Voice-Aktivität – {username}  ({days} Tage)",
        color="white", fontsize=14, pad=12,
    )
    ax.set_xlabel("Datum", color="#b5bac1", fontsize=10)
    ax.set_ylabel("Minuten", color="#b5bac1", fontsize=10)
    ax.tick_params(colors="#b5bac1")
    ax.spines[:].set_color("#4e5058")

    # X-Achsen-Format je nach Zeitraum
    if days <= 30:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m."))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    elif days <= 90:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m."))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator())

    fig.autofmt_xdate(rotation=30)
    ax.legend(facecolor="#313338", labelcolor="white", framealpha=0.8)
    ax.grid(axis="y", color="#4e5058", linestyle="--", linewidth=0.6, alpha=0.7)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ===========================================================================
# FUNKTION: register_voice_command
# Registriert den /voice Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Moderator tippt /voice @user [zeitraum]
#   2. Bot prüft Berechtigung
#   3. Bot lädt Voice-Daten aus der Datenbank
#   4. Bot erstellt ein Liniendiagramm und sendet es als Embed
# ===========================================================================

def register_voice_command(tree: app_commands.CommandTree):

    @tree.command(
        name="voice",
        description="Voice-Aktivität eines Users als Diagramm anzeigen",
    )
    @app_commands.describe(
        user      = "Der User, dessen Voice-Aktivität angezeigt werden soll",
        zeitraum  = "Zeitraum in Tagen (Standard: 30)",
    )
    @app_commands.choices(zeitraum=[
        app_commands.Choice(name="30 Tage",  value=30),
        app_commands.Choice(name="90 Tage",  value=90),
        app_commands.Choice(name="365 Tage", value=365),
    ])
    async def voice_command(
        interaction: discord.Interaction,
        user:        discord.Member,
        zeitraum:    int = 30,
    ):
        # --- Berechtigungsprüfung ---
        hat_berechtigung = any(
            rolle.id in ERLAUBTE_ROLLEN_IDS
            for rolle in interaction.user.roles
        )
        if not hat_berechtigung:
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung, den Befehl `/voice` auszuführen.\n"
                "Dieser Befehl ist nur für Moderatoren, Direktoren und Recruiter verfügbar.",
                ephemeral=True,
            )
            return

        # Zeitraum absichern
        if zeitraum not in ZEITBEREICHE:
            zeitraum = 30

        # Antwort verzögern, da Datenbankabfrage + Bildgenerierung Zeit braucht
        await interaction.response.defer(ephemeral=False)

        # --- Daten aus der Datenbank laden ---
        rows = await db.get_voice_activity(user_id=user.id, days=zeitraum)

        if not rows:
            await interaction.followup.send(
                f"📭 Keine Voice-Aktivität für **{user.display_name}** "
                f"in den letzten **{zeitraum} Tagen** gefunden.",
            )
            return

        # --- Gesamtminuten berechnen ---
        gesamt_minuten = sum(r["duration_minutes"] or 0.0 for r in rows)
        gesamt_stunden = gesamt_minuten / 60.0

        # --- Diagramm erstellen ---
        try:
            buf = _erstelle_voice_chart(
                username = user.display_name,
                days     = zeitraum,
                rows     = rows,
            )
        except Exception as exc:
            print(f"❌ Fehler beim Erstellen des Voice-Diagramms: {exc}")
            await interaction.followup.send(
                "❌ Beim Erstellen des Diagramms ist ein Fehler aufgetreten.",
            )
            return

        # --- Embed zusammenbauen ---
        embed = discord.Embed(
            title       = f"🎙️  Voice-Aktivität – {user.display_name}",
            description = (
                f"Zeitraum: **{zeitraum} Tage**\n"
                f"Gesamt: **{gesamt_stunden:.1f} Stunden** "
                f"({gesamt_minuten:.0f} Minuten)"
            ),
            colour      = discord.Colour.blurple(),
            timestamp   = discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_image(url="attachment://voice_activity.png")
        embed.set_footer(text=f"Angefragt von {interaction.user.display_name}")

        await interaction.followup.send(
            embed = embed,
            file  = discord.File(buf, filename="voice_activity.png"),
        )

        print(
            f"📊 /voice: {user.display_name} | {zeitraum} Tage | "
            f"{gesamt_stunden:.1f} h – angefragt von {interaction.user.name}"
        )
