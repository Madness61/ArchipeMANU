# Copilot-Anweisungen – ArchipeMANU

## Aktueller Projektstand

Privater Archipelago-Multiworld-Hub auf **Flask, Jinja, SQLite und Vanilla JavaScript**. Python 3.11–3.13; Windows-/PowerShell-first.

**Zuerst lesen:** [README.md](../README.md), [TODO.md](../TODO.md), [BROWSER_TESTS.md](../BROWSER_TESTS.md). Fachdetails in den verlinkten Dokumenten.

**Integrationsstand (13.11.2026):** `feature/unified-local-repo` bündelt #7 → #8 → #9, die Dokumentation aus #10 und den standardmäßigen Public-Start. Lokales Checkout und Remote-Branch sollen denselben Commit enthalten. Für neue Aufgaben zunächst Basisbranch und offene Änderungen überprüfen; Integration im Feature-Branch bedeutet keine Übernahme nach `main`.

## Windows-Start

```powershell
.\setup.ps1
.\start.ps1
# Optional nur auf dem eigenen Rechner:
.\start.ps1 -LocalOnly
```

Nach Setup: `http://127.0.0.1:8080`, für andere Geräte `http://<Host-IP>:8080`. Der Windows-Start bindet standardmäßig an `0.0.0.0`; `-Public` bleibt kompatibel. Es gibt **individuelle Benutzerkonten**, kein gültiges gemeinsames `HUB_PASSWORD`-Login mehr. Die ersten Konten-/Migrationsschritte stehen in `AUTH_MIGRATION.md`. Konfigurationsvariablen in `hub/config.py` nachsehen, nicht aus historischen Projektplänen übernehmen.

## Tests

```powershell
& "$env:USERPROFILE\.ap-yaml-hub\venv\Scripts\python.exe" -m unittest discover -s tests -v
.\test-browser.ps1
```

Browser-Setup: `BROWSER_TESTS.md`. Tests verwenden temporäre SQLite-DB, Mock-Generator und für WebSocket-Tests einen lokalen Protokollserver. **Keine** produktiven `data/`-Verzeichnisse, Seeds, Accounts oder echten Räume für automatische Tests verwenden.

Reale Seed-Generierung und Spielclient-Verbindungen separat prüfen und im PR von Mock-Tests unterscheiden.

## Architektur und Zuständigkeiten

- `hub/app.py` und Blueprints in `hub/mvp.py` / `hub/community.py`: Flask-Routen, Lobbys, Seed-Historie, Bibliothek.
- `hub/auth.py`: Registrierung, persönliche Passwörter, Sessions, CSRF und Ratenlimits.
- `hub/db.py`: SQLite und Migrationen; vorhandene Daten stets erhalten.
- `hub/yamlgen.py` / `hub/lobby_selection.py`: APWorld-Optionen, YAML-Ebenen, Spielerprofile, Vorlagen, Lobbywerte.
- `hub/apworld_library.py` / `hub/ap_bridge.py` / `ap_runner.py`: Archivierung, Schemaextraktion, lokale Archipelago-Generierung.
- `hub/live_api.py` / `hub/live_store.py` / `hub/live_routes.py` / `hub/live_metrics.py`: **read-only WebHost-API**, Polling, Cache, Fortschrittshistorie.
- `hub/ap_console.py` / `hub/console_routes.py` / `hub/static/console.js`: **separate** Archipelago-WebSocket-Konsole und Itemprotokoll.
- `hub/logic_tracker.py` / `hub/logic_routes.py` / `logic_worker.py`: deaktivierter historischer Universal-Logik-Tracker; alte URLs antworten mit 410 ohne Worker, **nicht** mit der WebHost-Tracker-API verwechseln.
- `hub/templates/`, `hub/static/`: Jinja, eigenes CSS/JS, SVG-Icons; Rundenzentrale mit `round*.html`, `round.css` und `round.js`.
- `hub/check_preview.py` und `ap_runner.py`: explizite Standard-Check-Vorschau ohne spielbare Ausgabe; keine automatische Generierung beim Bibliotheksbesuch.

## Arbeitsregeln

1. Nutzerfluss und bestehenden Datenvertrag vor Änderungen prüfen; Backend-Checks und Berechtigungen nicht durch bloße JS-Sperren ersetzen.
2. Bereits gespeicherte Accounts, YAMLs, APWorld-Versionen, Seeds und Event-Historie erhalten; additive Migrationen, wenn nötig.
3. Der Server kann den lokalen Spielclient nicht zuverlässig als verbunden nachweisen. „Webkonsole verbunden“ nicht als „Spiel online“ darstellen.
4. Die Live-Konsole ist das wichtigste UI-Element einer **laufenden** Runde; keine Umleitung in eine rein administrative Ansicht. Archipelago-Fachbegriffe sind für diese Gruppe bewusst passend.
5. Transiente API-/WebSocket-Probleme korrekt behandeln. Keine erfundenen Item-Sendungen, exakten Fundzeiten oder wiederholten Benutzerbefehle.
6. `Race`-/Spoilerregeln, private Nachrichten und Slotrechte in allen Ansichten und APIs bewahren.
7. Bei Styling-Änderungen gemeinsame Tokens/Makros nutzen; für kommende DE/EN- und Theme-Umschaltung siehe `TODO.md`.
8. Erst Tests ausführen, dann PR erstellen. Welche Tests **nicht** mit echten Archipelago-Spielclients liefen, ausdrücklich sagen.

Historische Dokumente sind nicht automatisch aktuelle Anforderungen. Insbesondere ältere Aussagen zu Gruppenpasswörtern, UI-Plan und Archipelago-Tracker-Verfügbarkeit vor Übernahme im Code prüfen.


## Sprache und Darstellung

Aktueller Produktzweig: `feature/social-console-localization-themes`, auf dem
Stabilitätspaket `feature/connection-reliability` (#12). Neue UI-Texte über `_()`
in Jinja beziehungsweise `window.HUB_I18N.t()` in JavaScript und die gepaarten
Kataloge in `hub/locales/` pflegen. Hinweise: `TRANSLATIONS.md`. Nutzerinhalte,
Spiel-/Slot-/Item-/Checknamen und native AP-Meldungen niemals automatisch übersetzen.
UI-Präferenzen verändern weder YAML-Werte noch Bereitschaft. Theme-Farben über
zentrale Variablen; alle vier Größen in DE/EN und beiden Themes prüfen.
