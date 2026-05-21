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
# KONFIGURATION – Rollen & Zeitbereiche
# ===========================================================================

ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]


# ===========================================================================
# HILFSFUNKTION: Wasserzeichen einfügen
# ===========================================================================

def _füge_wasserzeichen_ein(fig, ax):
    logo_pfad = Path(__file__).parent / "logo_transparent.png"
    if not logo_pfad.exists():
        return
    try:
        import numpy as np
        from PIL import Image

        # Axes-Position in Pixel berechnen (der eigentliche Diagrammbereich,
        # ohne Achsenbeschriftungen und Ränder)
        fig.canvas.draw()
        bbox = ax.get_window_extent(renderer=fig.canvas.get_renderer())

        ax_breite = bbox.width
        ax_hoehe  = bbox.height
        ax_x0     = bbox.x0
        ax_y0     = bbox.y0

        # Logo auf 75% der Axes-Höhe skalieren (quadratisch)
        ziel_groesse = int(min(ax_breite, ax_hoehe) * 0.75)

        logo = mpimg.imread(str(logo_pfad))
        logo_pil = Image.fromarray((logo * 255).astype(np.uint8))
        logo_pil = logo_pil.resize((ziel_groesse, ziel_groesse), Image.LANCZOS)
        logo_arr = np.array(logo_pil) / 255.0

        # Zentriert im Axes-Bereich platzieren
        x_pos = int(ax_x0 + (ax_breite  - ziel_groesse) / 2)
        y_pos = int(ax_y0 + (ax_hoehe   - ziel_groesse) / 2)

        fig.figimage(logo_arr, xo=x_pos, yo=y_pos, alpha=0.08, zorder=0)
    except Exception as e:
        print(f"⚠️ Wasserzeichen konnte nicht geladen werden: {e}")


# ===========================================================================
# HILFSFUNKTION: Diagramm erstellen
# ===========================================================================

def _erstelle_chat_chart(username: str, days: int, rows: list) -> io.BytesIO:
    tages_daten: dict = {}
    for row in rows:
        tages_daten[row["day"]] = int(row["message_count"])

    heute     = datetime.now(timezone.utc).date()
    startdag  = heute - timedelta(days=days - 1)
    alle_tage = [startdag + timedelta(days=i) for i in range(days)]
    werte     = [tages_daten.get(tag, 0) for tag in alle_tage]

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#2b2d31")
    ax.set_facecolor("#313338")

    balken_breite = max(0.4, 0.8 - days / 500)
    ax.bar(alle_tage, werte, width=balken_breite, color="#57f287",
           alpha=0.85, label="Nachrichten", zorder=2)

    ax.set_title(f"Chat-Aktivität – {username}  ({days} Tage)",
                 color="white", fontsize=14, pad=12)
    ax.set_xlabel("Datum",       color="#b5bac1", fontsize=10)
    ax.set_ylabel("Nachrichten", color="#b5bac1", fontsize=10)
    ax.tick_params(colors="#b5bac1")
    ax.spines[:].set_color("#4e5058")

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

    # Y-Achse: nur ganze Zahlen (Nachrichten können keine Dezimalwerte haben)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    y_max = max(max(werte), 1)
    ax.set_ylim(0, y_max * 1.1)

    plt.tight_layout()
    _füge_wasserzeichen_ein(fig, ax)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ===========================================================================
# HILFSFUNKTION: Nachricht senden oder aktualisieren
# ===========================================================================

