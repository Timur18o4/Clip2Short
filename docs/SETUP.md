# Einrichtung und Fehlerbehebung

## Datenordner selbst festlegen

Standardmäßig wird der lokale Windows-Anwendungsdatenordner verwendet. Für eine Installation mit allen Laufzeitdaten unter dem Programmordner kann die Einrichtung aus PowerShell erfolgen:

```powershell
Set-Location E:\Scripte\CNG_Clip_Dienst
$env:CNG_CLIP_DATA = Join-Path $PWD 'Daten'
.\EINRICHTEN.cmd
```

Die Einrichtung schreibt den aufgelösten Ort in `installation.json`. Spätere Starts und der Windows-Auftrag lesen diesen Eintrag. Die Datei gehört nicht in GitHub. Vorhandene lokale Datenordner mit Datenbank und Zugangsdaten werden nicht durch das Programm-ZIP ersetzt.

## Lumia-Befehl

Der Name muss exakt `cng-clip-dienst` lauten. Im Codefeld ist der vollständige Inhalt von `lumia/cng-clip-dienst.js` einschließlich `async function() { ... }` erforderlich. Den Befehl nur für den Streamer freigeben und die Warteschlange überspringen lassen. Keine eigene Chatbot-Antwort hinzufügen. Änderungen mit „Ausfüllen und speichern“ und gegebenenfalls „Aktualisierung“ übernehmen.

Die drei normalen Stufen sind:

| Stufe | Arbeit in Lumia |
|---|---|
| `resolve` | Exakte Clip-ID bei Twitch lesen; Kategorie und verfügbaren VOD-Titel auflösen |
| `editorial` | Über `ai_prompt` eigenen Titel und gegebenenfalls eine belegte Chat-ID bestimmen |
| `publish` | Beschreibung und Hashtags erzeugen; einmalige Freigabe beim Dienst holen; TikTok-Aktion ausführen |

Zusätzlich gibt es `check` für die Verbindungsdiagnose. Die Stufen werden vom Dienst übergeben; es müssen keine einzelnen Chat-Befehle dafür angelegt werden.

## Zuerst privat testen

Ein Clip muss **nach der ersten Dienstaktivierung** erstellt worden sein. Ein neu erstellter Clip aus einem älteren VOD ist möglich: Maßgeblich ist das Erstellungsdatum des Clips. Ein bereits vorhandener alter Clip wird nicht zum Test herangezogen.

Nach dem ersten Durchlauf bei TikTok prüfen, ob das Video tatsächlich unter „Nur ich“ vorhanden ist. Danach kann die Sichtbarkeit im Dienst geändert werden. Eine Umstellung betrifft künftig fertiggestellte Clips; sie bearbeitet keine bereits vorhandenen TikTok-Beiträge.

## Häufige Fälle

| Beobachtung | Prüfung |
|---|---|
| Kein Clip erscheint | Lumia läuft, API aktiv, Clip-Alarm aktiv, Stream-Modus passend, „Clips vom Streamer ignorieren“ aus; etwas Verzögerung berücksichtigen |
| Clip wird ausgeschlossen | Kanal und offizielles Erstellungsdatum prüfen; alte/bekannte IDs und Replays sind absichtlich gesperrt |
| Downloadfehler | Öffentliche Abrufbarkeit genau dieses Clips prüfen; gelöschte, private oder gesperrte Clips werden nicht umgangen; Twitch-Downloadänderungen können eine aktualisierte yt-dlp-Version erfordern |
| Bildprofil prüfen | Positionen in Prozent des ursprünglichen Bilds korrigieren; Referenz-Webcam liegt rechts im Bild; danach vor Upload-Freigabe erneut versuchen |
| Kein Chat-Zitat | Nachricht muss lesbar im Bild stehen, einen erkannten Plattformkopf haben und einen klaren Bezug zum Gesprochenen besitzen; ein Zitat ist optional |
| Titelantwort ungültig | Lumia-KI-Anbieter und dessen Antwort prüfen; ohne gültigen eigenen Titel wird nicht mit einem Platzhalter veröffentlicht |
| „An Lumia übergeben“, aber kein Beitrag | Im TikTok-Konto und in Lumia prüfen; der lokale Status beweist nicht die abschließende TikTok-Verarbeitung |
| „Uploadstatus ungeklärt“ | Zuerst TikTok kontrollieren; keine blinde Wiederholung, weil ein Beitrag bereits existieren könnte |
| Modell lädt lange | Erster Start kann Modelle herunterladen; CPU-Verarbeitung und Rendering können mehrere Minuten benötigen |
| FFmpeg fehlt/unvollständig | Vollständige Version installieren; eine eingeschränkte Remotion-Version genügt nicht |

Protokolle liegen im Datenordner. Vor dem Teilen einer Fehlerbeschreibung Kontodaten, Transkripte, lokale Pfade und etwaige vertrauliche Inhalte entfernen. Keine Zugangsdaten oder vollständigen Datenordner in öffentliche Issues hochladen.

## Aktualisieren

1. Laufende Verarbeitung abschließen lassen und `STOPPEN.cmd` ausführen.
2. Datenbank, Zugangsdaten und lokale Konfiguration sichern. Diese Dateien privat behalten.
3. Programmdateien aktualisieren. `Daten`, `installation.json` und bestehende Benutzereinstellungen nicht mit einer fremden Installation ersetzen.
4. Änderungen der Abhängigkeiten in einer passenden Python-Umgebung installieren. Nach einem Verschieben des Programmordners den Autostart am neuen Ort erneut einrichten.
5. Dienst starten und einen neuen Clip zunächst mit kontrollierter Sichtbarkeit testen.

Die erste Version enthält keinen automatischen Programm-Updater. Ein erneutes `EINRICHTEN.cmd` ist eine bewusste Neueinrichtung: Es fragt die Zugangsdaten erneut ab und erzeugt einen neuen lokalen Dienstschlüssel. Den Dienst vorher stoppen.
