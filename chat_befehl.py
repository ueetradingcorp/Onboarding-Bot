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

def _erstelle_chat_chart(
    username: str,
    days: int,
    rows: list,
) -> io.BytesIO:
    """
    Erstellt ein Balkendiagramm der täglichen Textnachrichten-Aktivität.

    Parameter:
        username – Anzeigename des Users (für den Titel)
        days     – Zeitraum in Tagen
        rows     – Datenbankzeilen mit day und message_count

    Rückgabe:
        BytesIO-Objekt mit dem PNG-Bild
    """
    # --- Daten aus den DB-Zeilen extrahieren ---
    tages_daten: dict = {}
    for row in rows:
        tages_daten[row["day"]] = int(row["message_count"])

    # --- Vollständige Datumsreihe (auch Tage ohne Aktivität = 0) ---
    heute    = datetime.now(timezone.utc).date()
    startdag = heute - timedelta(days=days - 1)
    alle_tage = [startdag + timedelta(days=i) for i in range(days)]
    werte     = [tages_daten.get(tag, 0) for tag in alle_tage]

    # --- Diagramm zeichnen ---
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#2b2d31")   # Discord-Dunkelgrau
    ax.set_facecolor("#313338")

    # Balkenbreite je nach Zeitraum anpassen
    balken_breite = max(0.4, 0.8 - days / 500)

    ax.bar(
        alle_tage, werte,
        width     = balken_breite,
        color     = "#57f287",   # Discord-Grün
        alpha     = 0.85,
        label     = "Nachrichten",
        zorder    = 2,
    )

    # Achsen & Beschriftungen
    ax.set_title(
        f"💬  Chat-Aktivität – {username}  ({days} Tage)",
        color="white", fontsize=14, pad=12,
    )
    ax.set_xlabel("Datum", color="#b5bac1", fontsize=10)
    ax.set_ylabel("Nachrichten", color="#b5bac1", fontsize=10)
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
    ax.grid(axis="y", color="#4e5058", linestyle="--", linewidth=0.6, alpha=0.7, zorder=1)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ===========================================================================
# FUNKTION: register_chat_command
# Registriert den /chat Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Moderator tippt /chat @user [zeitraum]
#   2. Bot prüft Berechtigung
#   3. Bot lädt Text-Daten aus der Datenbank
#   4. Bot erstellt ein Balkendiagramm und sendet es als Embed
# ===========================================================================

def register_chat_command(tree: app_commands.CommandTree):

    @tree.command(
        name="chat",
        description="Chat-Aktivität eines Users als Diagramm anzeigen",
    )
    @app_commands.describe(
        user      = "Der User, dessen Chat-Aktivität angezeigt werden soll",
        zeitraum  = "Zeitraum in Tagen (Standard: 30)",
    )
    @app_commands.choices(zeitraum=[
        app_commands.Choice(name="30 Tage",  value=30),
        app_commands.Choice(name="90 Tage",  value=90),
        app_commands.Choice(name="365 Tage", value=365),
    ])
    async def chat_command(
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
                "❌ Du hast keine Berechtigung, den Befehl `/chat` auszuführen.\n"
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
        rows = await db.get_text_activity(user_id=user.id, days=zeitraum)

        if not rows:
            await interaction.followup.send(
                f"📭 Keine Chat-Aktivität für **{user.display_name}** "
                f"in den letzten **{zeitraum} Tagen** gefunden.",
            )
            return

        # --- Gesamtnachrichten berechnen ---
        gesamt_nachrichten = sum(int(r["message_count"]) for r in rows)
        aktive_tage        = len(rows)

        # --- Diagramm erstellen ---
        try:
            buf = _erstelle_chat_chart(
                username = user.display_name,
                days     = zeitraum,
                rows     = rows,
            )
        except Exception as exc:
            print(f"❌ Fehler beim Erstellen des Chat-Diagramms: {exc}")
            await interaction.followup.send(
                "❌ Beim Erstellen des Diagramms ist ein Fehler aufgetreten.",
            )
            return

        # --- Embed zusammenbauen ---
        embed = discord.Embed(
            title       = f"💬  Chat-Aktivität – {user.display_name}",
            description = (
                f"Zeitraum: **{zeitraum} Tage**\n"
                f"Gesamt: **{gesamt_nachrichten:,} Nachrichten** "
                f"an **{aktive_tage} aktiven Tagen**"
            ),
            colour      = discord.Colour.green(),
            timestamp   = discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_image(url="attachment://chat_activity.png")
        embed.set_footer(text=f"Angefragt von {interaction.user.display_name}")

        await interaction.followup.send(
            embed = embed,
            file  = discord.File(buf, filename="chat_activity.png"),
        )

        print(
            f"📊 /chat: {user.display_name} | {zeitraum} Tage | "
            f"{gesamt_nachrichten} Nachrichten – angefragt von {interaction.user.name}"
        )
