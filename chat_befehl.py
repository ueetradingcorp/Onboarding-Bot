import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

import discord
from discord import app_commands
import matplotlib
matplotlib.use("Agg")  # Kein Display erforderlich (headless)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.image as mpimg

from database import db


# ===========================================================================
# HILFSFUNKTION: Wasserzeichen einfügen
# ===========================================================================

def _füge_wasserzeichen_ein(fig):
    """
    Legt das UEETC-Logo halbtransparent zentriert über die gesamte Figur.
    Verwendet fig.figimage() damit das Logo proportional bleibt.
    Das Logo muss als 'logo_transparent.png' im selben Verzeichnis liegen.
    """
    logo_pfad = Path(__file__).parent / "logo_transparent.png"
    if not logo_pfad.exists():
        return

    try:
        import numpy as np
        from PIL import Image

        logo = mpimg.imread(str(logo_pfad))

        # Figurgröße in Pixeln
        fig_breite = fig.get_figwidth()  * fig.dpi
        fig_hoehe  = fig.get_figheight() * fig.dpi

        # Logo auf 60% der Figurhöhe skalieren (quadratisch, unverzerrt)
        ziel_hoehe  = int(fig_hoehe * 0.6)
        ziel_breite = ziel_hoehe

        logo_pil = Image.fromarray((logo * 255).astype(np.uint8))
        logo_pil = logo_pil.resize((ziel_breite, ziel_hoehe), Image.LANCZOS)
        logo_skaliert = np.array(logo_pil) / 255.0

        # Zentrierte Position
        x_pos = int((fig_breite  - ziel_breite) / 2)
        y_pos = int((fig_hoehe   - ziel_hoehe)  / 2)

        fig.figimage(logo_skaliert, xo=x_pos, yo=y_pos, alpha=0.08, zorder=0)

    except Exception as e:
        print(f"⚠️ Wasserzeichen konnte nicht geladen werden: {e}")


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

    # Wasserzeichen zentriert im Hintergrund (nach tight_layout!)
    _füge_wasserzeichen_ein(fig)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ===========================================================================
# HILFSFUNKTION: Nachricht zusammenbauen und senden/aktualisieren
# ===========================================================================

async def _sende_chat_nachricht(
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
    rows = await db.get_text_activity(user_id=user.id, days=zeitraum)

    if not rows:
        inhalt = (
            f"📭 Keine Chat-Aktivität für **{user.display_name}** "
            f"in den letzten **{zeitraum} Tagen** gefunden."
        )
        if edit:
            await interaction.response.edit_message(content=inhalt, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(inhalt)
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
        fehler = "❌ Beim Erstellen des Diagramms ist ein Fehler aufgetreten."
        if edit:
            await interaction.response.edit_message(content=fehler, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(fehler)
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

    # --- Buttons für Zeitraum-Auswahl ---
    view = ChatZeitraumView(user=user, aktueller_zeitraum=zeitraum, original_user_id=original_user_id)

    datei = discord.File(buf, filename="chat_activity.png")

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
        f"📊 /chat: {user.display_name} | {zeitraum} Tage | "
        f"{gesamt_nachrichten} Nachrichten – angefragt von {interaction.user.name}"
    )


# ===========================================================================
# KLASSE: ChatZeitraumView
# Drei Buttons (30 / 90 / 365 Tage) unterhalb des Diagramms.
# Nur der ursprüngliche Aufrufer darf die Buttons drücken.
# ===========================================================================

class ChatZeitraumView(discord.ui.View):

    def __init__(self, user: discord.Member, aktueller_zeitraum: int, original_user_id: int):
        super().__init__(timeout=300)   # Buttons nach 5 Minuten deaktivieren
        self.user               = user
        self.aktueller_zeitraum = aktueller_zeitraum
        self.original_user_id   = original_user_id

        # Buttons dynamisch hinzufügen – aktiver Zeitraum wird hervorgehoben
        for tage, label in [(30, "30 Tage"), (90, "90 Tage"), (365, "365 Tage")]:
            button = discord.ui.Button(
                label     = label,
                style     = discord.ButtonStyle.primary if tage == aktueller_zeitraum
                            else discord.ButtonStyle.secondary,
                custom_id = f"chat_{tage}",
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

            await _sende_chat_nachricht(
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
# FUNKTION: register_chat_command
# Registriert den /chat Slash-Command am CommandTree des Bots.
# Wird einmalig in bot.py aufgerufen.
#
# Ablauf:
#   1. Moderator tippt /chat @user
#   2. Bot prüft Berechtigung
#   3. Bot lädt Chat-Daten für 30 Tage aus der Datenbank
#   4. Bot erstellt ein Balkendiagramm mit Zeitraum-Buttons und sendet es
#   5. Klick auf einen Button aktualisiert das Diagramm für den neuen Zeitraum
# ===========================================================================

def register_chat_command(tree: app_commands.CommandTree):

    @tree.command(
        name="chat",
        description="Chat-Aktivität eines Users als Diagramm anzeigen",
    )
    @app_commands.describe(
        user = "Der User, dessen Chat-Aktivität angezeigt werden soll",
    )
    async def chat_command(
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
                "❌ Du hast keine Berechtigung, den Befehl `/chat` auszuführen.\n"
                "Dieser Befehl ist nur für Moderatoren, Direktoren und Recruiter verfügbar.",
                ephemeral=True,
            )
            return

        # Antwort verzögern, da Datenbankabfrage + Bildgenerierung Zeit braucht
        await interaction.response.defer(ephemeral=False)

        await _sende_chat_nachricht(
            interaction      = interaction,
            user             = user,
            zeitraum         = 30,
            original_user_id = interaction.user.id,
            edit             = False,
        )
