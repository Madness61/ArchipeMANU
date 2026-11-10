# Check-Anzahl mit Spiel-Standard

Die Spielebibliothek und die Spielseite bieten **Standard-Checks ermitteln**.
Die Vorschau zählt keine Namen aus dem APWorld-Katalog. Sie erstellt eine
temporäre YAML mit den aktuellen Spielvorgaben und berechnet einen echten
Einzelspiel-Probelauf in der vorhandenen Archipelago-Laufzeit.

## Bedeutung

- Reiner Spiel-Standard, ohne Gruppen-Vorlage, persönliche Vorlage oder Profilwerte.
- Gezählt werden gefüllte Fundorte mit numerischer Check-ID und numerischem
  Itemcode. Events, Startinventar und nicht adressierte interne Fundorte zählen nicht.
- Fester Referenz-Seed `20261110`; der Wert ist eine Messung für diesen Probelauf.
  Zufallsoptionen, andere Einstellungen, APWorld-Versionen und Multiworld-Effekte
  können zu anderen Werten in einer tatsächlichen Runde führen.
- Kein Nachweis vollständiger Einrichtung oder Spielbarkeit. Die native
  `--skip_output`-Option überspringt Ausgabeschritte und die für sie vorgesehenen
  `assert_generate`-Prüfungen. Deshalb kann beispielsweise eine ROM-basierte
  Check-Zählung ohne Patchausgabe funktionieren, obwohl zum Spielen weiterhin
  eine Original-ROM erforderlich ist.
- Liefert eine APWorld ohne zusätzliche Dateien oder andere Spieler kein
  Ergebnis, erscheint ein verständlicher Hinweis; es gibt keinen Schätzwert.

## Ablauf

`GET /api/games/<slug>/checks` liest ausschließlich den Cache/Jobstatus.
`POST` startet ausdrücklich eine Berechnung (Anmeldung, CSRF und Rate-Limit).
Das bloße Öffnen der Bibliothek startet keine Generatoren. Jobs laufen begrenzt
im Hintergrund mit 120 Sekunden Timeout und verwenden die vorhandene
APWorld-Vertrauensfreigabe und den gemeinsamen Laufzeit-Lock. Eine bereits
laufende Generierung wird nicht durch eine Vorschau unterbrochen.

Ergebnisse stehen geteilt unter `data/check_previews/`. Der Cache-Schlüssel
berücksichtigt YAML, AP-Version/-Quellstand, aktive APWorld-Archivhashes und
Runner-Code. Änderungen führen zu einer neuen Berechnung. Vor Ausführung werden
Archivbytes erneut geprüft. Temporäre Daten werden entfernt; es entstehen keine
Hub-Lobbys, Seed-Einträge, Patchdateien, Multidata oder Spoilerberichte.

## Validierung

Native Probeläufe am 10.11.2026: **APQuest 6**, **Super Mario World 108**
Item-Checks mit den lokal installierten Spielversionen und dem Referenz-Seed.
Diese Werte sind keine Behauptung über andere Einstellungen oder laufende Runden.
Die automatisierten Tests verwenden isolierte Daten und einen Testgenerator.
Sie prüfen Zählkriterien, expliziten Start, CSRF, Cache, Versionswechsel,
Fehler/Beschäftigung und mobile Darstellung.

Lokale Gesamtabnahme: 194 Python-Tests und alle 15 Playwright-Szenarien
erfolgreich. Desktop- und Smartphone-Aufnahmen der neuen Anzeige wurden geprüft.
