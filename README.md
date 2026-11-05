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
