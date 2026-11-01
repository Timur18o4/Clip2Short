# Zugangsdaten und Sicherheitsmeldungen

## Nicht veröffentlichen

- Lokale API-Tokens, Twitch-/TikTok-/KI-Zugangsdaten oder Dienstschlüssel.
- `credentials.dpapi`, `installation.json`, lokale `config.json` oder `.env`-Dateien.
- Den Datenordner, Datenbanken, Logs, Clips, Browserprofile oder Modell-Caches.

Auch verschlüsselte Zugangsdaten und lokale Datenbanken bleiben privat. `.gitignore` ist eine zusätzliche Hilfe; vor einer Veröffentlichung ist die tatsächlich vorgesehene Dateiliste zu prüfen. `scripts/check_public_tree.py` kontrolliert die veröffentlichte Dateiauswahl auf Laufzeitdaten und bekannte Schlüssel-Muster. Eine zusätzliche lokale Kontrolle vergleicht die Release-Dateien mit den realen Zugangsdaten der Referenzinstallation, ohne diese auszugeben.

## Laufender Dienst

Die Schnittstellen sind für den eigenen PC gedacht. `127.0.0.1:39242` und Lumias lokale API nicht ins Internet weiterleiten. Die verschlüsselten Zugangsdaten gehören zum Windows-Benutzerkonto. Der Twitch-Anmeldetoken wird innerhalb von Lumia verwendet.

Die KI erhält Textkontext aus Untertiteln und sichtbaren Chatnachrichten. Der gewählte KI-Anbieter wird in Lumia festgelegt. Der fertige Clip wird über Lumia an TikTok übertragen.

## Meldungen

Keine echten Schlüssel, Videos oder Datenordner in öffentliche Issues oder Kommentare stellen. Sicherheitslücken können über GitHubs private Sicherheitsmeldung des Repositories gemeldet werden. Normale Fehlerberichte bitte mit einer bereinigten Beschreibung und ohne private Laufzeitdaten erstellen.

Bei versehentlich veröffentlichten Zugangsdaten die betroffenen Schlüssel beim jeweiligen Anbieter ersetzen. Ein Löschen aus der letzten Dateiversion entfernt sie nicht aus bereits bestehenden Git-Kopien.
