# Zugangsdaten und Sicherheitsmeldungen

## Nicht veröffentlichen

- Lokale API-Tokens, Twitch-/TikTok-/KI-Zugangsdaten oder Dienstschlüssel.
- `credentials.dpapi`, `installation.json`, lokale `config.json` oder `.env`-Dateien.
- Den Datenordner, Datenbanken, Logs, Clips, Browserprofile oder Modell-Caches.

Auch verschlüsselte Zugangsdaten und lokale Datenbanken bleiben privat. `.gitignore` ist eine zusätzliche Hilfe; vor einer Veröffentlichung ist die tatsächlich vorgesehene Dateiliste zu prüfen. `scripts/check_public_tree.py` kontrolliert die veröffentlichte Dateiauswahl auf Laufzeitdaten und bekannte Schlüssel-Muster. Eine zusätzliche lokale Kontrolle vergleicht die Release-Dateien mit den realen Zugangsdaten der Referenzinstallation, ohne diese auszugeben.

## Laufender Dienst

Die Schnittstellen sind für den eigenen PC gedacht. `127.0.0.1:39242` und Lumias lokale API nicht ins Internet weiterleiten. Die verschlüsselten Zugangsdaten gehören zum Windows-Benutzerkonto. Die native Integration übernimmt keinen Twitch- oder TikTok-Anmeldetoken aus Lumia.

Die KI erhält Textkontext aus Untertiteln und sichtbaren Chatnachrichten. Beim Lumia-Weg wird der Anbieter in Lumia festgelegt; Ollama verarbeitet den Text über eine lokale Adresse. Cloud-Modelle werden dort nicht angeboten. Ein zur TikTok-Übergabe ausgewählter fertiger Clip wird über Lumia an TikTok übertragen. Referenzvideos für den Editor gelangen nicht in die Job-Warteschlange und Hintergrundbilder bleiben im privaten Datenordner.

## Meldungen

Keine echten Schlüssel, Videos oder Datenordner in öffentliche Issues oder Kommentare stellen. Sicherheitslücken können über GitHubs private Sicherheitsmeldung des Repositories gemeldet werden. Normale Fehlerberichte bitte mit einer bereinigten Beschreibung und ohne private Laufzeitdaten erstellen.

Bei versehentlich veröffentlichten Zugangsdaten die betroffenen Schlüssel beim jeweiligen Anbieter ersetzen. Ein Löschen aus der letzten Dateiversion entfernt sie nicht aus bereits bestehenden Git-Kopien.
