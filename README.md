# AP YAML Hub

Eine kleine Website für eure Archipelago-Gruppe:

- **APWorlds** liegen zentral auf dem Server. Aus jeder APWorld wird automatisch ein Optionen-Formular erzeugt.
- **Vorlagen** pro Spiel („Standard“, „Kurz“, „Chaos“ …) gehören keinem Spieler. Wer spielen will, klickt
  **„Ich spiele das“**. Slot-Name und persönliche Einstellungen werden automatisch eingesetzt.
- **Sessions** sammeln, wer was spielt. Daraus entsteht eine `.zip` mit allen YAMLs, oder der Server generiert
  direkt die Multiworld zum Hochladen auf archipelago.gg.
- **Bestehende YAMLs importieren**: Sie werden zu Vorlagen, auch Dateien mit mehreren Spielen.

## Einrichten (Windows)

Voraussetzungen: Git und Python 3.11–3.13.

```powershell
.\setup.ps1 -ImportFrom "C:\ProgramData\Archipelago\custom_worlds"
.\start.ps1
```

Dann <http://127.0.0.1:8080> öffnen. Wer sich zuerst anmeldet, wird Admin.

`setup.ps1` legt die Archipelago-Quellen (Standard: Version 0.6.8) und eine Python-Umgebung unter
`%USERPROFILE%\.ap-yaml-hub` an. Ein kurzer Pfad ist nötig, weil Windows sonst an zu langen Dateipfaden scheitert.
Ohne `-ImportFrom` werden keine APWorlds kopiert; die ladet ihr dann über die Admin-Seite hoch.

**Wichtig:** Die Archipelago-Version des Hubs sollte zu der passen, die eure Spieler lokal benutzen.
Mit `.\setup.ps1 -ApVersion 0.6.9` wechselt ihr die Version.

## Für die Gruppe freigeben

```powershell
$env:HUB_PASSWORD = "geheim"
.\start.ps1 -Public
```

Es gibt keine Passwörter pro Benutzer, nur ein gemeinsames Gruppen-Passwort. Stellt die Seite am besten nicht
offen ins Internet, sondern nutzt z. B. Tailscale, ZeroTier oder ein VPN. APWorlds sind Python-Code und laufen
auf dem Server, deshalb dürfen nur Admins sie hochladen.

## Wie es funktioniert

```
APWorld-Standard          ← was das Spiel mitbringt
  └─ Vorlage              ← Gruppe oder persönlich
       └─ Profil          ← "bei mir immer DeathLink aus"
            = YAML mit deinem Slot-Namen
```

- Vorlagen speichern nur Werte, die vom APWorld-Standard abweichen. Ändert ein APWorld-Update die
  Standardwerte, gelten automatisch die neuen.
- Ein Session-Eintrag verweist auf die Vorlage. Wird die Vorlage geändert, bevor die Session gesperrt ist,
  gilt die neue Fassung.
- Eine hochgeladene APWorld mit demselben Modulnamen wie ein eingebautes Spiel (z. B. `dark_souls_3.apworld`)
  ersetzt die eingebaute Version.
- Mehrere Einträge desselben Spielers in einer Session bekommen automatisch `Max`, `Max2` usw.

## Einstellungen (Umgebungsvariablen)

| Variable | Standard | Bedeutung |
|---|---|---|
| `AP_HOME` | `%USERPROFILE%\.ap-yaml-hub` | Ort für Archipelago-Quellen und Python-Umgebung |
| `HUB_DATA` | `.\data` | Datenbank, APWorlds, erzeugte Dateien |
| `HUB_PASSWORD` | leer | Gruppen-Passwort |
| `HUB_GENERATE_TIMEOUT` | `900` | Sekunden bis zum Abbruch der Generierung |

## Tests

```powershell
& "$env:USERPROFILE\.ap-yaml-hub\venv\Scripts\python.exe" -m unittest discover tests
```

## Aufbau

| Datei | Inhalt |
|---|---|
| `hub/app.py` | Flask-Routen |
| `hub/yamlgen.py` | Ebenen zusammenführen, Slot-Namen, YAML-Export und -Import, Formular-Parsing |
| `hub/ap_bridge.py` | APWorld-Dateien, Aufruf von Archipelago als Unterprozess |
| `ap_runner.py` | Läuft innerhalb von Archipelago: liest Optionen aus, generiert |
| `data/` | `hub.db` (SQLite), `apworlds/`, `schemas/`, `sessions/` |


## Phase 1 – APWorld-Versionierung (Feature-Branch)

Die Admin-Seite zeigt neben der aktiven APWorld eine **Versionshistorie** je Modul an. Jede hochgeladene Version wird unter `data/apworlds/_versions/<sha256>.apworld` gespeichert und mit SHA-256, Modul, Version, Dateigröße und Zeitstempel in `data/apworld_versions.sqlite3` registriert. Neue Uploads aktivieren ihre Version; alte bleiben erhalten. Im Adminbereich lassen sich alte Dateien herunterladen oder erneut aktivieren. „Entfernen“ deaktiviert eine APWorld, ohne ihre archivierten Versionen zu löschen.

Vorhandene Dateien in `data/apworlds/*.apworld` und dem bisherigen `_old/`-Ordner werden beim ersten Zugriff auf den Versionskatalog **ohne Löschen** übernommen. Alte Datenbanken und YAML-Vorlagen werden nicht migriert oder ersetzt. Vor dem Update den vollständigen `data/`-Ordner sichern.

Die Archivprüfung begrenzt Uploadgröße, entpackte Größe, Anzahl der Dateien, Kompressionsverhältnisse und problematische Archivpfade; sie ist **keine Malware-Analyse und keine Sandbox**. Vor Upload und Aktivierung einer Version muss der Admin eine Vertrauensbestätigung abgeben.

**Sicherheitsgrenze:** Das vorhandene Archipelago-Setup importiert den Python-Code aktiver APWorlds beim Schema-Einlesen und Generieren. Dieser Code ist weiterhin **nicht in einer echten Sicherheits-Sandbox isoliert**. Nur überprüfte APWorlds aus vertrauenswürdigen Quellen auf einem privaten Server verwenden. Die Ausführung beliebiger fremder APWorlds und öffentliches Internet-Hosting sind ausdrücklich nicht freigegeben. Ein separater, ressourcenbegrenzter Worker ist eine notwendige Folgeaufgabe.

Die neue Versionshistorie ist noch **nicht** mit unveränderlichen Runden-Snapshots verknüpft; ein späterer APWorld-Wechsel kann deshalb bestehende noch nicht generierte Sessions beeinflussen. Einladungslinks, Bereitschaftsstatus, Seed-Snapshots und der Archipelago-Raumlink-Workflow folgen in späteren Phasen.

Tests: `python -m unittest discover -s tests -v`. GitHub Actions prüft die Tests auf Feature-Branches und Pull Requests.
