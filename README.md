# Clip2Short

Windows-Hintergrunddienst für **neue Twitch-Clips → Hochkantvideo → Untertitel → KI-Titel → TikTok**, mit Lumia Stream als Ereignisquelle und Upload-Anbindung.

[![Tests](https://github.com/Timur18o4/Clip2Short/actions/workflows/tests.yml/badge.svg)](https://github.com/Timur18o4/Clip2Short/actions/workflows/tests.yml)

**v1.0.0 · erste reguläre Veröffentlichung.** Neue Installationen benötigen keinen zusätzlichen Lumia-Befehl. Ersteinrichtung und Ausschnitteditor laufen im Browser auf dem eigenen PC.


Für den Betrieb ohne Lumia unter **Einrichtung & KI-Auswahl** die Clip-Quelle **Direkt über Twitch** wählen. Twitch-Kanal, Client-ID und Client-Secret einer eigenen [Twitch-App](https://dev.twitch.tv/console/apps) eingeben. Die Zugangsdaten werden lokal verschlüsselt gespeichert. Für Titel stehen der Originaltitel und Ollama zur Wahl. Bei einer bestehenden Installation Clip2Short nach dem Speichern einmal neu starten. Die direkte Erkennung berücksichtigt neue Clips ab ihrer Aktivierung und fragt Twitch alle 30 Sekunden ab. Fertige MP4s lassen sich über **TikTok-Upload vorbereiten** in TikTok Studio weiterverwenden.

## Funktionen

- Erkennt neue Twitch-Clip-Ereignisse aus Lumia. Nur Clips nach der ersten Aktivierung; bekannte IDs und Replays werden ignoriert.
- Prüft die exakte öffentliche Twitch-Clip-ID, Kanal, Datum und Kategorie über yt-dlp. Kein historischer Clip wird ersatzweise verwendet.
- Erstellt Untertitel mit lokalem Faster Whisper und prüft sichtbare Chatnachrichten mit RapidOCR.
- Erzeugt eigene Titel, belegten Chatbezug und Beschreibung über Lumia-KI oder lokales Ollama. Der lokale Weg benötigt kein OpenAI-Konto und keinen OpenAI-API-Schlüssel.
- Erkennt große Kamera, Gameplay und Desktop/Reaction anhand von Stichproben. Bildprofile müssen zu den eigenen OBS-Szenen passen.
- Visueller Editor: Ausschnitte im Original markieren, Zielflächen im Hochkantvideo verschieben und eine echte Render-Vorschau ansehen.
- Drei Vorlagen, Farben, Schriften, Untertitelboxen, eigene Fußzeile und Hintergrundbilder. Die Gestaltung wird auch beim Export verwendet.
- Übergabe fertiger Videos über Lumias Aktionsschnittstelle an TikTok. Eine einmalige Upload-Freigabe verhindert blinde Doppelposts.
- Windows-Autostart, lokale Video-Vorschau und dauerhaft gespeicherte Aufträge.

## Einrichtung auf einem weiteren Windows-PC

1. Das [Windows-Programm-ZIP](https://github.com/Timur18o4/Clip2Short/releases) in einen dauerhaften beschreibbaren Ordner entpacken.
2. `EINRICHTEN.cmd` öffnen und **Einrichten** wählen. Fehlendes Python 3.12 und FFmpeg werden geladen und geprüft. Für lokale Text-KI kann zusätzlich Ollama vorbereitet werden. Mehrere GB freier Speicher und Internet sind erforderlich.
3. Lumia öffnen, eigenes Twitch- und gewünschtes TikTok-Konto verbinden und die lokale API aktivieren. Den eigenen Lumia-API-Token in der Browser-Ersteinrichtung eingeben. Er wird nur lokal gespeichert und mit Windows-DPAPI verschlüsselt.
4. **Lumia verbinden & prüfen** wählen. Clip2Short übernimmt den angemeldeten Twitch-Kanal. Es werden keine Befehle angelegt oder überschrieben; ein Ausweichname ist deshalb nicht nötig.
5. KI auswählen: den Anbieter aus Lumia oder ein lokales Ollama-Modell. Die Oberfläche bietet bei Bedarf den Download von Qwen3 4B an (Modell ca. 2,5 GB).
6. Einen eigenen kurzen Beispielclip laden. Hauptbild und Webcam für die drei Szenen markieren und die Hochkant-Vorschau prüfen. Ein Beispielclip dient nur der Gestaltung und wird dadurch nicht veröffentlicht.
7. Design auswählen oder ein eigenes Hintergrundbild laden. Video-Zielflächen und Texte passend platzieren und speichern.
8. Sichtbarkeit und automatische TikTok-Übergabe bewusst auswählen. Die Ersteinrichtung beginnt ohne automatische Übergabe; fertige Videos können zunächst lokal geprüft und gespeichert werden.
9. Einrichtung abschließen. Optional richtet der Assistent den Windows-Autostart ein. Danach mit einem **neu erstellten** Twitch-Clip testen.

Lumia muss Clip-Ereignisse empfangen können. Der Assistent kann den Twitch-Clip-Alarm aktivieren. Wenn der Nutzer selbst Clips erstellt, darf Lumia diese nicht über **Clips vom Streamer ignorieren** unterdrücken. Je nach Lumia-Einstellung ist zusätzlich Stream-Modus erforderlich. Kontofreigaben bleiben beim Nutzer.

Voraussetzungen: Windows 10/11 x64, Lumia mit `run-actions` und aktivierter lokaler API (Referenzversion 9.3.4). Python, FFmpeg und Modelle sind nicht im kleinen Programm-ZIP enthalten; der Installer beziehungsweise die erste Nutzung lädt sie nach. Eine vollständige Installation auf frisch installiertem Windows ist noch nicht nachgewiesen; siehe [Prüfstand](docs/VALIDATION.md).

## Bedienung

| Datei oder Adresse | Zweck |
|---|---|
| `EINRICHTEN.cmd` | Grafischer Komponenten-Installer und Browser-Ersteinrichtung |
| `STARTEN.cmd` / `STOPPEN.cmd` | Hintergrunddienst starten beziehungsweise beenden |
| `AUTOSTART AN.cmd` / `AUTOSTART AUS.cmd` | Start bei der Windows-Anmeldung verwalten |
| `http://127.0.0.1:39242/` | Status, Sichtbarkeit und fertige Videos |
| `/studio` | Quellausschnitte, Zielflächen und Design |
| `/setup` | Lumia-Verbindung, KI-Auswahl und Ersteinrichtung |

Der Dienst läuft in der angemeldeten Benutzersitzung. Lumia muss ebenfalls laufen. Vorhandene Versionen können ihre bisherige Code-Befehlsbrücke behalten, bis sie unter **Einrichtung & KI-Auswahl** erfolgreich auf den direkten Weg umgestellt werden. Bestehende Befehle bleiben erhalten.

## Eigene Gestaltung

Links zeigt der Editor ein Standbild aus dem Quellclip; der Zeitpunkt ist verschiebbar. Rechtecke markieren Hauptbild und Webcam. Ziehen im Rechteck verschiebt es, Ziehen an den Ecken ändert die Größe, Ziehen außerhalb legt ein neues Rechteck an.

Rechts sind die Zielflächen für das 1080 × 1920-Video auswählbar. Auch Titel, Kategorie, Chat-Zitat, Untertitel und Fußzeile lassen sich platzieren. Videos werden proportional eingepasst. **Vorschau aktualisieren** verwendet denselben Renderer wie der Export. Untertitel dürfen Hauptbild und Webcam nicht überdecken.

Eigene PNG-, JPG- oder WebP-Hintergründe füllen die 9:16-Fläche. Das Bild liegt unter den Videoausschnitten und Texten; transparente Löcher sind nicht nötig. Die Video-Zielflächen werden auf die vorgesehenen Flächen des Designs gelegt. Ein Speichern verändert keine schon gerenderten Videos. Vorhandene persönliche Fußzeilen und Bildprofile bleiben bei einem Programm-Update erhalten.

## Daten und Zugriff

Standard-Datenordner: `%LOCALAPPDATA%\Clip2Short`. `installation.json` merkt sich einen abweichenden Ort; `CLIP2SHORT_CLIP_DATA` kann ihn bei einer vorbereiteten Installation vorgeben.

| Ort | Inhalt |
|---|---|
| `clips/` | Originaldateien neuer Twitch-Clips |
| `renders/` | Fertige MP4s und lokale Varianten |
| `transcripts/`, `reports/` | Untertitelcache und Verarbeitungsberichte |
| `references/` | Lokal ausgewählte Beispielvideos, ausschließlich für den Editor |
| `assets/` | Eigene Hintergrundbilder |
| `jobs.sqlite3` | Aktivierungsdatum, bekannte IDs und Auftragszustände |
| `credentials.dpapi`, `config.json` | Private Zugangsdaten und Einstellungen |
| `.runtime/` im Programmordner | Heruntergeladene Python-/FFmpeg-Laufzeit |
| `.installation/` im Programmordner | Installationsprotokolle |

Originale und Exporte werden nicht automatisch gelöscht. Temporäre Render-/Audioordner werden normalerweise entfernt; nach einem harten Abbruch können Reste bleiben. Ollama verwaltet seine Modelle im eigenen Modellordner.

Die Oberfläche bindet nur an localhost. Schreibzugriffe benötigen einen lokalen Schlüssel. Konto-Tokens, Medien, private Einstellungen und Modelle gehören nicht ins Repository. Der lokale KI-Weg verarbeitet Text lokal; der Lumia-KI-Weg übergibt Text an den in Lumia gewählten Anbieter. Ein zur TikTok-Übergabe ausgewähltes fertiges Video wird an TikTok übertragen.

## Grenzen

- Szenen- und Chat-Erkennung, Transkripte und KI-Texte können Fehler enthalten. Unsichere Bildprofile halten den Clip zur Prüfung an.
- Das Tool verarbeitet den ausgewählten Twitch-Clip, maximal 180 Sekunden; es sucht keine Highlights in ganzen Streams.
- Ohne sicher lesbare Chatnachricht wird kein Chat-Zitat eingeblendet.
- Lokale Text-KI kann auf der CPU deutlich länger brauchen. Ein bestimmtes Qualitätsniveau auf beliebiger Hardware ist nicht zugesichert.
- Öffentliche Clip-Auflösung verwendet den Twitch-Extractor von yt-dlp; Plattformänderungen können Anpassungen verlangen. Ein tatsächlicher Streamtitel ist dabei nicht immer verfügbar; die KI erhält die Clipdaten und Untertitel.
- Die Rückkehr einer Lumia-Uploadaktion ist keine verifizierte TikTok-Publikationsbestätigung. Ungeklärte Uploads werden nicht blind wiederholt.
- Konto-Anmeldungen, API-Freigabe und die Kontrolle der Kameraausschnitte erfordern einmalig den Nutzer.

## Entwicklung und Prüfung

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/lumia_contract.cjs
.\.venv\Scripts\python.exe scripts/check_public_tree.py
.\.venv\Scripts\python.exe scripts/build_release.py
```

Automatische Tests verwenden simulierte Konten und veröffentlichen keine Videos. Für die Verarbeitung wird `requirements.txt` benötigt. Weitere Informationen: [Einrichtung](docs/SETUP.md), [Konfiguration](docs/CONFIGURATION.md), [Architektur](docs/ARCHITECTURE.md), [Prüfstand](docs/VALIDATION.md), [Sicherheit](SECURITY.md), [Änderungen](CHANGELOG.md).

## Lizenz

Derzeit ist keine Nutzungslizenz festgelegt. Abhängigkeiten und Modelle unterliegen ihren jeweiligen Lizenzbedingungen. [GitHubs Hinweise zur Lizenzierung](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

## Grundlagen

- [Lumia: Aktionsschnittstelle](https://dev.lumiastream.com/docs/rest/run-actions)
- [Lumia: Ereignisse](https://dev.lumiastream.com/docs/websockets/listen-to-events)
- [Ollama: Lokale API](https://docs.ollama.com/api/authentication)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper)
- [Portable Python-Laufzeiten](https://github.com/astral-sh/python-build-standalone)
- [FFmpeg-Builds](https://www.gyan.dev/ffmpeg/builds/)
