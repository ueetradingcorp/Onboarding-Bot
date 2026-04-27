# UEE Trading Corp - Discord Onboarding Bot

Discord Bot für automatisches Onboarding und Mitgliederverwaltung in der UEE Trading Corp Star Citizen Community.

## Features

### 🎯 Automatisches Onboarding
- Sendet automatisch eine Willkommensnachricht per DM, wenn neue Mitglieder die "Interessent"-Rolle erhalten
- Übersicht über alle wichtigen Kanäle und Bereiche des Servers

### 📋 `/neu` Befehl - Mitglied aufnehmen
- **Autocomplete User-Auswahl:** Verhindert Tippfehler bei der Userauswahl
- **RSI-Profil-Integration:** Unterstützt sowohl direkte Handles als auch RSI-Profil-Links
  - Direkt: `StarPilot42`
  - URL: `https://robertsspaceindustries.com/citizens/StarPilot42`
- **Automatische Validierung:** Prüft Handle über die Star Citizen API (optional)
- **Rollen-Management:** Weist automatisch "Interessent" oder "Freund"-Rolle zu
- **Nickname-Verwaltung:** Setzt Nickname im Format `SC-Handle | Rufname`
- **Personalakten-Forum:** Erstellt automatisch einen Forum-Post mit allen wichtigen Infos

### 🔒 Berechtigungssystem
Nur folgende Rollen können den `/neu` Befehl ausführen:
- Direktoren
- Moderatoren
- Recruiter

## Installation & Deployment

### Railway (Empfohlen)

1. **Repository forken/klonen**
   ```bash
   git clone https://github.com/Belisarius7487/Onboarding-Bot.git
   cd Onboarding-Bot
   ```

