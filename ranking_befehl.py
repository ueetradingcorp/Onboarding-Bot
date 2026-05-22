import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

import discord
from discord import app_commands
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

from database import db


# ===========================================================================
# KONFIGURATION
# ===========================================================================

ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]

TOP_N = 10  # Anzahl der angezeigten Plätze


# ===========================================================================
# HILFSFUNKTION: Avatar herunterladen und kreisförmig zuschneiden
# ===========================================================================

async def _lade_avatar(avatar_url: str):
    try:
        import aiohttp
        import numpy as np
        from PIL import Image, ImageDraw

        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status != 200:
                    return None
                daten = await resp.read()

        img = Image.open(io.BytesIO(daten)).convert("RGBA").resize((128, 128), Image.LANCZOS)

        maske = Image.new("L", (128, 128), 0)
        draw  = ImageDraw.Draw(maske)
        draw.ellipse((0, 0, 128, 128), fill=255)
        img.putalpha(maske)

        return np.array(img) / 255.0
    except Exception as e:
        print(f"⚠️ Avatar konnte nicht geladen werden: {e}")
        return None


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

        fig_breite_px = int(fig.get_figwidth() * fig.dpi)
        fig_hoehe_px  = int(fig.get_figheight() * fig.dpi)

        logo_orig      = Image.open(str(logo_pfad)).convert("RGBA")
        orig_w, orig_h = logo_orig.size

        ziel_breite = fig_breite_px
        ziel_hoehe  = int(orig_h * ziel_breite / orig_w)

        logo_skaliert = logo_orig.resize((ziel_breite, ziel_hoehe), Image.LANCZOS)
        logo_arr      = np.array(logo_skaliert) / 255.0

        yo = fig_hoehe_px - ziel_hoehe
        fig.figimage(logo_arr, xo=0, yo=yo, alpha=0.08, zorder=0)
    except Exception as e:
        print(f"⚠️ Wasserzeichen konnte nicht geladen werden: {e}")


# ===========================================================================
# HILFSFUNKTION: Diagramm erstellen
# ===========================================================================

