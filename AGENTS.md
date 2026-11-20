# AGENTS.md – ArchipeMANU

Zentrale Anweisungen für Coding-Agenten. ArchipeMANU ist ein privater Archipelago-Multiworld-Hub mit Flask/Jinja, SQLite und Vanilla JS (Python 3.11–3.13). Maßgeblich sind aktueller Code und die konkrete Aufgabe, nicht historische Berichte.

## Kontext effizient verwenden

- Starte mit **dieser Datei und der Aufgabe**. README, Architektur- und Entwicklungsdokumente nicht pauschal vollständig lesen.
- Suche zuerst gezielt nach betroffenen Routen, Komponenten und Tests (z. B. `rg -n`). Lies relevante Ausschnitte statt das gesamte Repository, große Dateien oder ungekürzte Logs auszugeben.
- Ziehe Dokumentation nur bei Bedarf hinzu: [Architektur](docs/ARCHITECTURE.md) für unklare Zuständigkeiten/übergreifende Änderungen, [Entwicklung](docs/DEVELOPMENT.md) für Testbefehle/Git-Details, [Betrieb](docs/OPERATIONS.md) für Deployment/Daten, passende [Referenzen](docs/reference/) für API, Progression, UI oder YAML.
- Erweitere den Kontext nur, wenn Abhängigkeiten oder Fehler es erfordern. Keine vollständige Neuanalyse für eine lokale Änderung; keine unnötigen Statusberichte, Pläne, Diffs oder Dokumentationsdateien.
- Prüfe vorhandene Implementierungen vor Änderungen. Wiederverwende sie statt parallele Wege, neue Abstraktionen oder vorsorgliches Refactoring einzuführen.

## Architektur und verbindliche Grenzen

- HTTP, Rechte und Antworten: `hub/routes/` oder bestehende fachliche Blueprints (`hub/*_routes.py`). Geschäftslogik: `hub/services/`. Archipelago-Integration: `hub/integrations/`, `hub/live_api.py`, `hub/recording.py`. UI: `hub/templates/`, `hub/static/`, `hub/locales/`.
- Integrationen importieren keine Flask-Routen/Factory. Bestehende Alias-Module (`hub/mvp.py`, `hub/ap_bridge.py`, `hub/ap_console.py`, `hub/progression.py`) und Generator-/Worker-Einstiegspunkte erhalten; gemeinsame Logik nur einmal implementieren.
- APWorld-Regeln nicht im Webserver/JS nachbilden. Reguläre Progression prüft Einzelitems; Spielzielanalyse bleibt ausdrücklich getrennt, Paaranalyse deaktiviert.
- Erhalte Konten, IDs, Seeds, YAMLs, APWorld-Archive, Verbindungen und Ereignishistorie. Produktives `data/` niemals für Tests verwenden, löschen oder zurücksetzen. Datenbankmigrationen nur bei Bedarf, additiv, wiederholbar und mit Altbestandstest.
- Anmeldung, Rollen, CSRF, Rate-Limits, Slot-Zuordnung, Race- und Spoilerrechte serverseitig absichern. Persönliche Antworten und Passwörter niemals veröffentlichen. APWorld-Uploads enthalten ausführbaren Code ohne Sandbox: keine Vertrauensgrenze umgehen.
- Unbekannte/veraltete Datenstände korrekt kennzeichnen; keine erfundenen Spielclient-, Item- oder Serverzustände.

## UX und Qualität

- Die Spieleraufgabe hat Vorrang vor technischen Details: klare Navigation, wenig Redundanz, konsistente, responsive Oberflächen. Bestehende DE/EN-Übersetzungen (`_()`, `window.HUB_I18N.t()`) und Theme-Tokens nutzen; native Spiel-/Slotnamen nicht übersetzen.
- Bei UI-Änderungen relevante Abläufe auch mobil und visuell prüfen. Tests ersetzen keine Beurteilung von Hierarchie, Bedienbarkeit und Zuständen.
- Während der Umsetzung **gezielte Tests zuerst**; bei geänderten Verträgen Regressionen ergänzen. **Vor Merge** komplette Python- und Playwright-Suite ausführen bzw. erfolgreiche CI prüfen. Bei AP-/Worker-Änderungen zusätzlich echte isolierte Integrationstests; Skips und fehlende Praxisabnahmen offen benennen. Tests nicht abschwächen.
- Als Ausgangspunkt aktuelles `origin/main`; kurzlebiger Feature-Branch, PR direkt nach `main`, Review/CI prüfen, erst dann mergen. Keine gestapelten PR-Ketten oder Umgehung von Schutzregeln.
- Nur dauerhaft relevante Dokumentation in bestehenden zentralen Dateien pflegen. Neue Markdown-Dateien nur für eigenständige Themen; Aufgaben als GitHub Issues statt zusätzlicher TODO-Listen.
- Abschlussantwort knapp: **Änderungen, Prüfungen (inkl. Skips), Merge-Status, offene Risiken**. Keine Wiederholung langer Analysen oder Testlogs.
