# Einrichtung und Aktualisierung

## Neue Installation

`EINRICHTEN.cmd` öffnet `Installieren.ps1`. Der Installer sucht Python 3.12 und eine vollständige FFmpeg-Installation. Fehlende Laufzeiten werden im Programmordner bereitgestellt: portable Python-Laufzeit von astral-sh/python-build-standalone, geprüft gegen den SHA-256-Digest der Veröffentlichung; FFmpeg vom Build-Anbieter Gyan, geprüft gegen dessen SHA-256-Datei.

Die Bibliotheken werden in einer eigenen `.venv` installiert. Die optionale lokale Text-KI verwendet Ollama. Fehlt es, lädt der Installer den Hersteller-Installer und prüft dessen digitale Signatur. Danach öffnet sich die Browser-Ersteinrichtung. Downloads und Paketinstallation benötigen Internet und mehrere GB freien Speicher.

Die Ersteinrichtung prüft Lumia über eine harmlose Variable und Vorlagenauswertung, erkennt den Twitch-Kanal, speichert den API-Token mit Windows-DPAPI und bietet KI-, Sichtbarkeits-, Design- und Autostart-Auswahl. Ohne fertige Einrichtung wird keine Job-Datenbank mit vorzeitigem Aktivierungsdatum angelegt.

Lumia-Anmeldungen bestätigt der Nutzer. Für selbst erstellte Twitch-Clips darf die Lumia-Option zum Ignorieren von Streamer-Clips nicht aktiv sein. Eine vorhandene fremde Befehlsliste wird nicht verändert: Der native Weg benötigt keinen zusätzlichen Befehl.

## Gestaltung

Unter `/studio` einen Beispielclip laden und die drei eigenen Szenenprofile prüfen. Die Referenz wird nur lokal gespeichert. Quell- und Zielflächen sind getrennt: Das linke Bild definiert, welcher Teil des Originals verwendet wird; das rechte Bild definiert den Platz im Export.

Ein Hintergrundbild füllt die 9:16-Fläche. Videoausschnitte und Texte liegen darüber. Die Auswahl einer Vorlage setzt die Farbfelder, verändert aber nicht automatisch die Quellausschnitte. Erst **Bildprofile & Design speichern** übernimmt Änderungen für neue Exporte. Die Vorschau veröffentlicht nichts.

## Bestehende Installation aktualisieren

1. Laufende Verarbeitung abschließen lassen und `STOPPEN.cmd` ausführen.
2. Private Konfiguration und Job-Datenbank sichern. Vorhandenen Datenordner und `installation.json` behalten.
3. Programmdateien aktualisieren. `.venv`, Laufzeitdaten, Zugangsdaten, Bildprofile und Medien nicht mit Daten einer fremden Installation ersetzen.
4. Bei geänderten Abhängigkeiten `EINRICHTEN.cmd` verwenden. Die grafische Ersteinrichtung regeneriert den lokalen Schlüssel einer bestehenden Installation nicht beiläufig.
5. Unter **Einrichtung & KI-Auswahl** die direkte Lumia-Anbindung prüfen und speichern. Bestehende Installationen ohne `transport`-Eintrag verwenden bis dahin ihre bisherige Befehlsbrücke.
6. Dienst starten. Nach einem Verschieben des Programmordners den Autostart aktualisieren und vorhandene absolute Medienpfade berücksichtigen.

Aktivierungsdatum und bekannte IDs dürfen nicht zurückgesetzt werden. Die Umstellung veröffentlicht keine schon übergebenen Clips erneut. Vorhandene persönliche Gestaltung bleibt erhalten, bis ein neues Design ausdrücklich gespeichert wird.

## Frühere Befehlsbrücke

Für Installationen mit der bisherigen Integration bleibt `lumia/clip2short.js` enthalten. Der gespeicherte `command`-Name wird unverändert verwendet. Diese Variante erfordert den manuell angelegten Code-Befehl und verwendet Lumias KI. Neue Installationen sollten den direkten Weg wählen; er benötigt Lumias Funktion `run-actions`.

## Diagnose

- `Installieren.ps1 -Pruefen` zeigt ohne Installation die gefundene Python-Laufzeit und vorhandene Programmumgebung.
- Der Status bietet **Lumia prüfen**. Erfolgreiche Prüfung beweist den API-Zugriff, keinen fertigen TikTok-Upload.
- Die lokale KI-Auswahl liest Ollama. Cloud-Modelle werden für diesen Weg nicht angeboten.
- Bei unsicherem Bildprofil Quellausschnitte kontrollieren, Vorschau erstellen und danach den betroffenen Clip erneut versuchen.
- Bei ungeklärtem Upload zuerst TikTok prüfen. Die Upload-Sperre verhindert eine blinde Wiederholung.

Protokolle liegen im privaten Datenordner beziehungsweise unter `.installation` im Programmordner. Keine Tokens, Transkripte, privaten Pfade oder vollständigen Datenordner in öffentliche Issues kopieren.
