# Architektur

ArchipeMANU verwendet Flask/Jinja, SQLite und Vanilla JavaScript. Ein Waitress-Prozess hält die ausdrücklich gestarteten Textverbindungen und begrenzte Hintergrundjobs. Archipelago läuft für Extraktion, Generierung und Progression in getrennten Python-Prozessen. Es gibt keine neue Datenbankmigration für diese Umstrukturierung.

## Zuständigkeiten

| Bereich | Eigentümer |
| --- | --- |
| Zusammenbau, Konfiguration, additive Migrationen | `hub/app.py`; gemeinsame Flask-Instanz in `hub/web.py` |
| HTTP, Autorisierung, Formulare und Antworten | `hub/routes/`: security, overview, library, templates, accounts, lobbies, rounds, admin |
| Konten und unveränderte zusätzliche Blueprints | `hub/auth.py`, `community.py`, `live_routes.py`, `console_routes.py`, `progression_routes.py` |
| Presets, Originalvorlagen, Profile, YAML-Komposition | `hub/services/selection.py`, `hub/yamlgen.py` |
| Bereitschaft, Runden, Snapshots, Generierungsjobs, Hostingdaten | `hub/services/rounds.py` |
| Dauerhaftes Konsolenjournal und lesbare Ereignisse | `hub/services/console_journal.py` |
| Globale Itemsuche und belegter Check-/Empfangsstatus | `hub/services/item_finder.py` |
| Progression-Aufträge, Warteschlange, Cache, Worker | `hub/services/progression.py` |
| APWorld-Installationszugriff, Extraktion, Generierung | `hub/integrations/archipelago.py`, `hub/apworld_library.py` |
| Archipelago-WebSocket-Protokoll und Wiederverbindung | `hub/integrations/console.py`, `console_commands.py` |
| WebHost-HTTP-API, Cache und Fortschrittsmessung | `hub/live_api.py`, `live_store.py`, `live_metrics.py` |
| Rundenaufzeichnung und Lease | `hub/recording.py` |
| Einzelitem-Regeln / ausdrückliche Spielzielanalyse | `progression/engine.py`, `inventory.py`, `goals.py` |
| Darstellung | `hub/templates/`, `hub/static/`, `hub/locales/` |

`hub/ap_bridge.py`, `hub/ap_console.py`, `hub/mvp.py` und `hub/progression.py` sind kompatible Modul-Aliasse auf die kanonischen Implementierungen. Es gibt keine kopierte Geschäftslogik; bestehende Imports und Test-Patches adressieren dasselbe Modulobjekt. Die unpräfixierten Flask-Endpunkte und das `mvp`-Blueprint behalten ihre bisherigen Namen und URLs. Der Vertrag ist in `tests/fixtures/route_contract.json` festgehalten.

## Datenflüsse

**Vorbereitung:** HTTP-Route → Auswahl/YAML-Service → APWorld-Standard → gewählte Vorlage → persönliche Profilwerte → Lobbywerte. Die Vorschau und der eingefrorene Generator-Snapshot verwenden dieselbe Komposition. Die Bereitschaft hängt am Fingerprint von Optionen, Vorlage, Slot und APWorld-Version.

**Generierung:** Host-Route → `rounds.begin_build` → geprüfte Teilnehmer/YAMLs → unveränderlicher Build → Hintergrundjob → Archipelago-Integration → `ap_runner.py`. Ergebnisse und Original-YAMLs werden unter dem jeweiligen Seed archiviert. Ein globaler AP-Lock verhindert gleichzeitige Installation/Extraktion/Generierung/Rekonstruktion.

**Live:** Browser → Konsole-Route → authentifizierter TextOnly-Client. Strukturierte Item-Sendungen gelangen in das Journal. WebHost-Fortschritt verwendet einen unabhängigen Cache. Empfangslisten beweisen Empfänge, kein vollständiges vergangenes Weltlog. Private Nachrichten bleiben privat.

**Progression:** ausdrücklicher POST → eigener Slot und Spoiler/Race-Prüfung → beobachtetes Inventar/Checks → überprüfte Seed-Evidenz → Cache/Warteschlange → `progression_worker.py` → Original-APWorld rekonstruieren → Einzelitem- oder Zielmodus. GET startet keine Berechnung. Beide Modi besitzen getrennte Cache-Schlüssel. Details: [Progression](reference/PROGRESSION.md).

## Abhängigkeitsregeln

- Routen verarbeiten HTTP und rufen Dienste auf. Dienste bündeln Anwendungsvorgänge und benutzen Integrationen; Integrationen importieren keine HTTP-Routen oder App-Factory.
- Flask-Instanz und Blueprint-Identität liegen außerhalb der Dienste. Keine Registrierung beim Aufruf eines Dienstes.
- Bestehende Flask-kontextbezogene Zugriffshelfer der Runden bleiben explizit; keine zweite Autorisierungsimplementierung einführen.
- Der Auswahl-Dienst besitzt auch den Bereitschafts-Fingerprint. Der Runden-Dienst verwendet diese gemeinsamen Funktionen; der Auswahl-Dienst importiert weder Runden noch Factory.
- Die vier alten Modulpfade bleiben nur Import-Kompatibilität. Neue Implementierungen gehören direkt in ihre zuständigen Module.
- Generator-/Worker-Einstiegspunkte im Projektstamm bleiben stabil: `ap_runner.py`, `progression_worker.py`, außerdem der deaktivierte historische `logic_worker.py`.
- Keine APWorld-Regeln in Webserver oder JavaScript nachbilden. Die alte Kombinationserweiterung ist ausdrücklich deaktiviert; produktiver Code importiert sie nicht.

Weitere Regeln und Prüfungen: [Entwicklung](DEVELOPMENT.md). Persistenz und Grenzen: [Betrieb](OPERATIONS.md), [API](reference/API.md).
