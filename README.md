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


## MVP-Weiterentwicklung: Lobby, Seeds, Hosting, Guides

Diese Erweiterung baut auf dem existierenden Flask-Projekt auf. SQLite-Daten werden **additiv migriert**; vorhandene Benutzer, Templates, Sessions und APWorld-Dateien bleiben erhalten. **Vor dem ersten Start ein vollständiges Backup von `data/` erstellen.**

### Benutzerfluss

1. Der Host erstellt eine Session und teilt einen 7 Tage gültigen Einladungslink.
2. Teilnehmer melden sich an, treten bei, wählen ein Spiel, ein YAML-Preset und ggf. eine konkrete APWorld-Version.
3. Unter **Slotoptionen** werden die tatsächlich durch Archipelago extrahierten Einstellungen angepasst. Es gibt einfachen und erweiterten Modus sowie YAML-Vorschau. Gewichte dürfen nicht sämtlich 0 sein.
4. Jeder Teilnehmer markiert seine Konfiguration als bereit. Die Bereitschaft ist an einen Hash von Slotnamen, Optionen und World-Version gebunden. Ändert sich etwas, muss erneut bestätigt werden.
5. Der Host startet die Generierung. Vorher werden vorhandene Welten, Vorlagen, Bereitschaft, gewichtete Optionen und APWorld-Versionen geprüft. Jeder erfolgreiche Build hat einen eigenen unveränderlichen Datensatz und Ausgabeordner: `data/sessions/_seeds/<build-id>/`. Frühere Seeds werden nicht überschrieben.
6. Der Host lädt die Multiworld-ZIP herunter, lädt sie **manuell** auf https://archipelago.gg/uploads hoch und klickt dort **Create Room**. Danach hinterlegt er den tatsächlichen Raumlink sowie Host:Port. Kein automatisierter Upload, kein eigener Archipelago-Spielserver.
7. Spieler sehen die Verbindungsdaten und Slotnamen unter **Jetzt spielen**, können Werte kopieren und tatsächlich in der Seed-ZIP vorhandene zusätzliche Dateien herunterladen. Nicht alle Patchdateien können sicher einem Spieler zugeordnet werden.
8. Der Host pflegt pro Spiel ein Guide-Profil für Installationsschritte, Mod-Links, erforderliche Versionen und häufige Fehler. Fehlende Informationen werden nicht erfunden.

### APWorld-Versionen

Unter Admin werden alle Versionen mit SHA-256, Archivgröße, Weltversion, optionalem Quellenlink und Aktivstatus angezeigt. Alte Versionen bleiben herunterladbar und wieder aktivierbar. Pro APWorld-Modul kann nur eine Version zugleich im Generator aktiv sein. Wählt ein Teilnehmer eine andere Version, blockiert die Preflight-Prüfung, bis Host und Spieler die Version abgestimmt haben.

### Setup und Update in VS Code

```powershell
git pull
.\start.ps1
```

Python-Code-Änderungen erfordern einen Neustart des Webservers; neue CSS-/JavaScript-Dateien ggf. Strg+F5 im Browser. Es ist kein erneutes Entpacken nötig. Für Erstinstallation zunächst `.\setup.ps1` ausführen. Die Benutzerdaten liegen **nicht** auf GitHub.

### Sicherheitsgrenzen – unbedingt beachten

**Custom APWorlds führen Python-Code aus.** Das Einlesen und Generieren erfolgt in einem Unterprozess, aber **ohne ausreichend starke Sandbox/VM-Isolation**. Die Ausführung von Custom Worlds ist deshalb standardmäßig gesperrt. Nur nach eigener Prüfung vertrauenswürdiger Dateien darf der Host lokal und bewusst aktivieren:

```powershell
$env:HUB_TRUSTED_APWORLDS = "1"
.\start.ps1
```

Diese Freigabe ist **keine Sandbox und schützt nicht vor bösartigem APWorld-Code**. Fremde und ungeprüfte Custom Worlds nicht ausführen. Ein wirklich isolierter Worker mit eingeschränkten Dateisystem-/Netzwerkrechten und Ressourcenlimits bleibt eine wichtige offene Aufgabe.

**Nicht im öffentlichen Internet betreiben.** Die bisherige Anmeldung verwendet ein gemeinsames Gruppenpasswort, jedoch keine individuellen Benutzerpasswörter. Daher ist Identitätsübernahme möglich, wenn ein Teilnehmer das Gruppenpasswort kennt. Es gibt jetzt CSRF-Schutz und geschützte Ressourcen, aber für öffentliches Hosting fehlen individuelle Authentifizierung, HTTPS, Rate-Limits und weitere Sicherheitsmaßnahmen. Ausschließlich in einer vertrauenswürdigen Privatgruppe, im LAN oder über abgesichertes VPN verwenden.

### Grenzen und Tests

- Keine automatische Mod-/ROM-Installation; keine universelle Patch-Engine.
- Kein automatisches Erstellen von Räumen auf archipelago.gg.
- Check-Zahlen/Check-Prozente werden nur angezeigt, wenn sie aus zuverlässigen Seed-Daten extrahiert werden können. Aktuell sind sie **nicht verifiziert** und werden nicht erfunden.
- Keine vollständig getestete reale Windows-Multiworld mit unterschiedlichen APWorlds; bislang automatisierte Tests mit Fake-Generator.
- Spielversionen und inkompatible APWorlds müssen zusätzlich mit realem Archipelago geprüft werden.

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m unittest discover -s tests -v
```
