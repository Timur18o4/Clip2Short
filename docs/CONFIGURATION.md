# Konfiguration und Speicherorte

`installation.json` im Programmordner zeigt auf den tatsächlichen Datenordner. Diese Datei wird bei der Einrichtung erzeugt und nicht veröffentlicht. Die Standardeinstellungen liegen im Code; die lokalen Einstellungen stehen in `<Datenordner>/config.json`.

Ein kommentierungsfreies Beispiel ohne Zugangsdaten befindet sich unter [examples/config.example.json](../examples/config.example.json). Nicht über eine laufende persönliche Konfiguration kopieren.

## Einstellungen

| Feld | Bedeutung |
|---|---|
| `channel` | Eigener Twitch-Kanal; wird im Browser-Assistenten aus Lumia erkannt |
| `privacy` | `SELF_ONLY` oder `PUBLIC_TO_EVERYONE`; frisch eingerichtet zunächst privat |
| `enabled` | Neue Verarbeitung/Freigaben anhalten beziehungsweise fortsetzen |
| `auto_upload` | Nach erfolgreichem Rendering Lumia zum Upload aufrufen |
| `model` | Whisper-Sprachmodell; Referenzwert `medium` |
| `fps` | Zielbildrate; Referenzwert 60 |
| `brand` | Optionaler eigener Text der Fußzeile; neue Installationen beginnen leer, vorhandene Werte bleiben erhalten |
| `transport` | `native` für direkte Lumia-Aktionen; `command` für die bisherige Code-Befehlsbrücke |
| `ai_provider` | `lumia` oder `ollama` für lokale Text-KI |
| `ollama_url`, `ollama_model` | Lokale Ollama-Adresse und vorhandenes Modell; Cloud-Modelle sind ausgeschlossen |
| `design` | Vorlage, Farben, Schrift, Untertitelbox, verwaltetes Hintergrundbild und relative Zielflächen |
| `vision` | Lokales Bildmodell für die Inhaltsklassifikation verwenden |
| `require_face` | Sichere Gesichtserkennung verlangen; in der Referenz aktiv |
| `profiles` | Relative Rechtecke für `camera`, `gameplay` und `reaction` |
| `port`, `lumia_url` | Lokale Adressen; Lumia- und KI-Verbindungen bleiben auf localhost beschränkt |
| `command` | Nur für die ältere Befehlsbrücke relevant; native Installationen benötigen keinen Befehl |

Die normale Bedienung erfolgt im Status. Erweiterte Änderungen an der JSON-Konfiguration bei gestopptem Dienst vornehmen und danach neu starten.

## Bildprofile

Alle Rechtecke enthalten `x`, `y`, `width`, `height` als Werte von 0 bis 1 bezogen auf die Quelle. Im Status werden dieselben Werte in Prozent dargestellt.

- `camera.main`: große Kamera ohne zweite Ansicht.
- `gameplay.main`: Ausschnitt des Spiels; `gameplay.facecam`: Webcam rechts.
- `reaction.main`: vollständiges Desktop-/Videobild; `reaction.facecam`: Webcam rechts.

Die automatische Erkennung wählt ein Profil und kann es innerhalb des Clips wechseln. Sie ermittelt nicht beliebige Webcam-Rahmen millimetergenau aus jeder OBS-Szene. Passt die erkannte Person nicht in das Profil, wird der Clip zur Prüfung angehalten.

Unter `/studio` sind die Quellausschnitte direkt auf einem Standbild auswählbar. `design.targets` enthält getrennte Zielflächen pro Ansicht (`main`, `facecam`, `title`, `caption`, `quote`, `category`, `footer`), relativ zu 1080 × 1920. Vorschau und Export verwenden dieselben Werte. Hintergrundbilder werden über den Editor als verwaltete Dateien geladen, nicht als beliebige Dateipfade.

## Umgebungsvariablen

| Name | Verwendung |
|---|---|
| `CLIP2SHORT_CLIP_DATA` | Datenordner überschreiben; bei Einrichtung wird der Ort in `installation.json` festgehalten |
| `CLIP2SHORT_TWITCH_CHANNEL` | Eigener Kanal für eine vorbereitete Einrichtung; alternativ `setup --channel KANAL` |
| `CLIP2SHORT_LUMIA_TOKEN` | Optionaler Token für eine vorbereitete Einrichtung; bevorzugt verdeckte Eingabe verwenden; niemals in Git committen |
| `CLIP2SHORT_FFMPEG` | Vollständiger Pfad zu `ffmpeg.exe`, falls die automatische Suche nicht passt |
| `CLIP2SHORT_FFPROBE` | Vollständiger Pfad zu `ffprobe.exe` |

## Dateien und Aufbewahrung

| Relativer Pfad im Datenordner | Inhalt | Wird automatisch entfernt? |
|---|---|---|
| `clips/<ID>.part` | Laufender Download | Normalerweise ersetzt beziehungsweise bei Abbruch bereinigt |
| `clips/<ID>.mp4` | Heruntergeladene Originaldatei | Nein |
| `renders/<ID>.mp4` | Fertiger Hochkantclip | Nein |
| `renders/<ID>-preview.mp4` | Lokale KI-Vorschau | Nein; eine neue Vorschau kann diese Variante ersetzen |
| `transcripts/*.clip2short-transcript.json` | Cache der Untertitelseiten | Nein |
| `reports/<ID>.json` | Analyse, Szenen, Untertitel und Gestaltung | Nein |
| `references/` | Lokal ausgewählte Beispielclips und deren Namen; keine Uploadaufträge | Nein |
| `assets/` | Eigene Hintergrundbilder als verwaltete PNG-Dateien | Nein |
| `clip2short-scenes-*/` | Teilvideos und Renderarbeitsdateien; darunter `.clip2short-render-*` | Normalerweise nach Verarbeitung |
| `jobs.sqlite3` | Aktivierungszeitpunkt, bekannte IDs, Zustände und Freigaben | Nein |
| `config.json`, `credentials.dpapi` | Lokale Einstellungen und verschlüsselte Zugangsdaten | Nein |
| `service.log`, `runtime.log` | Betriebsprotokolle | Nein |

Weitere temporäre Dateien befinden sich im Windows-Tempordner: `clip2short-transcribe-*` für Tonspuren, `clip2short-preview-*` für Standbildvorschauen. Nach hartem Prozessabbruch können temporäre Reste bestehen bleiben. Modellgewichte verwenden die Caches der jeweiligen Bibliotheken; sie gehören nicht zum Repository oder Programm-ZIP.

Laufzeitdaten können Transkripte, sichtbare Chattexte, Kontonamen und lokale Dateipfade enthalten. Sie bleiben privat und sind über `.gitignore` sowie die Veröffentlichungskontrolle ausgeschlossen.
