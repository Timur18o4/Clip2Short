# Ausführung und Schnittstellen

## Nativer Ablauf ab Version 0.2.0

1. Lumia liefert neue Twitch-Clip-Ereignisse per WebSocket. Beim Verbinden werden gepufferte Ereignisse gelesen.
2. Der Dienst registriert nur neue, nicht wiederholte IDs nach dem gespeicherten Aktivierungszeitpunkt.
3. yt-dlp löst ausschließlich diese öffentliche Clip-ID auf. Kanal, ID, Datum, Kategorie und Länge werden geprüft. Es gibt keine historische Ersatzsuche.
4. Download nach `clips/`, Transkription, Chat-Texterkennung und Szenenprüfung erfolgen lokal.
5. Text-KI läuft über lokale Ollama-Aufrufe oder Lumias Vorlagenauswertung mit `run-actions / lumia / updateVariable`. Ein eigener gesperrter Variablenplatz wird wiederverwendet. Nach unklarem Timeout wird ein neuer Platz verwendet, damit eine verspätete Antwort keine neue ersetzt.
6. Vorschau und Export teilen Layout, Schrift- und Bildgestaltung. Quellausschnitte sind relativ zum Original, Zielflächen relativ zu 1080 × 1920.
7. Die einmalige Upload-Freigabe prüft Datei, Hash, Sichtbarkeit, Datum und Zustand. Danach verwendet der Dienst `run-actions / tiktok / uploadAndPublishVideo`.
8. Eine abgeschlossene lokale Aktion wird als `submitted`, ein unklarer Ausgang als `uncertain` geführt. Beides wird nicht blind erneut veröffentlicht.

Kein zusätzlicher Lumia-Befehl ist für diesen Weg nötig. Native API-Aufrufe führen keinen benutzerdefinierten JavaScript-Code und keine Shell-Befehle in Lumia aus.

## Ersteinrichtung und Editor

`SetupSession` bietet dieselbe lokale Oberfläche ohne Job-Datenbank, Warteschlange oder Uploadverarbeitung. Erst nach Abschluss startet der eigentliche Dienst. Die Einrichtung nutzt den eigenen lokalen API-Token und speichert ihn mit Windows-DPAPI. Der vorhandene Dienstschlüssel bleibt bei erneuter Konfiguration erhalten.

`/studio` verwaltet Referenzclips, Hintergrundbilder, relative Ausschnitte und Gestaltung. Medien werden nicht in die Job-Warteschlange übernommen. Schreibende Routen und private Medien benötigen einen lokalen UI-/Dienstschlüssel; der Server akzeptiert nur localhost.

## Kompatibilität

Bestehende Konfigurationen ohne `transport` bleiben auf `command`. Die bisherige JS-Brücke übernimmt dann `resolve`, `editorial` und `publish`. Nach erfolgreicher Prüfung kann der Benutzer im Assistenten auf `native` wechseln. Frühere Befehle werden weder gelöscht noch überschrieben.

## Prozesse und Daten

Der Windows-Auftrag startet `pythonw.exe -m clip2short run` im Programmordner. Eine Dateisperre erlaubt nur eine Instanz pro Datenordner. SQLite speichert IDs, Aktivierungsdatum und Zustände. Bei Neustart werden unterbrochene Analyseaufträge wieder aufgenommen; unklare Uploads bleiben gesperrt.

`clip2short/lumia.py` enthält die lokale Lumia-Anbindung; `ai.py` die Text-KI; `wizard.py` die Ersteinrichtung; `studio.py` Medien und Designer; `design.py` validierte Vorlagen. `clip_engine` rendert Vorschau und Video. `Installieren.ps1` verwaltet die benötigten Laufzeiten.