def _erstelle_ranking_chart(
    days:        int,
    voice_rows:  list,
    chat_rows:   list,
    guild:       discord.Guild,
    voice_avatare: dict,
    chat_avatare:  dict,
) -> io.BytesIO:
    """
    Erstellt zwei horizontale Balkendiagramme übereinander.
    voice_avatare / chat_avatare: {user_id: np.array (RGBA, 128x128)} oder leer.
    """
    import numpy as np

    # ── Daten aufbereiten ────────────────────────────────────────────────
    def _aufbereiten(rows, wert_key, umrechnung=1.0):
        namen, werte, user_ids = [], [], []
        for row in rows[:TOP_N]:
            member = guild.get_member(row["user_id"])
            namen.append(member.display_name if member else f"ID {row['user_id']}")
            werte.append(round((row[wert_key] or 0.0) * umrechnung, 2))
            user_ids.append(row["user_id"])
        # Umkehren: Platz 1 oben
        return namen[::-1], werte[::-1], user_ids[::-1]

    voice_namen, voice_werte, voice_ids = _aufbereiten(
        voice_rows, "gesamt_minuten", 1 / 60.0)
    chat_namen,  chat_werte,  chat_ids  = _aufbereiten(
        chat_rows, "gesamt_nachrichten", 1.0)

    # ── Figure ───────────────────────────────────────────────────────────
    fig, (ax_v, ax_c) = plt.subplots(
        2, 1,
        figsize=(12, max(7, TOP_N * 1.0)),
        facecolor="#2b2d31",
    )
    fig.patch.set_facecolor("#2b2d31")

    def _zeichne_balken(ax, namen, werte, user_ids, avatare, farbe, xlabel, titel):
        ax.set_facecolor("#313338")

        # Y-Achsen-Labels leer lassen – Namen kommen als fig.text neben Avatar
        positionen = list(range(len(namen)))
        bars = ax.barh(positionen, werte, color=farbe, alpha=0.85, height=0.55)

        # Wert rechts am Balken
        for bar, wert in zip(bars, werte):
            label = f"{wert:.1f} h" if farbe == "#5865f2" else f"{int(wert):,}"
            ax.text(
                bar.get_width() + (max(werte) * 0.01 if werte else 0.01),
                bar.get_y() + bar.get_height() / 2,
                label,
                va="center", ha="left", color="white", fontsize=9,
            )

        ax.set_title(titel, color="white", fontsize=13, pad=8)
        ax.set_xlabel(xlabel, color="#b5bac1", fontsize=10)
        ax.set_yticks(positionen)
        ax.set_yticklabels([""] * len(namen))  # leere Labels, Avatar + Name kommen separat

        # Rahmen: nur unten und rechts sichtbar, links weg
        for spine in ax.spines.values():
            spine.set_color("#4e5058")
        ax.spines["left"].set_visible(False)

        ax.tick_params(colors="#b5bac1", left=False)
        ax.set_xlim(0, max(werte) * 1.18 if werte else 1)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))
        ax.grid(axis="x", color="#4e5058", linestyle="--", linewidth=0.6, alpha=0.7)
        ax.set_ylim(-0.5, len(namen) - 0.5)

        # Avatare + Namen links neben den Balken
        # Nach tight_layout werden die Axes-Koordinaten in Figure-Koordinaten umgerechnet
        fig.canvas.draw()
        renderer  = fig.canvas.get_renderer()
        ax_bbox   = ax.get_window_extent(renderer=renderer)
        fig_h_px  = fig.get_figheight() * fig.dpi
        fig_w_px  = fig.get_figwidth()  * fig.dpi

        # Höhe einer Zeile in Figure-Koordinaten
        if len(namen) > 1:
            y0_px = ax.transData.transform((0, positionen[0]))[1]
            y1_px = ax.transData.transform((0, positionen[1]))[1]
            zeilen_hoehe_px = abs(y1_px - y0_px)
        else:
            zeilen_hoehe_px = ax_bbox.height / max(len(namen), 1)

        avatar_groesse = min(int(zeilen_hoehe_px * 0.75), 36)  # max 36px

        for i, (uid, name) in enumerate(zip(user_ids, namen)):
            # Y-Mitte dieser Zeile in Pixel (von unten)
            y_px = ax.transData.transform((0, positionen[i]))[1]

            # Avatar zeichnen
            if uid in avatare and avatare[uid] is not None:
                avatar_arr = avatare[uid]
                # Auf Zielgröße skalieren
                from PIL import Image
                pil = Image.fromarray((avatar_arr * 255).astype(np.uint8))
                pil = pil.resize((avatar_groesse, avatar_groesse), Image.LANCZOS)
                avatar_klein = np.array(pil) / 255.0

                x_avatar = ax_bbox.x0 - avatar_groesse - 4
                y_avatar = y_px - avatar_groesse / 2
                fig.figimage(avatar_klein, xo=int(x_avatar), yo=int(y_avatar),
                             zorder=5)

                # Name rechts vom Avatar
                x_name_px  = ax_bbox.x0 - 2
                y_name_frac = y_px / fig_h_px
                x_name_frac = x_name_px / fig_w_px
            else:
                # Kein Avatar – nur Name
                x_name_frac = (ax_bbox.x0 - 4) / fig_w_px
                y_name_frac = y_px / fig_h_px

            fig.text(
                x_name_frac, y_name_frac, name,
                color="#b5bac1", fontsize=9,
                va="center", ha="right",
            )

    _zeichne_balken(ax_v, voice_namen, voice_werte, voice_ids, voice_avatare,
                    "#5865f2", "Stunden",
                    f"🎙️  Voice-Ranking  –  letzte {days} Tage")
    _zeichne_balken(ax_c, chat_namen,  chat_werte,  chat_ids,  chat_avatare,
                    "#57f287", "Nachrichten",
                    f"💬  Chat-Ranking  –  letzte {days} Tage")

    plt.tight_layout(rect=[0.12, 0, 1, 0.97])
    _füge_wasserzeichen_ein(fig)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120,
                facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ===========================================================================
# HILFSFUNKTION: Nachricht senden oder aktualisieren
# ===========================================================================