2. **Railway-Projekt erstellen**
   - Gehe zu [railway.app](https://railway.app)
   - Erstelle ein neues Projekt
   - Verbinde dein GitHub-Repository

3. **Environment Variables setzen**
   
   **Erforderlich:**
   - `DISCORD_TOKEN` - Dein Discord Bot Token
   
   **Optional (für RSI-Integration):**
   - `STARCITIZEN_API_KEY` - API-Key von [starcitizen-api.com](https://starcitizen-api.com)
   
   **Automatisch gesetzt:**
   - `PORT` - Wird von Railway automatisch gesetzt (Standard: 8000)

4. **Deploy**
   - Railway deployt automatisch bei jedem Push

### Lokale Entwicklung

1. **Python 3.8+ installieren**

2. **Dependencies installieren**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Variables setzen**
   ```bash
   export DISCORD_TOKEN="dein-discord-bot-token"
   export STARCITIZEN_API_KEY="dein-api-key"  # Optional
   export PORT=8000
   ```

4. **Bot starten**
   ```bash
   python bot.py
   ```

## Discord Bot Setup

1. **Bot erstellen**
   - Gehe zu [Discord Developer Portal](https://discord.com/developers/applications)
   - Erstelle eine neue Application
   - Gehe zu "Bot" → "Add Bot"
   - Kopiere den Bot Token

2. **Bot-Berechtigungen**
   
   **Erforderliche Intents:**
   - ✅ Server Members Intent (für Onboarding & User-Autocomplete)
   - ✅ Message Content Intent (optional)
   
   **Erforderliche Permissions:**
   - ✅ Manage Roles (Rollen zuweisen/entfernen)
   - ✅ Manage Nicknames (Nickname setzen)
   - ✅ Send Messages in Threads (Forum-Posts erstellen)
   - ✅ Create Forum Posts
   - ✅ Send Messages (für DMs)

3. **Bot zum Server hinzufügen**
   - OAuth2 → URL Generator
   - Scopes: `bot`, `applications.commands`
   - Permissions: Siehe oben
   - Generierte URL im Browser öffnen

## Konfiguration

### Rollen-IDs anpassen (`neu_befehl.py`)

```python
# Rollen, die den /neu Befehl ausführen dürfen
ERLAUBTE_ROLLEN_IDS = [
    920642041959038976,   # Direktoren
    915861683380027432,   # Moderatoren
    1447574324289736717,  # Recruiter
]

# Rollen, die dem neuen User zugewiesen werden
INTERESSENT_ROLLE_ID = 915601784343498793
FREUND_ROLLE_ID      = 966290443090407464

# Rolle, die beim Aufnehmen entfernt wird
GAST_ROLLE_ID        = 915546303113596949

# Personalakten-Forum
FORUM_KANAL_ID = 1046482975879073912
```

### Server-ID anpassen (`bot.py`)

```python
GUILD_ID = 915532597306753044  # Deine Discord-Server-ID
```

### Willkommensnachricht anpassen (`onboarding.py`)

```python
WELCOME_MESSAGE = """**Deine Willkommensnachricht hier**"""
```

## Verwendung

### Für Recruiter

1. **Neues Mitglied aufnehmen:**
   - Befehl: `/neu`
   - User auswählen (mit Autocomplete)
   - Modal ausfüllen:
     - **Star Citizen Handle:** `StarPilot42` oder `https://robertsspaceindustries.com/citizens/StarPilot42`
     - **Rufname:** Wie die Person angesprochen werden soll
     - **Status:** Interessent oder Freund
     - **Notizen:** Infos aus dem Erstgespräch

2. **Was passiert automatisch:**
   - ✅ Rolle wird zugewiesen
   - ✅ Gast-Rolle wird entfernt
   - ✅ Nickname wird gesetzt
   - ✅ Personalakte im Forum wird erstellt
   - ✅ Willkommens-DM wird gesendet (durch Rollen-Trigger)

## Star Citizen API Integration

### Mit API-Key (empfohlen)

**Vorteile:**
- ✅ Validiert, ob das Handle existiert
- ✅ Korrekte Schreibweise wird automatisch übernommen
- ✅ Fehlermeldung bei nicht existierenden Handles

**Setup:**
1. Registriere dich auf [starcitizen-api.com](https://starcitizen-api.com)
2. Kopiere deinen API-Key
3. Setze `STARCITIZEN_API_KEY` als Environment Variable

### Ohne API-Key

Der Bot funktioniert auch ohne API-Key:
- ⚡ Extrahiert Handle aus URL
- ⚠️ Keine Validierung (Tippfehler werden nicht erkannt)

## Projektstruktur

```
Onboarding-Bot/
├── bot.py                 # Hauptdatei - Bot-Einstiegspunkt
├── neu_befehl.py         # /neu Slash-Command & RSI-Integration
├── onboarding.py         # Automatische Willkommens-DMs
├── requirements.txt      # Python Dependencies
├── railway.toml          # Railway Deployment-Config
└── README.md            # Diese Datei
```

## Erweiterung - Neue Befehle hinzufügen

1. **Neue Datei erstellen** (z.B. `sos.py`)
   ```python
   from discord import app_commands
   
   def register_sos_command(tree: app_commands.CommandTree):
       @tree.command(name="sos", description="SOS-Signal senden")
       async def sos_command(interaction):
           # Dein Code hier
           pass
   ```

2. **In `bot.py` importieren**
   ```python
   from sos import register_sos_command
   ```

3. **In `OnboardingBot.__init__` registrieren**
   ```python
   register_sos_command(self.tree)
   ```

## Troubleshooting

### Bot reagiert nicht auf `/neu`
- ✅ Stelle sicher, dass der Bot neu gestartet wurde
- ✅ Prüfe, ob du die richtige Rolle hast
- ✅ Schaue in die Bot-Logs für Fehler

### "Star Citizen Handle nicht gefunden"
- ✅ Prüfe die Schreibweise
- ✅ Stelle sicher, dass das RSI-Profil öffentlich ist
- ✅ Versuche die direkte Handle-Eingabe statt URL

### "API-Timeout"
- ✅ Star Citizen API könnte langsam sein
- ✅ Bot verwendet dann Handle ungeprüft
- ✅ Kein kritischer Fehler

### Keine Willkommens-DM
- ✅ User hat DMs von Server-Mitgliedern deaktiviert
- ✅ Check Bot-Logs für "Forbidden" Fehler
- ✅ Dies ist normal und kein Bot-Fehler

## Health Check

Der Bot läuft einen internen HTTP-Server auf dem konfigurierten Port (Standard: 8000) für Health Checks:
- Endpoint: `http://localhost:8000/`
- Response: `200 OK`

Nützlich für UptimeRobot oder ähnliche Monitoring-Tools.

## Support & Entwicklung

- **Issues:** [GitHub Issues](https://github.com/Belisarius7487/Onboarding-Bot/issues)
- **Entwickler:** Belisarius7487
- **Organisation:** UEE Trading Corp

## Lizenz

Dieses Projekt ist für den internen Gebrauch der UEE Trading Corp gedacht.

---

**Star Citizen®** und **Roberts Space Industries®** sind eingetragene Marken der Cloud Imperium Rights LLC.
Dieser Bot ist ein Fan-Projekt und nicht mit Cloud Imperium Games verbunden.
