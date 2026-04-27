# 🚀 Railway Deployment Checkliste

## ✅ Vor dem Deployment

### 1. Repository vorbereiten
- [ ] Alle Dateien sind committed
- [ ] `.gitignore` ist vorhanden
- [ ] `requirements.txt` ist aktuell
- [ ] `railway.toml` ist konfiguriert

### 2. Discord Bot Setup
- [ ] Bot im Discord Developer Portal erstellt
- [ ] Bot Token kopiert
- [ ] Server Members Intent aktiviert
- [ ] Bot zum Server hinzugefügt mit korrekten Permissions:
  - [ ] Manage Roles
  - [ ] Manage Nicknames
  - [ ] Send Messages in Threads
  - [ ] Create Forum Posts
  - [ ] Send Messages

### 3. Star Citizen API (Optional)
- [ ] Account auf https://starcitizen-api.com erstellt
- [ ] API-Key kopiert

## 🔧 Railway Setup

### 1. Projekt erstellen
- [ ] Auf https://railway.app einloggen
- [ ] "New Project" klicken
- [ ] "Deploy from GitHub repo" wählen
- [ ] Repository "Onboarding-Bot" auswählen

### 2. Environment Variables setzen

**ERFORDERLICH:**
```
DISCORD_TOKEN = <Dein Discord Bot Token>
```

**OPTIONAL (für RSI-Integration):**
```
STARCITIZEN_API_KEY = <Dein API-Key von starcitizen-api.com>
```

**Hinweis:** `PORT` wird automatisch von Railway gesetzt

### 3. Deployment starten
- [ ] Auf "Deploy" klicken
- [ ] Warten bis Build erfolgreich ist
- [ ] Logs prüfen auf Fehlermeldungen

## 📋 Nach dem Deployment

### 1. Bot-Status prüfen
- [ ] Bot ist online auf Discord (grüner Status)
- [ ] Logs zeigen: "✅ Slash-Commands wurden bei Discord registriert."
- [ ] Logs zeigen: "🔹 Health-Server läuft auf Port XXXX"

### 2. Funktionen testen

**Onboarding testen:**
- [ ] Test-User erstellen
- [ ] "Interessent"-Rolle manuell zuweisen
- [ ] Prüfen ob DM mit Willkommensnachricht ankommt

**/neu Befehl testen:**
- [ ] Mit Recruiter-Account einloggen
- [ ] `/neu` eingeben
- [ ] User per Autocomplete auswählen
- [ ] Modal ausfüllen:
  - [ ] Star Citizen Handle (oder URL) eingeben
  - [ ] Rufname eingeben
  - [ ] Status wählen (Interessent/Freund)
  - [ ] Notizen eingeben
- [ ] Prüfen ob:
  - [ ] Rolle zugewiesen wurde
  - [ ] Gast-Rolle entfernt wurde
  - [ ] Nickname gesetzt wurde
  - [ ] Forum-Post erstellt wurde
  - [ ] Willkommens-DM gesendet wurde

**RSI-Integration testen (falls API-Key gesetzt):**
- [ ] Mit gültigem RSI-Profil-Link testen
- [ ] Mit direktem Handle testen
- [ ] Mit ungültigem Handle testen (sollte Fehlermeldung geben)

### 3. Monitoring einrichten (Optional)

**UptimeRobot:**
- [ ] Account auf https://uptimerobot.com erstellen
- [ ] HTTP(s) Monitor hinzufügen
- [ ] URL: `https://<dein-railway-projekt>.up.railway.app/`
- [ ] Interval: 5 Minuten
- [ ] Alert-Methode wählen (E-Mail/Discord Webhook)

## 🐛 Troubleshooting

### Bot startet nicht
1. Prüfe Railway Logs auf Fehler
2. Stelle sicher, dass `DISCORD_TOKEN` gesetzt ist
3. Prüfe ob `requirements.txt` vollständig ist

### Slash-Commands erscheinen nicht
1. Warte bis zu 1 Stunde (Discord-Cache)
2. Prüfe Logs auf "✅ Slash-Commands wurden bei Discord registriert"
3. Prüfe ob `GUILD_ID` in `bot.py` korrekt ist
4. Kicke & reinvite den Bot

### /neu funktioniert nicht
1. Prüfe ob du eine der erlaubten Rollen hast
2. Prüfe `ERLAUBTE_ROLLEN_IDS` in `neu_befehl.py`
3. Schaue in Railway Logs nach Fehlermeldungen

### Keine Willkommens-DM
1. Normal wenn User DMs deaktiviert hat
2. Prüfe Logs auf "❌ Konnte DM nicht senden"
3. Kein kritischer Fehler

### RSI-Integration funktioniert nicht
1. Prüfe ob `STARCITIZEN_API_KEY` gesetzt ist
2. Teste Handle direkt auf https://starcitizen-api.com
3. Bei Timeout: Bot nutzt Handle trotzdem (unvalidiert)

## 🔄 Updates deployen

Bei jedem Git Push zu GitHub deployt Railway automatisch neu:

```bash
git add .
git commit -m "Beschreibung der Änderung"
git push origin main
```

Railway:
1. Erkennt den Push
2. Buildet neu
3. Startet den Bot neu
4. Logs zeigen den Fortschritt

## 📊 Wichtige Railway-Einstellungen

### Build Command (automatisch)
```
pip install -r requirements.txt
```

### Start Command (aus railway.toml)
```
python bot.py
```

### Restart Policy (aus railway.toml)
```
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

Bei Crash wird der Bot automatisch bis zu 10x neu gestartet.

## ✨ Fertig!

Dein Bot sollte jetzt:
- ✅ 24/7 online sein auf Railway
- ✅ Automatisch Willkommens-DMs senden
- ✅ `/neu` Befehl bereitstellen
- ✅ RSI-Profile integrieren (falls API-Key gesetzt)
- ✅ Bei Crashes automatisch neu starten

---

**Bei Fragen oder Problemen:**
- Schaue in die Railway Logs
- Prüfe die Discord Bot Permissions
- Öffne ein GitHub Issue