async def _sende_ranking_nachricht(
    interaction: discord.Interaction,
    zeitraum:   int,
    edit:       bool = False,
):
    guild      = interaction.guild
    voice_rows = await db.get_voice_ranking(days=zeitraum, limit=TOP_N)
    chat_rows  = await db.get_chat_ranking(days=zeitraum,  limit=TOP_N)

    if not voice_rows and not chat_rows:
        inhalt = (
            f"📭 Noch keine Aktivitätsdaten für die letzten **{zeitraum} Tage** vorhanden."
        )
        if edit:
            await interaction.response.edit_message(
                content=inhalt, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(inhalt)
        return

    # Avatare für alle User vorab laden (parallel wäre ideal,
    # sequentiell ist aber einfacher und bei 10-20 Usern schnell genug)
    async def _avatare_laden(rows, id_key="user_id"):
        avatare = {}
        for row in rows:
            uid    = row[id_key]
            member = guild.get_member(uid)
            if member and uid not in avatare:
                avatare[uid] = await _lade_avatar(str(member.display_avatar.url))
        return avatare

    voice_avatare = await _avatare_laden(voice_rows)
    chat_avatare  = await _avatare_laden(chat_rows)

    try:
        buf = _erstelle_ranking_chart(
            days=zeitraum,
            voice_rows=voice_rows,
            chat_rows=chat_rows,
            guild=guild,
            voice_avatare=voice_avatare,
            chat_avatare=chat_avatare,
        )
    except Exception as exc:
        print(f"❌ Fehler beim Erstellen des Ranking-Diagramms: {exc}")
        fehler = "❌ Beim Erstellen des Diagramms ist ein Fehler aufgetreten."
        if edit:
            await interaction.response.edit_message(
                content=fehler, embed=None, attachments=[], view=None)
        else:
            await interaction.followup.send(fehler)
        return

    embed = discord.Embed(
        title       = f"🏆  Aktivitäts-Ranking  –  Top {TOP_N}",
        description = f"Zeitraum: **{zeitraum} Tage**",
        colour      = discord.Colour.gold(),
        timestamp   = discord.utils.utcnow(),
    )
    embed.set_image(url="attachment://ranking.png")
    embed.set_footer(text=f"Angefragt von {interaction.user.display_name}")

    view  = RankingZeitraumView(aktueller_zeitraum=zeitraum)
    datei = discord.File(buf, filename="ranking.png")

    if edit:
        await interaction.response.edit_message(
            embed=embed, attachments=[datei], view=view)
    else:
        await interaction.followup.send(embed=embed, file=datei, view=view)

    print(
        f"📊 /ranking | {zeitraum} Tage – angefragt von {interaction.user.name}"
    )


# ===========================================================================
# KLASSE: RankingZeitraumView
# Zeitraum-Buttons + Refresh, neustart-sicher über handle_ranking_button.
# custom_id Format: "ranking_<tage>" oder "ranking_refresh_<tage>"
# ===========================================================================

class RankingZeitraumView(discord.ui.View):

    def __init__(self, aktueller_zeitraum: int):
        super().__init__(timeout=None)
        self.aktueller_zeitraum = aktueller_zeitraum

        for tage, label in [(30, "30 Tage"), (90, "90 Tage"), (365, "365 Tage")]:
            button = discord.ui.Button(
                label     = label,
                style     = (discord.ButtonStyle.primary
                             if tage == aktueller_zeitraum
                             else discord.ButtonStyle.secondary),
                custom_id = f"ranking_{tage}",
                disabled  = (tage == aktueller_zeitraum),
            )
            button.callback = self._erstelle_callback(tage)
            self.add_item(button)

        refresh_button = discord.ui.Button(
            label     = "🔄",
            style     = discord.ButtonStyle.secondary,
            custom_id = f"ranking_refresh_{aktueller_zeitraum}",
        )
        refresh_button.callback = self._erstelle_refresh_callback()
        self.add_item(refresh_button)

    def _erstelle_callback(self, tage: int):
        async def callback(interaction: discord.Interaction):
            if not any(r.id in ERLAUBTE_ROLLEN_IDS for r in interaction.user.roles):
                await interaction.response.send_message(
                    "❌ Du hast keine Berechtigung.", ephemeral=True)
                return
            await _sende_ranking_nachricht(interaction, zeitraum=tage, edit=True)
        return callback

    def _erstelle_refresh_callback(self):
        async def callback(interaction: discord.Interaction):
            if not any(r.id in ERLAUBTE_ROLLEN_IDS for r in interaction.user.roles):
                await interaction.response.send_message(
                    "❌ Du hast keine Berechtigung.", ephemeral=True)
                return
            await _sende_ranking_nachricht(
                interaction, zeitraum=self.aktueller_zeitraum, edit=True)
        return callback


# ===========================================================================
# FUNKTION: handle_ranking_button
# Wird von bot.py's on_interaction für custom_ids mit "ranking_" aufgerufen.
# custom_id Formate:
#   ranking_7            → 7-Tage-Ansicht
#   ranking_30           → 30-Tage-Ansicht
#   ranking_90           → 90-Tage-Ansicht
#   ranking_refresh_<n>  → Aktuellen Zeitraum neu laden
# ===========================================================================

async def handle_ranking_button(interaction: discord.Interaction):
    custom_id = interaction.data["custom_id"]

    if not any(r.id in ERLAUBTE_ROLLEN_IDS for r in interaction.user.roles):
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung.", ephemeral=True)
        return

    teile = custom_id.split("_")  # ["ranking", "30"] oder ["ranking", "refresh", "30"]

    if len(teile) >= 3 and teile[1] == "refresh":
        try:
            zeitraum = int(teile[2])
        except (ValueError, IndexError):
            zeitraum = 30
    else:
        try:
            zeitraum = int(teile[1])
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "❌ Ungültige Button-Daten.", ephemeral=True)
            return

    await _sende_ranking_nachricht(interaction, zeitraum=zeitraum, edit=True)


# ===========================================================================
# FUNKTION: register_ranking_command
# ===========================================================================

def register_ranking_command(tree: app_commands.CommandTree):

    @tree.command(
        name="ranking",
        description="Top-10 der aktivsten Mitglieder in Voice und Chat anzeigen",
    )
    async def ranking_command(interaction: discord.Interaction):
        if not any(r.id in ERLAUBTE_ROLLEN_IDS for r in interaction.user.roles):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung, den Befehl `/ranking` auszuführen.\n"
                "Dieser Befehl ist nur für Moderatoren, Direktoren und Recruiter verfügbar.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False)
        await _sende_ranking_nachricht(interaction, zeitraum=30, edit=False)
