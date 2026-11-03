# Änderungen

## 0.2.0 — 2026-11-03

- Direkte Lumia-Anbindung über `run-actions`: kein zusätzlicher Code-Befehl und keine Befehlsnamenskollision erforderlich. Bestehende Installationen können die bisherige Brücke bis zur geprüften Umstellung behalten.
- Grafischer Installer richtet eine fehlende portable Python-3.12-Laufzeit und FFmpeg mit Prüfsummenprüfung ein; optional wird der signierte Ollama-Installer angeboten.
- Ersteinrichtung im Browser mit Lumia-Prüfung, automatisch erkanntem Twitch-Kanal, KI-Auswahl, Upload-Auswahl und Windows-Autostart.
- Visueller Ausschnitteditor für drei Szenenprofile, Quellbilder und Hochkant-Zielflächen. Referenzclips dienen nur der Gestaltung und gelangen nicht in die Verarbeitungswarteschlange.
- Drei Gestaltungsvorlagen, Farben, Schriften, Untertitelboxen, eigene Fußzeile und eigene Hintergrundbilder. Vorschau und Export verwenden denselben Renderer.
- Lokale Titel- und Beschreibungs-KI über Ollama, mit Modellauswahl und optionalem Download von Qwen3 4B. Kein OpenAI-Konto für diesen Weg erforderlich.
- Neue Installationen übernehmen keine persönliche Website oder Twitch-Voreinstellung. Vorhandene private Einstellungen bleiben erhalten.

## 0.1.1 — 2026-11-01

- Programmoberfläche, Windows-Auftrag, Programmmodule, Lumia-Befehl und interne Variablen heißen jetzt Clip2Short.
- Umgebungsvariablen, Standard-Datenordner, temporäre Dateinamen und Downloadpaket verwenden den neuen Namen.
- Die persönliche Fußzeile `CNG-PLATTFORM.COM / TIMUR18O4` und das Videodesign bleiben erhalten.
- Bei bestehenden Installationen müssen Lumia-Befehl und Autostart gemeinsam mit den Programmdateien umgestellt werden. Datenbank und Zugangsdaten bleiben erhalten; die Einrichtung darf nicht erneut ausgeführt werden.

## 0.1.0 — 2026-11-01

Erste öffentliche Testversion von Clip2Short.

- Neue Twitch-Clips über Lumia-Ereignisse erkennen und nach Datum, Kanal und ID filtern.
- Öffentliche Clipdateien herunterladen; Untertitel, sichtbare Chatnachrichten und Szenen lokal analysieren.
- Eigenen KI-Titel, belegten Chatkontext und TikTok-Beschreibung über Lumia erzeugen.
- Kamera-, Gameplay- und Reaction-Layouts im Clip2Short-Design rendern.
- TikTok-Upload über Lumia mit einmaliger Freigabe und dauerhaftem Zustand.
- Lokaler Status, private Test-Voreinstellung, Bildprofile, Vorschauen und Windows-Autostart.
- Einrichtung fragt den eigenen Twitch-Kanal ab; Startprüfung verwendet den eingerichteten Kanal.
- Bereinigte Veröffentlichung mit Dokumentation, Tests, Beispielen und Prüfung auf versehentliche Laufzeitdaten.

Die Veröffentlichung enthält keine persönlichen Einstellungen, Zugangsdaten oder Medien. Eine Nutzungslizenz wurde noch nicht festgelegt.
