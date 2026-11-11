# ArchipeMANU

**Privater Multiworld-Hub für Archipelago.** ArchipeMANU bündelt Spielebibliothek, APWorlds, YAML-Konfiguration, Lobbys, Seed-Generierung, persönliche Spieldateien und die gemeinsame Live-Konsole in einer lokalen Webanwendung.

> **Projektstand (11.11.2026):** Das aktuelle `main` enthält das Dark-Gaming-Design, Seed-Analysen, Live-Dashboard, Archipelago-Textkonsole und den **experimentellen** Universal-Logik-Tracker. Die neue zentrale Rundenseite liegt noch in offenen, aufeinander aufbauenden PRs. Geplante Änderungen stehen in [TODO.md](TODO.md); sie sind **noch nicht umgesetzt**.

## Was der Hub macht

- **Gemeinsame Spielebibliothek:** APWorlds verwalten, Versionen archivieren, Metadaten, Einrichtungsanleitungen und Gruppenvorlagen pflegen.
- **Lobby & Konfiguration:** Spieler wählen ihre Spiele, übernehmen Standardwerte oder ändern YAML-Optionen, melden sich bereit.
- **Seed-Generierung:** Der Host erstellt eine Multiworld-ZIP, lädt sie **manuell** zu archipelago.gg hoch und hinterlegt den Raumlink beziehungsweise Host und Port.
- **Spielstart:** Slotnamen, Anleitungen, Downloads und Verbindungsdaten für die Mitglieder bereitstellen.
- **Live-Begleitung:** WebHost-API für Checks, Fortschritt und Verlauf; separate Archipelago-Textkonsole für Item-Sendungen, Chat und Befehle. Die Konsole ersetzt den lokalen Spielclient **nicht**.
- **Auswertung:** Seed- und Spielerstatistiken; Spoiler erscheinen nur nach ausdrücklicher Freigabe und gemäß Race-Regeln.

**Grenzen:** Die Website installiert oder prüft lokale Spiele, Emulatoren, Mods und ROMs nicht. Eine erfolgreich generierte Multiworld beweist keine Kompatibilität des lokalen Spielclients. Die WebHost-API liefert keinen lückenlosen Echtzeit-Eventlog; die separate Konsole erfasst Nachrichten ab ihrer Verbindung. Der Universal-Logik-Tracker ist experimentell und [zur Entfernung aus der Produktoberfläche vorgesehen](TODO.md).

## Schnellstart (Windows)

Benötigt: Git, Python 3.11–3.13, PowerShell.

```powershell
.\setup.ps1
.\start.ps1
```

