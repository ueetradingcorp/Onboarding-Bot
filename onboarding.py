import discord
import asyncio


# Willkommensnachricht, die per DM gesendet wird
WELCOME_MESSAGE = """**Kanäle zu denen du nun Zugang hast:**

**Regelwerk & Kontakt**
Enthält unser erweitertes Regelwerk und
- <#986694012738109550> Unser Ticketsystem zur Kontaktaufnahme mit der Leitung

**Infos & Einstellungen**
- <#1360388334739918989> Dient zur Benachrichtigung aller Mitglieder zu Orga- oder Spielneuigkeiten
- <#1374030788709843024> Hier werden Eventankündigungen gepostet
- <#1374051098687442955> Hier posten wir Umfragen
- <#1227946509526368286> Enthält diverse Hilfestellungen zur UEETC, dem Spectrum und dem Discord

**Chat & Foren**
- <#920025294604222584> Allgemeiner Chatkanal für alle (bitte keine Spoiler)
- <#1381728524859080805> Für akute Notfälle im Verse kann man hier via Bot-Befehl ein SOS-Signal an die UEETC senden
- <#1239307522855145623> Leaks-Kanal zu Star Citizen (bitte für Spoiler nutzen)
- <#1269578675033079850> Allgemeiner Laberkanal

**dynamische Sprachkanäle**
- <#966305727784304690> Enthält alle Botbefehle der Sprachkanäle
- <#1416511439321038859> Bei Klick öffnet der Bot automatisch einen neuen Sprachkanal & schiebt dich hinein
- <#1077845742229659719> Öffnet einen Push-to-Talk Sprachkanal
- <#1403269417520857240> Sprachkanal für Twitch/YouTube-Streamer (Wer da drin ist, streamt wahrscheinlich gerade)
- <#1491149696901713950> Wartebereich für einen Livestream
- <#1491470812257976460> Event-Sprachkanal

**Interaktive Themen**
- <#915637257103355974> Diverse Fundsachen in Videoform
- <#915636487456952341> Fragen zu Mechaniken in SC
- <#915636737487798272> Allgemeine Hilfen zu SC
- <#915637107282813001> Screenshots gehen hier rein
- <#977633525580828672> Anleitungen zu SC

**Star Citizen Schule**
- <#921369803418107934> Kurse die wir anbieten
- <#1204399162297294869> Info- & Lernmaterialsammlung der SC-Schule
- <#921376033851207741> Hier meldest du dich für unsere Kurse an & vereinbarst Termine mit unseren Ausbildern
- <#921369966937264138> Hierhin zieht dich der Ausbilder, damit ihr ungestört trainieren könnt

**Lost in Space**
- <#915704701767548978> Wenn du AFK gehst, kannst du hier reingehen (kein Zwang)
"""


# ===========================================================================
# KLASSE: OnboardingHandler
# Kümmert sich darum, dass neue Mitglieder mit der "Interessent"-Rolle
# automatisch eine Willkommens-DM mit der Kanalübersicht erhalten.
# ===========================================================================

class OnboardingHandler:

    def __init__(self, rolle_id):
        self.rolle_id = rolle_id  # ID der Interessent-Rolle speichern

    # Prüft, ob die Interessent-Rolle gerade hinzugefügt wurde
    def rolle_wurde_hinzugefuegt(self, before, after):
        rolle = discord.utils.get(after.guild.roles, id=self.rolle_id)
        return rolle is not None and rolle in after.roles and rolle not in before.roles

    # Wird aufgerufen, wenn sich die Rollen eines Mitglieds ändern
    async def on_member_update(self, before, after):
        print("DEBUG: on_member_update wurde ausgelöst")
        print(f"Vorherige Rollen: {[r.id for r in before.roles]}")
        print(f"Nachher Rollen:   {[r.id for r in after.roles]}")

        # Nur weiter, wenn die Interessent-Rolle hinzugekommen ist
        if not self.rolle_wurde_hinzugefuegt(before, after):
            return

        await self.sende_willkommens_dm(after)

    # Sendet die Willkommensnachricht als DM an das Mitglied
    async def sende_willkommens_dm(self, member):
        # Discord erlaubt maximal 2000 Zeichen pro Nachricht → an Absatzgrenzen aufteilen
        teile = []
        absaetze = WELCOME_MESSAGE.split('\n\n')
        aktuelle_nachricht = ""

        for absatz in absaetze:
            # Wenn der aktuelle Absatz + neuer Absatz unter 2000 Zeichen bleibt, hinzufügen
            if len(aktuelle_nachricht) + len(absatz) + 2 <= 2000:  # +2 für "\n\n"
                if aktuelle_nachricht:
                    aktuelle_nachricht += "\n\n"
                aktuelle_nachricht += absatz
            else:
                # Wenn zu lang, aktuelle Nachricht speichern und neue starten
                if aktuelle_nachricht:
                    teile.append(aktuelle_nachricht)
                aktuelle_nachricht = absatz

        # Letzte Nachricht nicht vergessen
        if aktuelle_nachricht:
            teile.append(aktuelle_nachricht)

        try:
            for teil in teile:
                await member.send(teil)
                await asyncio.sleep(1)  # Kurz warten, damit Discord nicht blockt
            print(f"✅ DM erfolgreich an {member.name} gesendet.")

        except discord.Forbidden:
            print(f"❌ Konnte DM an {member.name} nicht senden (Privatsphäre-Einstellungen).")

        except discord.HTTPException as e:
            print(f"❌ Fehler beim Senden der DM an {member.name}: {e}")
