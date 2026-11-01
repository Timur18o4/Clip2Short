# Aufrufe und Ausführung

## Prozesse

Die Windows-Aufgabenplanung startet `.venv\Scripts\pythonw.exe -m clip2short run` mit dem Programmordner als Arbeitsverzeichnis. Der Dienst läuft in der angemeldeten Benutzersitzung. Lumia bleibt eine separate Anwendung.

Der Dienst enthält einen Ereignisempfänger, eine lokale Arbeitswarteschlange, eine Verarbeitungsroutine und die HTTP-Oberfläche. Pro Datenordner verhindert eine Dateisperre zwei Dienstinstanzen. Der Windows-Auftrag ignoriert zusätzliche Starts einer bereits laufenden Instanz.

## Kommunikationswege

| Richtung | Aufruf | Zweck |
|---|---|---|
| Dienst → Lumia | WebSocket `ws://127.0.0.1:39231/api` | Nur Alert-Ereignisse abonnieren und `twitch-clip` auswerten |
| Dienst → Lumia | `POST /api/mcp`, Tool `get_recent_events` | Einmal beim Verbinden gepufferte Twitch-Clip-Ereignisse nachholen |
| Dienst → Lumia | `POST /api/send`, Typ `chat-command`, Wert `clip2short` | Mit `clip2short_stage` die Stufen `resolve`, `editorial` und `publish` aufrufen |
| Lumia → Twitch | `GET /helix/clips`, `/helix/games`, gegebenenfalls `/helix/videos` | Metadaten genau der gemeldeten ID und passende Kategorie lesen |
| Lumia → Dienst | `POST /api/eligible`, `POST /api/resolved` | Datum/Kanal prüfen und den neuen Clip in die Warteschlange übernehmen |
| Dienst → Twitch | yt-dlp für `https://clips.twitch.tv/<ID>`, danach HTTPS-Mediendownload | Horizontale Datei ermitteln und laden; ID, Kanal und Datum erneut vergleichen |
| Lumia → Dienst | `GET /api/jobs/<ID>`, `POST /api/editorial` | Textkontext beziehen und die geprüfte Titel-/Chatantwort zurückgeben |
| Lumia → KI-Anbieter | `resolveVariables` mit `ai_prompt` | Titel/Chatbezug vor dem Rendern sowie Beschreibung/Hashtags danach erzeugen |
| Lumia → Dienst | `POST /api/claim` | Datei und Caption prüfen; Upload atomar einmal freigeben |
| Lumia → TikTok | Custom Action `tiktok / uploadAndPublishVideo` | Fertige MP4 mit der gespeicherten Sichtbarkeit übertragen |
| Lumia → Dienst | `POST /api/result` | Rückkehr oder Fehler der Lumia-Aktion protokollieren |

Alle Dienst-Endpunkte liegen unter `http://127.0.0.1:39242`. Der lokale Dienstschlüssel wird zur Laufzeit übergeben; der veröffentlichte Lumia-Code enthält keinen Schlüssel.

## Verarbeitung auf dem PC

1. Offizielles Twitch-Datum, Kanal und ID prüfen und dauerhaft registrieren.
2. Öffentliche Originaldatei in `clips/<ID>.part` laden und vollständig in `<ID>.mp4` umbenennen.
3. Tonspur mit FFmpeg extrahieren und mit Faster Whisper (`medium`, CPU/int8) in zeitlich begrenzte Untertitelseiten umsetzen.
4. Bis zu acht Bildzeitpunkte an beiden Bildrändern mit RapidOCR prüfen. Nur Nachrichten unter erkannten Plattformköpfen mit wiederholter hoher OCR-Bewertung werden als Kandidaten zugelassen.
5. Lumia wählt den eigenen Titel und optional eine vorhandene Kandidaten-ID. Ein Zitat wird aus dem gespeicherten OCR-Text eingesetzt, nicht frei aus der KI-Antwort übernommen. Ein zusammenhängender Untertitelausschnitt muss den Antwortbezug zeitlich stützen.
6. OpenCV-Gesichterkennung und das lokale Modell `openai/clip-vit-base-patch32` prüfen Kamera-/Gameplay-/Reaction-Stichproben. Referenzprofile werden in Pixelkoordinaten der Quelle umgerechnet.
7. FFmpeg rendert jede erkannte Layoutphase mit dem gemeinsamen Clip2Short-Design. Phasen werden zu einer MP4 zusammengesetzt.
8. Dateiprüfsumme und Sichtbarkeit speichern; erst danach die Lumia-Veröffentlichung auslösen.

Rohbilder und Audioanalyse bleiben lokal. Titel- und Beschreibungs-KI erhalten Textkontext über Lumia. Der eigentliche TikTok-Upload verwendet die fertige lokale MP4.

## Zustand und Wiederaufnahme

`jobs.sqlite3` speichert den ersten Aktivierungszeitpunkt, bekannte Clip-IDs und den Verarbeitungsstand. Wiederholte Ereignisse führen nicht zu einem zweiten Auftrag.

Nach einem Neustart werden unterbrochene Download-/Analyse-/Renderaufträge wieder in die Warteschlange übernommen. Eine einmal erteilte Upload-Freigabe wird dagegen bei unklarem Ausgang als ungeklärt behandelt und nicht erneut freigegeben. Dadurch wird bei einem Absturz zwischen Übertragung und Bestätigung kein blinder zweiter Beitrag erzeugt.

„An Lumia übergeben“ ist ein Abschluss der lokalen Aktion, keine verifizierte TikTok-Publikationsbestätigung. Die Referenzinstallation wurde beim ersten privaten Test zusätzlich vom Nutzer im Konto kontrolliert.

## Quelldateien

| Datei | Verantwortung |
|---|---|
| `clip2short/service.py` | Ablauf, Warteschlange, Wiederaufnahme, Rendern und Upload-Freigabe |
| `clip2short/lumia.py` | Lokale REST-/WebSocket-/MCP-Anbindung |
| `lumia/clip2short.js` | In Lumia auszuführender Code für Twitch, KI und TikTok |
| `clip2short/downloads.py` | Öffentliche Twitch-Datei exakt der Clip-ID auflösen |
| `clip2short/editorial.py` | OCR-Kandidaten, Titelprompt und belegte Chat-Auswahl |
| `clip2short/layout.py` | Gesichter, Bildklassifikation und Szenenprofile |
| `clip_engine/transcribe.py` | Audioextraktion und Untertitelcache |
| `clip_engine/artwork.py`, `clip_engine/render.py` | Gestaltung, Untertitel und FFmpeg-Export |
| `clip2short/server.py` | Lokale Statusoberfläche und geschützte Rückmeldungen |
| `Verwalten.ps1` | Einrichtung, manueller Start/Stopp und Windows-Auftrag |
