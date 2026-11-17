# Entwicklung und Tests

## Git und Aufgaben

`main` ist der zentrale Entwicklungsstand. Neue Arbeit beginnt auf einem kurzlebigen Feature-Branch von aktuellem `origin/main`, mit PR direkt gegen `main`. Tests und Review vor dem Merge prüfen; Branch-Schutz niemals umgehen. Keine normalen Ketten auf offenen Feature-Branches. Technisch erforderliche Ausnahmen müssen im PR begründet und zeitnah integriert werden.

Aufgaben ausschließlich als [GitHub Issues](https://github.com/Madness61/ArchipeMANU/issues) führen. Kategorien: Bug, Feature, UX, Refactoring, Tests, Dokumentation. Titel/Kategorie und Akzeptanzkriterien nennen, Duplikate vorher suchen und passende PRs verlinken. Es gibt keine zweite aktive TODO-Liste. Ohne Projects-Zugriff genügt diese Issues-Struktur.

Die alte Kette #11–16 wurde anhand ihrer Commit-Abstammung geprüft und über #16 per Merge-Commit integriert. Alle sechs PRs sind gemergt. Die anschließende Vereinfachung beginnt direkt auf diesem `main`; die [Archivübersicht](archive/README.md) erklärt die Dokumentations- und TODO-Migration.

## Umgebung

Python 3.11–3.13; für AP 0.6.8 bevorzugt 3.13. Installation/Betrieb: [OPERATIONS.md](OPERATIONS.md). Für Tests eine eigene venv verwenden:

```powershell
py -3.13 -m venv .venv-browser
.\.venv-browser\Scripts\python.exe -m pip install -r requirements-browser.txt
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD ".playwright-browsers"
.\.venv-browser\Scripts\python.exe -m playwright install chromium
```

## Prüfungen

```powershell
.\.venv-browser\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v
.\test-browser.ps1
.\.venv-browser\Scripts\python.exe -m unittest discover -s integration_tests -v
.\.venv-browser\Scripts\python.exe -m scripts.ui_checks
```

Die echte Integrationssuite benötigt einen vorhandenen AP-Checkout und dessen Python-Umgebung (`AP_SOURCE`, `AP_PYTHON`); sie kopiert Quellen und benötigte APWorlds in temporäre Ordner. Fehlende Voraussetzungen werden als Skip sichtbar. Sie prüft ChecksFinder, Meritous, vorhandene Custom-Pseudoregalia und echte DS3-Regeln. Kein Netzwerkraum und keine produktive Datenbank werden benutzt.

Zum Zuschauen: `.\test-browser.ps1 -Headed -SlowMo 700`; gezielt mit `-Filter progression`. Alternativ `python -m browser_tests` unter Linux/macOS nach `python -m playwright install --with-deps chromium`. In einem Worktree kann `PLAYWRIGHT_BROWSERS_PATH` auf den bereits installierten Browsercache zeigen.

| Suite | Vertrag |
| --- | --- |
| `tests/` | Konten/Migration/Rechte, Bibliothek/APWorlds, YAML-Schichtung, Lobby/Bereitschaft, Generierung/Downloads, Hosting, Console/Wiederverbindung/Aufzeichnung, Cache, Spoiler/Race, Übersetzungen, Einzelitem-Regeln, Zielmodus, Imports/Routen/Links/Skripte |
| `browser_tests/` | Echte Formulare, Cookies, CSRF und JavaScript; getrennte Kontokontexte, gemeinsame Bibliothek, Lobby, YAML, simulierte Generierung, Statistik, lokale AP-Protokolltests; DE/EN/Themes/Mobil |
| `integration_tests/` | Echte AP-Generierung/Rekonstruktion und Originalregeln; Worker-Ressourcenlimits, eigene API-Jobs und Ablehnung veränderter Evidenz |

Reguläre GitHub Actions führen Python- und Chromium-Tests aus. Der Mock-Generator ist ausschließlich Testinfrastruktur. Fehler liefern Screenshots, Trace/Video und Browser-/Serverlogs unter `test-results/browser/`; echte Integrationen schreiben nach `test-results/progression-real/`. Keine Passwörter in Logs. Diese automatisierten Tests ersetzen keinen echten mehrstündigen Spieleabend; die offene Abnahme steht in [#17](https://github.com/Madness61/ArchipeMANU/issues/17), weitere Welten in [#19](https://github.com/Madness61/ArchipeMANU/issues/19).

## Änderungsregeln

Zuständigkeit vor Änderungen in [ARCHITECTURE.md](ARCHITECTURE.md) bestimmen. Bestehende URLs, CLI-Einstiegspunkte und Datenverträge bewahren. Keine Datenbankmigration allein für Dateiverschiebungen. Nötige Migrationen additiv, wiederholbar und mit Altdaten-Test ausführen. Niemals echten `data/`-Ordner für Tests verwenden, zurücksetzen oder löschen.

Tests entsprechend geändertem Verhalten ergänzen; alte Funktionsverträge nicht stillschweigend abschwächen. Die deaktivierte Paarlogik behält ihre Regressionen in der Extension; die Produktionsengine erhält eigene Tests gegen unbeabsichtigte Paar-/Zielaufrufe. Route-, Import-, Skript- und Markdown-Verträge gehören zur Unit-Suite.

Neue UI-Texte und Theme-Farben über [gemeinsame Ressourcen](reference/INTERFACE.md) pflegen. Vorhandene zentrale Dokumente aktualisieren; neue Markdown-Dateien nur für dauerhaft eigenständige Themen. Historische Resultate ins Archiv statt ins README. Gemessene Ergebnisse im PR mit Commit, Suite, Skips und echten/mocked Grenzen dokumentieren.