async def _sende_chat_nachricht(
    interaction: discord.Interaction,
    user: discord.Member,
    zeitraum: int,
    edit: bool = False,
):
    rows = await db.get_text_activity(user_id=user.id, days=zeitraum)

    if not rows:
        inhalt = (
            f"📭 Keine Chat-Aktivität für **{user.display_name}** "
            f"in den letzten **{zeitraum} Tagen** gefunden."
        )
        if edit:
            await interaction.response.edit_message(
                content=inhalt, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(inhalt)
        return

    gesamt_nachrichten = sum(int(r["message_count"]) for r in rows)
    aktive_tage        = len(rows)

    try:
        buf = _erstelle_chat_chart(
            username=user.display_name, days=zeitraum, rows=rows)
    except Exception as exc:
        print(f"❌ Fehler beim Erstellen des Chat-Diagramms: {exc}")
        fehler = "❌ Beim Erstellen des Diagramms ist ein Fehler aufgetreten."
        if edit:
            await interaction.response.edit_message(
                content=fehler, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(fehler)
        return

    embed = discord.Embed(
        title       = f"💬  Chat-Aktivität – {user.display_name}",
        description = (
            f"Zeitraum: **{zeitraum} Tage**\n"
            f"Gesamt: **{gesamt_nachrichten:,} Nachrichten** "
            f"an **{aktive_tage} aktiven Tagen**"
        ),
        colour    = discord.Colour.green(),
        timestamp = discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_image(url="attachment://chat_activity.png")
    embed.set_footer(text=f"Angefragt von {interaction.user.display_name}")

    # user_id wird in der custom_id gespeichert → überlebt Bot-Neustarts
    view  = ChatZeitraumView(user_id=user.id, aktueller_zeitraum=zeitraum)
    datei = discord.File(buf, filename="chat_activity.png")

    if edit:
        await interaction.response.edit_message(
            embed=embed, attachments=[datei], view=view)
    else:
        await interaction.followup.send(embed=embed, file=datei, view=view)

    print(
        f"📊 /chat: {user.display_name} | {zeitraum} Tage | "
        f"{gesamt_nachrichten} Nachrichten – angefragt von {interaction.user.name}"
    )


# ===========================================================================
# KLASSE: ChatZeitraumView  (Persistent View – kein Timeout)
#
# Die user_id wird direkt in der custom_id gespeichert:
#   Format: "chat_<tage>_<user_id>"
# So kennt der Bot nach einem Neustart den Ziel-User ohne extra Speicher.
# ===========================================================================

class ChatZeitraumView(discord.ui.View):

    def __init__(self, user_id: int, aktueller_zeitraum: int):
        super().__init__(timeout=None)   # Kein Timeout – Buttons bleiben dauerhaft aktiv
        self.user_id            = user_id
        self.aktueller_zeitraum = aktueller_zeitraum

        for tage, label in [(30, "30 Tage"), (90, "90 Tage"), (365, "365 Tage")]:
            button = discord.ui.Button(
                label     = label,
                style     = (discord.ButtonStyle.primary
                             if tage == aktueller_zeitraum
                             else discord.ButtonStyle.secondary),
                custom_id = f"chat_{tage}_{user_id}",  # user_id steckt in der ID
                disabled  = (tage == aktueller_zeitraum),
            )
            button.callback = self._erstelle_callback(tage)
            self.add_item(button)

    def _erstelle_callback(self, tage: int):
        async def callback(interaction: discord.Interaction):
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

            # user_id aus der custom_id auslesen und Member laden
            user_id = self.user_id
            user    = interaction.guild.get_member(user_id)
            if user is None:
                try:
                    user = await interaction.guild.fetch_member(user_id)
                except discord.NotFound:
                    await interaction.response.send_message(
                        "❌ User nicht mehr auf dem Server gefunden.",
                        ephemeral=True,
                    )
                    return

            await _sende_chat_nachricht(
                interaction=interaction,
                user=user,
                zeitraum=tage,
                edit=True,
            )
        return callback


# ===========================================================================
# FUNKTION: register_chat_command
# ===========================================================================

def register_chat_command(tree: app_commands.CommandTree):

    @tree.command(
        name="chat",
        description="Chat-Aktivität eines Users als Diagramm anzeigen",
    )
    @app_commands.describe(
        user="Der User, dessen Chat-Aktivität angezeigt werden soll",
    )
    async def chat_command(interaction: discord.Interaction, user: discord.Member):
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

        await interaction.response.defer(ephemeral=False)
        await _sende_chat_nachricht(
            interaction=interaction,
            user=user,
            zeitraum=30,
            edit=False,
        )


# ===========================================================================
# FUNKTION: handle_chat_button
# Wird von bot.py's on_interaction aufgerufen für alle Button-Klicks deren
# custom_id mit "chat_" beginnt. Parst die custom_id selbst und braucht
# keine View-Instanz – funktioniert damit auch nach Bot-Neustarts für
# beliebig alte Nachrichten.
#
# custom_id Formate:
#   chat_30_<user_id>       → 30-Tage-Ansicht
#   chat_90_<user_id>       → 90-Tage-Ansicht
#   chat_365_<user_id>      → 365-Tage-Ansicht
#   chat_refresh_<user_id>  → Aktuellen Zeitraum neu laden
# ===========================================================================

async def handle_chat_button(interaction: discord.Interaction):
    custom_id = interaction.data["custom_id"]  # z.B. "chat_30_123456789"

    # Berechtigungsprüfung
    hat_berechtigung = any(
        rolle.id in ERLAUBTE_ROLLEN_IDS
        for rolle in interaction.user.roles
    )
    if not hat_berechtigung:
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung, diesen Button zu verwenden.",
            ephemeral=True,
        )
        return

    teile = custom_id.split("_")  # ["chat", "30", "123456789"]
                                   # ["chat", "refresh", "123456789"]

    try:
        user_id = int(teile[-1])
    except (ValueError, IndexError):
        await interaction.response.send_message(
            "❌ Ungültige Button-Daten. Bitte Befehl neu ausführen.",
            ephemeral=True,
        )
        return

    # User laden
    user = interaction.guild.get_member(user_id)
    if user is None:
        try:
            user = await interaction.guild.fetch_member(user_id)
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ User nicht mehr auf dem Server gefunden.",
                ephemeral=True,
            )
            return

    # Zeitraum bestimmen
    aktion = teile[1]  # "30", "90", "365" oder "refresh"

    if aktion == "refresh":
        zeitraum = _zeitraum_aus_embed(interaction)
    else:
        try:
            zeitraum = int(aktion)
        except ValueError:
            await interaction.response.send_message(
                "❌ Unbekannte Aktion. Bitte Befehl neu ausführen.",
                ephemeral=True,
            )
            return

    await _sende_chat_nachricht(
        interaction=interaction,
        user=user,
        zeitraum=zeitraum,
        edit=True,
    )


def _zeitraum_aus_embed(interaction: discord.Interaction) -> int:
    """
    Liest den aktuell angezeigten Zeitraum aus dem Embed der Nachricht,
    auf die der Button-Klick reagiert. Fallback: 30 Tage.
    """
    try:
        nachricht = interaction.message
        if nachricht and nachricht.embeds:
            beschreibung = nachricht.embeds[0].description or ""
            for zeile in beschreibung.splitlines():
                if "Zeitraum" in zeile:
                    for wort in zeile.split():
                        zahl = wort.strip("*").replace("Tage", "").replace("Tage**", "")
                        if zahl.isdigit():
                            return int(zahl)
    except Exception:
        pass
    return 30