Öffne danach [http://127.0.0.1:8080](http://127.0.0.1:8080). Bei einer neuen Installation registriert sich der erste Benutzer als Administrator; andere Spieler erstellen eigene Konten.

Optional vorhandene APWorlds beim Setup übernehmen:

```powershell
.\setup.ps1 -ImportFrom "C:\ProgramData\Archipelago\custom_worlds"
```

Für den Zugriff anderer Rechner im privaten Netzwerk/VPN:

```powershell
.\start.ps1 -Public
```

Die Anwendung bindet dann an alle Netzwerkschnittstellen; Zugangsdaten außerhalb von localhost nur über eine geeignete HTTPS-Konfiguration verwenden. Für private APWorlds siehe die bestehenden Hinweise unter [Betrieb und Konfiguration](#betrieb-und-konfiguration).

## So läuft eine Runde ab

1. **Spielebibliothek vorbereiten:** Benötigte APWorlds hinzufügen beziehungsweise aktivieren.
2. **Lobby erstellen oder beitreten:** Jeder Spieler wählt Spiel und Einstellungen und meldet sich bereit.
3. **Seed generieren:** Der Host erzeugt die ZIP-Datei über den Hub.
4. **Raum eröffnen:** Die ZIP manuell auf archipelago.gg hochladen und den tatsächlichen Raumlink/Port im Hub speichern.
5. **Lokal spielen:** Jeder installiert die zu seinem Spiel passende Integration und verbindet seinen Spielclient selbst mit Archipelago.
6. **Gemeinsam verfolgen:** Die Hub-Konsole für Item-Sendungen/Chat und das Live-Dashboard für Fortschritt nutzen.
7. **Abschluss:** Spieler bestätigen ihren Abschluss, Auswertungen und Downloads bleiben verfügbar.

Die drei getrennten Verbindungen **Hub-Webseite**, **WebHost-API** und **Archipelago-Textkonsole** können unabhängig voneinander funktionieren oder ausfallen.

## Tests

```powershell
& "$env:USERPROFILE\.ap-yaml-hub\venv\Scripts\python.exe" -m unittest discover -s tests -v
.\test-browser.ps1
```

Playwright muss zuvor nach [BROWSER_TESTS.md](BROWSER_TESTS.md) eingerichtet sein. Die Browser-Suite verwendet isolierte Daten, simulierte Seed-Generierung und bei Bedarf einen lokalen Archipelago-Protokollserver; sie ist **kein** End-to-End-Test mit realen Spielclients.

## Entwicklungsstand und Roadmap

Die letzten, noch nicht in `main` gemergten PRs bauen aufeinander auf:

1. [#7 – Rundenzentrale und vereinfachte Navigation](https://github.com/Madness61/ArchipeMANU/pull/7)
2. [#8 – Standard-Check-Vorschau](https://github.com/Madness61/ArchipeMANU/pull/8) (basiert auf #7)
3. [#9 – Itemprotokoll und Chat als Hauptansicht](https://github.com/Madness61/ArchipeMANU/pull/9) (basiert auf #8)

Die nächsten **getrennten** Arbeitspakete stehen in [TODO.md](TODO.md):

- **A – Verbindungsstabilität:** automatischer WebSocket-Reconnect, browserunabhängige laufende Textverbindung, klare API-/Konsolen-Statusanzeige, experimentellen Universal-Logik-Tracker deaktivieren.
- **B – Produkt-UX:** Konsole als Zentrum laufender Runden, DE/EN-Umschaltung, Light/Dark/System-Theme, bessere visuelle Priorisierung, persönliche Itemfilter.

## Dokumentation

| Thema | Dokument |
| --- | --- |
| Prioritäten, Aufgaben und Abnahmekriterien | [TODO.md](TODO.md) |
| YAML-Ebenen, Konfiguration und Vorlagen | [YAML_CONFIGURATION.md](YAML_CONFIGURATION.md) |
| Spielebibliothek, Einrichtung, Quellen | [GAME_LIBRARY.md](GAME_LIBRARY.md) |
| Live-Dashboard, API-Daten, Cache und Grenzen | [LIVE_DASHBOARD.md](LIVE_DASHBOARD.md) |
| Textkonsole, Befehle und Live-Item-Ereignisse | [ARCHIPELAGO_CONSOLE.md](ARCHIPELAGO_CONSOLE.md) |
| Experimenteller Universal-Logik-Tracker (historischer Ist-Stand) | [LOGIC_TRACKER.md](LOGIC_TRACKER.md) |
| Benutzerkonten und Kontomigration | [AUTH_MIGRATION.md](AUTH_MIGRATION.md) |
| Layout und Design-Tokens | [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) |
| Browser-Tests und Testisolation | [BROWSER_TESTS.md](BROWSER_TESTS.md) |
| Frühere Umsetzungsstände | [UI_PLAN.md](UI_PLAN.md), [PROJEKTANALYSE.md](PROJEKTANALYSE.md), [historisches README](docs/archive/README_legacy_2026-11-11.md) |

Ältere Analysen und UI-Pläne sind **historische Dokumente**. Bei Widersprüchen gelten der aktuelle Quellcode, die jeweils neueste Feature-Dokumentation und die verifizierten Testresultate.

## Betrieb und Konfiguration

- Standard-Archipelago-Checkout: `%USERPROFILE%\.ap-yaml-hub`, Version über `.\setup.ps1 -ApVersion ...` wählbar.
- Datenverzeichnis: `data/`, konfigurierbar über `HUB_DATA`. **Vor Updates oder Migrationen den vollständigen Datenordner sichern.**
- `HUB_GENERATE_TIMEOUT` steuert das Generator-Timeout (Standard: 900 Sekunden).
- `.\start.ps1 -Public` bindet den Hub für andere Geräte; `HUB_COOKIE_SECURE=1` bei HTTPS.
- Das Aktivieren benutzerdefinierter APWorlds führt deren Python-Code auf dem Host aus. Der Startschalter `-NoCustomWorlds` sperrt diese Ausführung. Der Hub ist für einen privaten, vertrauenswürdigen Nutzerkreis konzipiert.

Weitere technische Details stehen in `hub/config.py` und den jeweiligen Dokumentationsdateien.
