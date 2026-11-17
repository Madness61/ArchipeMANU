# ArchipeMANU – verbindliche Entwicklungsregeln

Zuerst [README](../README.md), [Architektur](../docs/ARCHITECTURE.md) und [Entwicklung](../docs/DEVELOPMENT.md) lesen. Flask/Jinja, SQLite, Vanilla JS; Python 3.11–3.13. Historische Berichte sind keine aktuellen Anforderungen.

- `main` ist der zentrale Stand. Feature-Branch von aktuellem `origin/main`, kurzlebiger PR direkt gegen `main`, Tests und Review vor Merge. Keine normalen gestapelten Feature-Branches; technische Ausnahmen ausdrücklich begründen. Schutzregeln niemals umgehen.
- HTTP/Autorisierung/Antworten in `hub/routes/` bzw. den bestehenden fachlichen Blueprints. Geschäftslogik in `hub/services/`, AP-Kommunikation in `hub/integrations/`. Integrationen importieren keine Routen/Factory. Alte Modul-Aliasse dienen nur der Import-Kompatibilität. Gemeinsame Logik nur einmal implementieren.
- Generator-/Worker-Einstiegspunkte im Projektstamm erhalten; keine APWorld-Regeln im Webserver/JS nachbauen. Progression prüft regulär nur einzelne Items. Zielanalyse ausdrücklich getrennt, Kombinationserweiterung deaktiviert.
- Bestehende Konten, IDs, Seeds, YAMLs, APWorld-Archive und Historie erhalten. Niemals produktives `data/` für Tests benutzen oder löschen. Migrationen nur wenn nötig, additiv/wiederholbar und mit Altdaten-Test. Keine Migration für bloße Dateiverschiebungen.
- Anmeldung, Rollen, CSRF, Rate-Limits, Slotrechte, Race-/Spoilerregeln in jeder API serverseitig prüfen. Private Nachrichten/Passwörter nicht veröffentlichen. Keine erfundenen Messwerte oder Behauptungen über lokale Spielclients.
- Neue UI-Texte über gemeinsame DE/EN-Kataloge, Jinja `_()` und `window.HUB_I18N.t()`; Namen/Spielwerte/native AP-Nachrichten nicht übersetzen. Zentrale Theme-Tokens und responsive Komponenten verwenden.
- Vollständige Python- und Playwright-Suite ausführen; bei AP-/Worker-Änderungen echte isolierte Integrationstests. Route-, Import-, Startskript-, Markdown-Link- und Übersetzungsprüfungen gehören zur Unit-Suite. Mocktests von echten Spielclient-Abnahmen unterscheiden; Tests nicht abschwächen.
- Dauerhaft relevante Änderungen in bestehenden zentralen Dokumenten pflegen. Neue Markdown-Dateien nur für eigenständige Themen, alte Berichte ins Archiv. Aufgaben als GitHub Issues (Bug/Feature/UX/Refactoring/Tests/Dokumentation), Duplikate zusammenführen und PRs verlinken; keine konkurrierende TODO-Liste.
