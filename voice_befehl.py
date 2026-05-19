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
# HILFSFUNKTION: Nachricht zusammenbauen und senden/aktualisieren
# ===========================================================================

async def _sende_voice_nachricht(
    interaction: discord.Interaction,
    user: discord.Member,
    zeitraum: int,
    original_user_id: int,
    edit: bool = False,
):
    """
    Lädt Daten, erstellt das Diagramm und sendet oder aktualisiert die Nachricht.

    Parameter:
        edit             – True = bestehende Nachricht aktualisieren (Button-Klick)
                           False = neue Nachricht senden (erster Aufruf)
        original_user_id – Discord-ID des Users, der den Befehl ursprünglich
                           ausgeführt hat (für Button-Berechtigungsprüfung)
    """
    # --- Daten aus der Datenbank laden ---
    rows = await db.get_voice_activity(user_id=user.id, days=zeitraum)

    if not rows:
        inhalt = (
            f"📭 Keine Voice-Aktivität für **{user.display_name}** "
            f"in den letzten **{zeitraum} Tagen** gefunden."
        )
        if edit:
            await interaction.response.edit_message(content=inhalt, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(inhalt)
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
        fehler = "❌ Beim Erstellen des Diagramms ist ein Fehler aufgetreten."
        if edit:
            await interaction.response.edit_message(content=fehler, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(fehler)
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

    # --- Buttons für Zeitraum-Auswahl ---
    view = VoiceZeitraumView(user=user, aktueller_zeitraum=zeitraum, original_user_id=original_user_id)

    datei = discord.File(buf, filename="voice_activity.png")

    if edit:
        await interaction.response.edit_message(
            embed       = embed,
            attachments = [datei],
            view        = view,
        )
    else:
        await interaction.followup.send(
            embed = embed,
            file  = datei,
            view  = view,
        )

    print(
        f"📊 /voice: {user.display_name} | {zeitraum} Tage | "
        f"{gesamt_stunden:.1f} h – angefragt von {interaction.user.name}"
    )


# ===========================================================================
# KLASSE: VoiceZeitraumView
# Drei Buttons (30 / 90 / 365 Tage) unterhalb des Diagramms.
# Nur der ursprüngliche Aufrufer darf die Buttons drücken.
# ===========================================================================

class VoiceZeitraumView(discord.ui.View):

    def __init__(self, user: discord.Member, aktueller_zeitraum: int, original_user_id: int):
        super().__init__(timeout=300)   # Buttons nach 5 Minuten deaktivieren
        self.user              = user
        self.aktueller_zeitraum = aktueller_zeitraum
        self.original_user_id  = original_user_id

        # Buttons dynamisch hinzufügen – aktiver Zeitraum wird hervorgehoben
        for tage, label in [(30, "30 Tage"), (90, "90 Tage"), (365, "365 Tage")]:
            button = discord.ui.Button(
                label    = label,
                style    = discord.ButtonStyle.primary if tage == aktueller_zeitraum
                           else discord.ButtonStyle.secondary,
                custom_id = f"voice_{tage}",
                disabled  = (tage == aktueller_zeitraum),  # Aktiven Button deaktivieren
            )
            button.callback = self._erstelle_callback(tage)
            self.add_item(button)

    def _erstelle_callback(self, tage: int):
        async def callback(interaction: discord.Interaction):
            # Alle erlaubten Rollen dürfen Buttons drücken
            hat_berechtigung = any(
                rolle.id in ERLAUBTE_ROLLEN_IDS
                for rolle in interaction.user.roles
            )
            if not hat_berechtigung:
                await interaction.response.send_message(
                    "❌ Du hast keine Berechtigung, den Zeitraum zu wechseln.",
                    ephemeral=True,
                )
                return

            await _sende_voice_nachricht(
                interaction      = interaction,
                user             = self.user,
                zeitraum         = tage,
                original_user_id = self.original_user_id,
                edit             = True,
            )
        return callback

    async def on_timeout(self):
        # Alle Buttons nach Timeout deaktivieren
        for item in self.children:
            item.disabled = True


# ===========================================================================
# FUNKTION: register_voice_command
# Registriert den /voice Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Moderator tippt /voice @user
#   2. Bot prüft Berechtigung
#   3. Bot lädt Voice-Daten für 30 Tage aus der Datenbank
#   4. Bot erstellt ein Liniendiagramm mit Zeitraum-Buttons und sendet es
#   5. Klick auf einen Button aktualisiert das Diagramm für den neuen Zeitraum
# ===========================================================================

def register_voice_command(tree: app_commands.CommandTree):

    @tree.command(
        name="voice",
        description="Voice-Aktivität eines Users als Diagramm anzeigen",
    )
    @app_commands.describe(
        user = "Der User, dessen Voice-Aktivität angezeigt werden soll",
    )
    async def voice_command(
        interaction: discord.Interaction,
        user:        discord.Member,
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

        # Antwort verzögern, da Datenbankabfrage + Bildgenerierung Zeit braucht
        await interaction.response.defer(ephemeral=False)

        await _sende_voice_nachricht(
            interaction      = interaction,
            user             = user,
            zeitraum         = 30,
            original_user_id = interaction.user.id,
            edit             = False,
        )
