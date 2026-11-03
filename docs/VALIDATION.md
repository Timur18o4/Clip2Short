# Prüfstand

## Korrektur 0.2.1 am 03.11.2026

- 61 Python-Tests und sieben Lumia-Vertragstests bestanden.
- Der betroffene lokale Kamera-Clip bestand mit unveränderten Quellprofilen alle 16 Stichproben als durchgehende Kameraansicht. Zuvor führten kleine Gesicht-Fehlfunde am Ende zur falschen Reaction-Auswahl.
- Wiederverwendung bereits geprüfter Titel ohne erneuten KI-/OCR-Aufruf getestet. Die Gesicht-Abdeckungsprüfung bleibt bestehen.
- Keine TikTok-Veröffentlichung für diesen Korrekturtest ausgelöst.

## Version 0.2.0 am 03.11.2026

- 59 Python-Tests, sieben Lumia-Vertragstests und die Syntaxprüfung beider Browseroberflächen erfolgreich ausgeführt.
- Native Lumia-Anbindung auf dem vorhandenen Rechner geprüft: Vorlagenauswertung, erkannter Twitch-Kanal, Text-KI und Aktivierung des Twitch-Clip-Alarms über `run-actions`. Kein neuer Code-Befehl war dafür nötig.
- Ersteinrichtung mit getrenntem Datenordner und eigener lokaler Testoberfläche geprüft. Die Produktion wurde dafür nicht neu initialisiert. Die Tests erzeugten keine TikTok-Veröffentlichung.
- Browserprüfung: Verbindung zu Lumia, lokale Modellliste, Referenzvideo, Standbild und Render-Vorschau; keine JavaScript-Laufzeitfehler und kein horizontaler Überlauf in der mobilen Ansicht.
- Eigener Hintergrund und mit der Maus verschobene Quell-/Zielflächen gespeichert und als lokale MP4 mit 1080 × 1920 exportiert.
- Die bisherige persönliche Gestaltung einschließlich Fußzeile wurde gegen die vorige Fassung pixelgleich verglichen.
- Portable Python-3.12-Laufzeit heruntergeladen und anhand des veröffentlichten SHA-256-Digests geprüft. In einer getrennten Umgebung mit Testabhängigkeiten liefen die automatischen Tests. Dies ersetzt keine vollständige Neuinstallation von Windows.
- Windows-PowerShell-Installer auf Syntax, Laufzeiterkennung und versteckte Prozessaufrufe mit korrekter Erkennung erfolgreicher sowie fehlgeschlagener Rückgabewerte geprüft.
- Die lokale Ollama-Anbindung lieferte auf dem vorhandenen Rechner einen Titel und eine Beschreibung mit gültigem Ausgabeformat. Ein zuvor beobachteter Zeilenformat-Fehler wurde durch strukturierte JSON-Ausgabe für den lokalen Weg behoben; Inhaltsprüfung und kanonischer Kategorie-Hashtag bleiben im Programm. Laufzeit und Qualität hängen vom Modell und der Hardware ab.

Noch offen: vollständiger Installer-Durchlauf auf frisch installiertem Windows, neue Installation des optionalen Ollama-Installers, erster echter Clip-Durchlauf mit TikTok-Veröffentlichung über den neuen nativen Weg und Erkennung beliebiger fremder OBS-Szenen. Der früher bestätigte Upload verwendete die bisherige Brücke und belegt diesen neuen Weg nicht.

## Historischer Prüfstand der ersten Veröffentlichung

## Referenzdurchlauf am 31.10.2026

- Ein nach Dienstaktivierung neu erstellter Twitch-Clip wurde über Lumia erkannt und genau dieser Clip heruntergeladen.
- Metadaten, Kategorie und Erstellungsdatum wurden geprüft. Es wurde kein alter Clip als Ersatz verwendet.
- Lokal wurden Untertitel und eine große Kamera erkannt. Das Video wurde mit 1080 × 1920, 60 Bildern/s, 30 Sekunden Laufzeit und Audiospur erstellt.
- Lumia erzeugte Beschreibung und vier Hashtags und führte den privaten TikTok-Upload aus. Der Nutzer bestätigte den vorhandenen privaten Beitrag im TikTok-Konto.
- Anschließend wurde die Gestaltung desselben neuen Testclips als lokale Variante um eigenen KI-Titel und eine aus dem Bild erkannte Chatnachricht erweitert. Diese Variante wurde nicht erneut hochgeladen. Die Originaldatei blieb anhand ihrer gespeicherten Prüfsumme unverändert.
- Ein synthetisches Video mit Kamera → Gameplay → Reaction wurde mit 1080 × 1920, 30 Bildern/s und Audiospur gerendert.
- Windows-Aufgabenplanung, lokale Schnittstellen, FFmpeg, Sprachmodell, Bildmodell und Datenbank wurden in der Referenzinstallation geprüft.

Private Kontodaten, Originalmedien, Vorschaubilder, Chatprotokolle und Laufzeitdaten dieses Tests werden nicht veröffentlicht.

## Automatische Prüfungen

Für die öffentliche Fassung wurden am 01.11.2026 **42 Python-Tests und sieben Lumia-Vertragstests erfolgreich ausgeführt**. Die Veröffentlichungskontrolle prüft zusätzlich die Dateiauswahl; das erzeugte ZIP wird auf Vollständigkeit und ZIP-Integrität geprüft.

Die Tests unter `tests/` behandeln unter anderem:

- Datumssperre, Kanalprüfung, alte oder wiederholte Ereignisse;
- Neustart und unterbrochene Verarbeitung;
- einmalige atomare Upload-Freigabe und verspätete Antworten;
- Prüfung veränderter Videodateien und gespeicherter Sichtbarkeit;
- lokale Zugriffssperre und gültige Bildprofile;
- Caption-Länge, Leerzeile, vier Hashtags und tatsächliche Kategorie;
- eigene Titel, ausschließlich vorhandene Chat-Kandidaten und Untertitelbelege;
- Ausschluss von Likes-Meldungen, Moderator-Abzeichen und erfundenen Zitaten;
- lokale Vorschauen ohne Wiederöffnung einer Upload-Freigabe;
- Kanalnamen bei der Einrichtung und Lumia-API-Verträge mit simulierten Antworten.

GitHub Actions führt die Python-Tests unter Windows sowie die JavaScript-Vertragstests aus. Diese Tests benötigen keine echten Plattformzugänge, laden keine Modellgewichte und veröffentlichen nichts.

## Noch nicht durch diesen Prüfstand belegt

- Ein echter Gameplay- oder Reaction-Clip wurde hier nicht durch einen öffentlichen Upload geprüft; dafür liegen synthetische Layoutprüfungen vor.
- Die korrekte Erkennung jeder anderen OBS-Szene, Sprache, Webcam-Position oder Chatgestaltung ist nicht garantiert.
- Das Tool fragt keinen abschließend verifizierten TikTok-Publikationsstatus ab. „An Lumia übergeben“ bleibt ein lokales Aktionsergebnis.
- Die vollständige Neuinstallation auf beliebiger fremder Hardware und das Verhalten zukünftiger Plattformversionen sind nicht durch einen einzelnen Referenzdurchlauf belegt.

Die Veröffentlichung ist deshalb ausdrücklich eine **Testversion**, keine Zusicherung fehlerfreier autonomer Veröffentlichung.
