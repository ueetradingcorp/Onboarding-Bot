import io
import math
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

def _füge_wasserzeichen_ein(fig):
    logo_pfad = Path(__file__).parent / "logo_transparent.png"
    if not logo_pfad.exists():
        return
    try:
        import numpy as np
        from PIL import Image
        logo = mpimg.imread(str(logo_pfad))
        fig_breite = fig.get_figwidth()  * fig.dpi
        fig_hoehe  = fig.get_figheight() * fig.dpi
        ziel_hoehe  = int(fig_hoehe * 0.85)
        ziel_breite = ziel_hoehe
        logo_pil = Image.fromarray((logo * 255).astype(np.uint8))
        logo_pil = logo_pil.resize((ziel_breite, ziel_hoehe), Image.LANCZOS)
        logo_skaliert = np.array(logo_pil) / 255.0
        x_pos = int((fig_breite  - ziel_breite) / 2)
        y_pos = int((fig_hoehe   - ziel_hoehe)  / 2)
        fig.figimage(logo_skaliert, xo=x_pos, yo=y_pos, alpha=0.08, zorder=0)
    except Exception as e:
        print(f"⚠️ Wasserzeichen konnte nicht geladen werden: {e}")


# ===========================================================================
# HILFSFUNKTION: Diagramm erstellen
# ===========================================================================

def _erstelle_voice_chart(username: str, days: int, rows: list) -> io.BytesIO:
    tages_daten: dict = {}
    for row in rows:
        tag = row["start_time"].astimezone(timezone.utc).date()
        tages_daten[tag] = tages_daten.get(tag, 0.0) + (row["duration_minutes"] or 0.0)

    heute     = datetime.now(timezone.utc).date()
    startdag  = heute - timedelta(days=days - 1)
    alle_tage = [startdag + timedelta(days=i) for i in range(days)]
    werte     = [tages_daten.get(tag, 0.0) for tag in alle_tage]

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#2b2d31")
    ax.set_facecolor("#313338")

    ax.plot(alle_tage, werte, color="#5865f2", linewidth=2,
            marker="o", markersize=3, label="Sprachminuten")
    ax.fill_between(alle_tage, werte, alpha=0.15, color="#5865f2")

    ax.set_title(f"Voice-Aktivität – {username}  ({days} Tage)",
                 color="white", fontsize=14, pad=12)
    ax.set_xlabel("Datum",   color="#b5bac1", fontsize=10)
    ax.set_ylabel("Minuten", color="#b5bac1", fontsize=10)
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
    ax.legend(
        facecolor="#313338", labelcolor="white", framealpha=0.8,
        loc="lower left", bbox_to_anchor=(0, 1.02, 1, 0.08),
        borderaxespad=0, mode="expand", ncol=1,
    )
    ax.grid(axis="y", color="#4e5058", linestyle="--", linewidth=0.6, alpha=0.7)

    y_max = max(max(werte), 1.0)
    ax.set_ylim(0, math.ceil(y_max * 1.1))
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

    plt.tight_layout()
    _füge_wasserzeichen_ein(fig)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor(),
                bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ===========================================================================
# HILFSFUNKTION: Nachricht senden oder aktualisieren
# ===========================================================================

async def _sende_voice_nachricht(
    interaction: discord.Interaction,
    user: discord.Member,
    zeitraum: int,
    edit: bool = False,
):
    rows = await db.get_voice_activity(user_id=user.id, days=zeitraum)

    if not rows:
        inhalt = (
            f"📭 Keine Voice-Aktivität für **{user.display_name}** "
            f"in den letzten **{zeitraum} Tagen** gefunden."
        )
        if edit:
            await interaction.response.edit_message(
                content=inhalt, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(inhalt)
        return

    gesamt_minuten = sum(r["duration_minutes"] or 0.0 for r in rows)
    gesamt_stunden = gesamt_minuten / 60.0
    gesamt_sekunden = gesamt_minuten * 60.0

    if gesamt_minuten < 1.0:
        dauer_anzeige = f"**{gesamt_sekunden:.0f} Sekunden**"
    elif gesamt_stunden < 1.0:
        dauer_anzeige = f"**{gesamt_minuten:.1f} Minuten**"
    else:
        verbleibende_minuten = gesamt_minuten % 60
        dauer_anzeige = (
            f"**{gesamt_stunden:.0f} Std. {verbleibende_minuten:.0f} Min.**"
            f" ({gesamt_minuten:.0f} Minuten gesamt)"
        )

    try:
        buf = _erstelle_voice_chart(
            username=user.display_name, days=zeitraum, rows=rows)
    except Exception as exc:
        print(f"❌ Fehler beim Erstellen des Voice-Diagramms: {exc}")
        fehler = "❌ Beim Erstellen des Diagramms ist ein Fehler aufgetreten."
        if edit:
            await interaction.response.edit_message(
                content=fehler, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(fehler)
        return

    embed = discord.Embed(
        title       = f"🎙️  Voice-Aktivität – {user.display_name}",
        description = (
            f"Zeitraum: **{zeitraum} Tage**\n"
            f"Gesamt: {dauer_anzeige}"
        ),
        colour    = discord.Colour.blurple(),
        timestamp = discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_image(url="attachment://voice_activity.png")
    embed.set_footer(text=f"Angefragt von {interaction.user.display_name}")

    # user_id wird in der custom_id gespeichert → überlebt Bot-Neustarts
    view  = VoiceZeitraumView(user_id=user.id, aktueller_zeitraum=zeitraum)
    datei = discord.File(buf, filename="voice_activity.png")

    if edit:
        await interaction.response.edit_message(
            embed=embed, attachments=[datei], view=view)
    else:
        await interaction.followup.send(embed=embed, file=datei, view=view)

    print(
        f"📊 /voice: {user.display_name} | {zeitraum} Tage | "
        f"{gesamt_stunden:.1f} h – angefragt von {interaction.user.name}"
    )


# ===========================================================================
# KLASSE: VoiceZeitraumView  (Persistent View – kein Timeout)
#
# Die user_id wird direkt in der custom_id gespeichert:
#   Format: "voice_<tage>_<user_id>"
# So kennt der Bot nach einem Neustart den Ziel-User ohne extra Speicher.
# ===========================================================================

class VoiceZeitraumView(discord.ui.View):

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
                custom_id = f"voice_{tage}_{user_id}",  # user_id steckt in der ID
                disabled  = (tage == aktueller_zeitraum),
            )
            button.callback = self._erstelle_callback(tage)
            self.add_item(button)

    def _erstelle_callback(self, tage: int):
        async def callback(interaction: discord.Interaction):
            # Berechtigungsprüfung
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

            await _sende_voice_nachricht(
                interaction=interaction,
                user=user,
                zeitraum=tage,
                edit=True,
            )
        return callback


# ===========================================================================
# FUNKTION: register_voice_command
# ===========================================================================

def register_voice_command(tree: app_commands.CommandTree):

    @tree.command(
        name="voice",
        description="Voice-Aktivität eines Users als Diagramm anzeigen",
    )
    @app_commands.describe(
        user="Der User, dessen Voice-Aktivität angezeigt werden soll",
    )
    async def voice_command(interaction: discord.Interaction, user: discord.Member):
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

        await interaction.response.defer(ephemeral=False)
        await _sende_voice_nachricht(
            interaction=interaction,
            user=user,
            zeitraum=30,
            edit=False,
        )
