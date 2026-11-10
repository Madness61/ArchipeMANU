# Multiworld Hub

In der Spielebibliothek zeigt **Standard-Checks ermitteln** die Anzahl der
Item-Fundorte eines echten Einzelspiel-Probelaufs mit den Spielvorgaben.
Ergebnisse werden pro Konfiguration und Spielversion zwischengespeichert;
eure spätere Runde kann abweichen. [Details](STANDARD_CHECK_PREVIEW.md).

Die Oberfläche hat drei Hauptbereiche: **Übersicht**, **Meine Runden** und
**Spiele entdecken**. Jede Runde öffnet eine gemeinsame Rundenzentrale mit
**Spielen**, **Fortschritt**, **Mitspieler** und **Mehr**. Eigene Dateien,
Slotname und Serveradresse stehen direkt bei deinem Spiel. Details zum Ablauf
und zu unverändert verfügbaren URLs: [UX_SIMPLIFICATION.md](UX_SIMPLIFICATION.md).

### Erreichbare Checks und Go-Mode

Unter **Runde → Fortschritt → Deine nächsten Checks** berechnet Universal Tracker die
Erreichbarkeit für den eigenen verbundenen Slot. Checks lassen sich nach
Logikstatus und Region filtern; Iteminhalte werden nur ausdrücklich aufgedeckt.
Einrichtung, Datenquellen und Grenzen: [LOGIC_TRACKER.md](LOGIC_TRACKER.md).

Die Spielebibliothek unterstützt eigene Beschreibungen, Genres und freie Tags
beim Upload und unter **Spiel bearbeiten**. Tags wirken sofort in Suche und
Filtern. Uploader bearbeiten ihre Spiele, Admins alle Spiele. Katalogangaben
bleiben beim APWorld-Versionswechsel erhalten. Der Desktop-Inhaltsbereich
nutzt auch breite Bildschirme vollständig.

### Archipelago-Konsole und Befehls-API

Unter **Runde → Mehr → Archipelago-Konsole** kannst du deinen eigenen Slot
als Textclient verbinden: konkrete Item-Sendungen mit Finder, Empfänger und
Check, Chat, `/received`, `/missing`, `/items`, `/hint` und weitere Befehle.
Item-Sendungen sind gemeinsam sichtbar; Befehlsantworten bleiben persönlich.
Die bisherige Tracker-Schnittstelle bleibt erhalten. Einrichtung, Grenzen und
JSON-Endpunkte: [ARCHIPELAGO_CONSOLE.md](ARCHIPELAGO_CONSOLE.md).

Das [Designsystem](DESIGN_SYSTEM.md) beschreibt das neue Dark-Gaming-Frontend:
Sidebar und mobiles Menü, persönliches Dashboard, Spielkatalog mit eigenen
grafischen Titelbildern, Lobby-Spielerkarten und eine persönliche Spielstartzentrale.
Die vorhandenen Formulare, YAML-Regeln, Rechte und Seed-/Live-Funktionen bleiben
erhalten. Eigene Katalogangaben werden in einer zusätzlichen Tabelle gespeichert;
bestehende Spiel- und Rundendaten werden nicht ersetzt.

Das neue [Live-Dashboard](LIVE_DASHBOARD.md) begleitet laufende Runden mit
gemeinsam gecachten Archipelago-Daten, Spielerkarten, Empfangsmatrix, Verlauf,
Ereignissen und Vergleichen. Nach dem Upload des Seeds genügt der Raumlink
unter „Generierte Runden“ oder „Jetzt spielen / Verbindung“.

### Überarbeitete Oberfläche

Dunkle Navigation, helle Karten und ein klarer Ablauf für die gemeinsame Runde:
Übersicht → Lobby → Spiel und Einstellungen → Bereit → Generierung durch den Host.
Die Bibliothek bietet Suche sowie Status- und Herkunftsfilter. Spieler und Host
haben getrennte Aktionen; technische Extras bleiben aufklappbar erreichbar.
Die Analyse zeigt echte Kennzahlen, bewusst aufdeckbare Spoiler und die vom Host
gespeicherte Verbindung. Plan, Umsetzung und Prüfung: [UI_PLAN.md](UI_PLAN.md).

### Spielauswahl ohne YAML-Editor

Die Lobby bietet **YAML überarbeiten** sowie **Standardwerte übernehmen**
(bei einer Vorlage: **Vorlage übernehmen**). Die direkte Übernahme speichert
Spiel, gewählte Vorlage und passende Profilwerte ohne Editor. Danach meldet sich
der Spieler in der Teilnehmerliste bereit. Bereits gespeicherte Lobby-Anpassungen
werden beim erneuten direkten Übernehmen durch diese Grundwerte ersetzt.

Vorlagen zeigen eine Beschreibung und konkrete Abweichungen vom Spiel-Standard.
Im YAML-Editor gelten die angezeigten Werte automatisch; Vererbungs-Häkchen sind
nicht nötig. **Diesen Wert zurücksetzen** setzt nur die betreffende Anpassung auf
Vorlage/Profil zurück und lässt andere Änderungen im Entwurf erhalten. Gespeichert
wird weiterhin erst mit **Auswahl übernehmen** beziehungsweise **Einstellungen
speichern**.

### Aktive Lobby und Verbindung einrichten

In der Lobby aktualisieren **Teilnehmer aktualisieren** und **Runden aktualisieren**
den Teilnehmerstatus und die generierten Seeds. Mit JavaScript bleiben offene
YAML-Entwürfe sowie angefangene Verbindungsformulare dabei erhalten.

Unter **Generierte Runden** sieht der Host bei jedem erfolgreichen Seed ein
Formular **Raum-Link, Server & Port eintragen**. Nach dem Speichern erscheint der
Reiter **Aktive Lobby** für Teilnehmer, Host und Admins. Eine eingerichtete Runde
wird direkt geöffnet; bei mehreren gibt es eine Auswahl. Pro Lobby wird die
zuletzt gespeicherte Verbindung eines erfolgreichen Seeds verwendet. Ein
Archipelago-Raum-Link ist optional, damit auch selbst gehostete Spielserver
eingetragen werden können. Die angezeigten Verbindungen sind Angaben des Hosts,
keine automatische Prüfung, ob der Spielserver online ist.

### Automatische Browser-Tests

Playwright bedient die Website mit getrennten Spieler-Sitzungen: Registrierung,
gemeinsame APWorld-Bibliothek, Aktivierung, Lobby, YAML-Optionen, Bereitschaft,
simulierter Seed-Build und Statistik. Alle Daten liegen in temporären
Verzeichnissen; der produktive `data`-Ordner wird nicht verwendet.
Nach einmaliger Einrichtung starten mit `.\test-browser.ps1` oder
`python -m browser_tests`. Einrichtung, Fehlerartefakte und CI:
[BROWSER_TESTS.md](BROWSER_TESTS.md).

### Verlässliche YAML-Konfiguration

Die Priorität ist **APWorld-Standard → Vorlage → Spielerprofil → Lobby-Änderungen**.
Lobby-Werte haben immer Vorrang, auch explizite Rücksetzungen auf Standardwerte.
Hochgeladene YAMLs erscheinen als unveränderliche Presets. Eine Auswahl wird im
Lobby-Slot fixiert; Änderungen an der Vorlage gelten erst nach erneuter Auswahl.
Vorschau und Generator verwenden denselben vollständigen YAML-Export.
Details zur Prüfung, Migration und zu gewichteten Optionen:
[YAML_CONFIGURATION.md](YAML_CONFIGURATION.md).

### Persönliche Benutzerkonten

Jeder Spieler registriert sich mit Benutzername und eigenem Passwort, ohne
Einladungscode oder Mindestlänge. Bei leerem Benutzerbestand wird das erste Konto
automatisch Admin; alle weiteren Registrierungen erhalten Spielerrechte.
Bestehende Benutzer und Adminrechte bleiben erhalten; Altkonten vergeben ihr
erstes Passwort mit einem persönlichen Einrichtungscode vom Host.
Die Migration und die Einrichtung des bisherigen Admins sind in
[AUTH_MIGRATION.md](AUTH_MIGRATION.md) beschrieben. Die früheren Hinweise zur
gemeinsamen Anmeldung weiter unten sind damit abgelöst.

### Admin: Accounts, Runden und Seeds löschen

Unter **Admin → Accounts / Runden / Seeds verwalten** lassen sich einzelne
Datensätze nach Bestätigung löschen. Eine Runde umfasst dabei alle zugehörigen
Seeds, Analysen, Einladungen, Verbindungsdaten und lokalen Dateien. Ein einzelner
Seed kann separat gelöscht werden; seine Lobby bleibt erhalten. Extern gehostete
Archipelago-Räume werden dadurch nicht beendet.

Beim Account-Löschen werden Anmeldungen, Einrichtungscodes und Teilnahmen entfernt.
Runden, Seeds, Vorlagen, Spiel-Uploads und Anleitungen bleiben erhalten und gehen
an den ausführenden Admin über. Bestehende Seeds behalten ihre gespeicherten
Slotnamen. Die übrigen Teilnehmer betroffener Lobbys müssen sich erneut bereit
melden. Gelöschte Account-IDs werden nicht für Neuregistrierungen wiederverwendet.
Das eigene Admin-Konto und von laufenden Generierungen betroffene Daten können
nicht gelöscht werden. Normale Hosts können weiterhin nur Lobbys ohne Seed-Historie
löschen.

### Seed-Analyse: Übersicht und Spoiler

Die Analyse zeigt zunächst die Anzahl der Spiele, Spieler und platzierten Items.
Pro Spiel erscheinen die Items für seine Spieler, ihr Anteil an der Runde und
die Itemplatzierungen in seinen Welten. Mehrere Slots desselben Spiels werden
zusammengefasst; eine Aufschlüsselung nach Spielern ist aufklappbar.

**„Progression-Items pro Spiel“** listet die vom Generator als Progression
markierten Items mit Empfänger und Anzahl auf. Mehrere Exemplare desselben Items
für denselben Spieler werden zusammengefasst. **„Fundorte aufdecken“** lädt erst
beim Aufklappen den konkreten Check-Namen, Spieler und Spiel für jedes Exemplar.
Ohne JavaScript führt ein Link zur Fundort-Anzeige.

Erst **„Spoiler anzeigen & Details erkunden“** blendet die Verteilung zwischen
Spielern, Itemklassen und Links zu konkreten Itemlisten ein. Diese lassen sich
nach Empfänger oder Fundwelt durchsuchen, mit höchstens 50 Einträgen pro Seite.
Die Startansicht liefert weder Fundwelten noch konkrete Fundorte im HTML mit.

Die Spielseite zeigt unter „Check-Analyse“ die tatsächlich erfassten Checks mit
platziertem Item pro Spiel. Events, Startinventar und Item-Link-Gruppenslots werden
nicht gezählt. Der alte feste Hinweis auf fehlende Daten wurde entfernt; fehlende
Statistikdaten und Race-Modus werden anhand des jeweiligen Seeds angezeigt.

Neu erzeugte Seeds speichern neben `item_distribution.json` auch
`item_placements.json` mit Itemnamen, Fundorten und Empfängern. Die Detailansicht
prüft die Einträge gegen die aggregierten Zahlen. Für ältere Seeds ohne diese
Datei bleibt die Zusammenfassung nutzbar; konkrete Fundorte werden nicht
nachträglich rekonstruiert. Bestehende Seeds bleiben unverändert. Im Race-Modus
werden weiterhin keine Analysedateien erzeugt und keine Spoiler angezeigt.

**Start mit Custom-APWorlds:** `start.ps1` gibt die Ausführung aktivierter
Custom-APWorlds jetzt automatisch frei. Ein manuelles Setzen von
`HUB_TRUSTED_APWORLDS=1` ist bei diesem Startweg nicht mehr nötig.
Jeder Upload eines angemeldeten Mitspielers aktiviert und lädt die World
automatisch, ohne zusätzliche Vertrauensabfrage oder Admin-Freigabe pro Spiel.
Das gilt im Adminbereich und in der gemeinsamen Spielebibliothek.
Archivierte ältere Versionen können angemeldete Mitspieler direkt aktivieren.
Die Adminseite aktualisiert den Ladestatus automatisch. Bei Ladefehlern zeigt sie
das Protokoll an; ein Serverneustart ist für neue APWorlds nicht erforderlich.
Aktivierte APWorlds führen Python-Code mit den Rechten des Servers aus.
Mit `.\start.ps1 -NoCustomWorlds` bleibt diese Ausführung gesperrt.
Auch beim direkten Start über `python -m hub` sind aktivierte Custom-Worlds
standardmäßig freigegeben; `HUB_TRUSTED_APWORLDS=0` sperrt ihre Ausführung.
Dieser Ablauf ersetzt die älteren Hinweise zur Standardsperre und zur
Admin-Freigabe weiter unten.

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

Bei einer neuen Installation <http://127.0.0.1:8080/register> öffnen. Das erste
registrierte Konto wird automatisch Admin; weitere Konten sind normale Spieler.
Bei bestehenden Installationen stattdessen `setup-account` verwenden, siehe
[Kontomigration](AUTH_MIGRATION.md).

`setup.ps1` legt die Archipelago-Quellen (Standard: Version 0.6.8) und eine Python-Umgebung unter
`%USERPROFILE%\.ap-yaml-hub` an. Ein kurzer Pfad ist nötig, weil Windows sonst an zu langen Dateipfaden scheitert.
Ohne `-ImportFrom` werden keine APWorlds kopiert; die ladet ihr dann über die Admin-Seite hoch.

**Wichtig:** Die Archipelago-Version des Hubs sollte zu der passen, die eure Spieler lokal benutzen.
Mit `.\setup.ps1 -ApVersion 0.6.9` wechselt ihr die Version.

## Für die Gruppe freigeben

```powershell
.\start.ps1 -Public
```

Neue Spieler erstellen ihr Konto mit Benutzername und frei gewähltem, nicht leerem
Passwort. Es gibt keinen Einladungscode, keine Freigabe und keine Mindestlänge
für Passwörter. Nach der Registrierung ist man direkt angemeldet; später meldet
man sich mit denselben Zugangsdaten an. Außerhalb von localhost HTTPS verwenden und
`HUB_COOKIE_SECURE=1` setzen. Die APWorld-Ausführung bleibt auf dem privaten Host
ohne Sandbox; auch angemeldete Mitspieler können APWorlds hochladen.

## Wie es funktioniert

```
APWorld-Standard          ← was das Spiel mitbringt
  └─ Vorlage              ← Gruppe oder persönlich
       └─ Profil          ← "bei mir immer DeathLink aus"
            └─ Lobby      ← individuelle Änderungen für diese Runde
                 = YAML mit deinem Slot-Namen
```

- Explizite Vorlagenwerte bleiben erhalten, auch wenn sie dem APWorld-Standard entsprechen.
  Ein World-Update erfordert eine neue Prüfung der Bereitschaft.
- Ein Session-Eintrag besitzt eine fixierte Kopie der gewählten Vorlage.
  Für eine neue Fassung die Vorlage ausdrücklich erneut auswählen.
- Eine hochgeladene APWorld mit demselben Modulnamen wie ein eingebautes Spiel (z. B. `dark_souls_3.apworld`)
  ersetzt die eingebaute Version.
- Mehrere Einträge desselben Spielers in einer Session bekommen automatisch `Max`, `Max2` usw.

## Einstellungen (Umgebungsvariablen)

| Variable | Standard | Bedeutung |
|---|---|---|
| `AP_HOME` | `%USERPROFILE%\.ap-yaml-hub` | Ort für Archipelago-Quellen und Python-Umgebung |
| `HUB_DATA` | `.\data` | Datenbank, APWorlds, erzeugte Dateien |
| `HUB_COOKIE_SECURE` | `0` | `1` bei HTTPS: Session-Cookies nur verschlüsselt übertragen |
| `HUB_GENERATE_TIMEOUT` | `900` | Sekunden bis zum Abbruch der Generierung |

Alte Werte für `HUB_INVITE_CODE` und `HUB_PASSWORD` werden ignoriert. Bestehende
Konten und ihre Rechte bleiben erhalten. Für Altkonten ohne persönliches Passwort
bleibt die einmalige [Kontoeinrichtung](AUTH_MIGRATION.md) verfügbar.

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


## Community-Multiworld-Workflow (November 2026)

Diese Ausbaustufe setzt den gemeinsam abgestimmten Prototypen in der bestehenden Flask-Anwendung um. Alle Änderungen sind **additiv**: Vorhandene Benutzer, Spiele, YAML-Vorlagen, APWorld-Dateien, Seeds und Hosting-Einträge werden nicht überschrieben. Vor dem Update den gesamten lokalen Ordner `data/` sichern.

### 1. Anmelden und Übersicht

Der Nutzer meldet sich wie bisher an. Die Startseite zeigt die Anzahl vorhandener Spiele, offener Lobbys und registrierter Spieler. **Wichtig:** Die Anmeldung verwendet weiterhin Benutzername plus optionalem gemeinsamem Gruppenpasswort und ist gegen Identitätsübernahme innerhalb der Gruppe nicht hinreichend geschützt. Nicht öffentlich im Internet hosten.

### 2. Gemeinsame Spielebibliothek

Jeder angemeldete Spieler kann unter **Spielebibliothek → Spiel hinzufügen** ein Custom-Spiel einreichen:

- APWorld-Datei (maximal 20 MiB); die .apworld wird ohne Import und Codeausführung validiert und mit SHA-256 versioniert archiviert.
- Optional Spielname, HTTPS-Quellenlink und YAML-Vorlage (maximal 512 KiB, UTF-8, mit `name` und `game`).
- Die APWorld und YAML-Datei stehen angemeldeten Spielern als Download zur Verfügung. Alte Versionen bleiben archiviert. Bereits installierte und integrierte Archipelago-Spiele erscheinen ebenfalls im Katalog.
- **Ein neuer Upload ist zunächst inaktiv.** Der Host prüft die Herkunft und den Code, startet seine lokale Instanz bei bewusstem Vertrauen mit `HUB_TRUSTED_APWORLDS=1` und aktiviert die gewünschte Version. Erst dann kann das Spiel beim Archipelago-Schemaeinlesen geladen und in der Lobby gewählt werden.
- Diese Freigabe ist **KEINE Sandbox**. Custom APWorlds sind ausführbarer Python-Code, der auf dem Host mit dessen Rechten läuft. Auch vertraute Mitspieler können versehentlich fehlerhaften Code hochladen. Die sichere Isolation in einer OS-/VM-Sandbox bleibt offen.

Wird die optionale YAML-Vorlage hochgeladen, bleibt sie als **unverändertes Original** erhalten und kann heruntergeladen werden. Sie wird bewusst nicht ungeprüft zum aktiven Slot-Preset gemacht. Für spielbare Einstellungen liest der Host nach der Aktivierung die tatsächlichen Optionen der World ein; Vorlagen können mit der bestehenden YAML-Importfunktion weiterverarbeitet werden.

### 3. Offene Lobbys und Spielauswahl

**Lobbys** listet alle offenen und geschlossenen Runden für angemeldete Gruppenmitglieder auf. Jeder kann selbst eine Lobby erstellen. Eine offene Lobby lässt beliebig viele Beitritte zu – keine feste Teilnehmeranzahl und kein Einladungscode erforderlich. Der bisherige optionale Einladungslink bleibt aus Kompatibilitätsgründen erhalten.

Ablauf: **Mitmachen → direkt in die Lobby, zunächst ohne Spiel → unter „Deine Spielauswahl“ ein Spiel und eine Vorlage wählen → „YAML erstellen / bearbeiten“ → Einstellungen prüfen und ändern → „Auswahl übernehmen“ → Bereitschaft bestätigen**. Auch eine neu erstellte Lobby beginnt ohne Spielslot.

Der YAML-Editor öffnet sich direkt in der Lobby. Vorschau, Download, Zurücksetzen und Abbrechen ändern die gespeicherte Auswahl nicht. Erst „Auswahl übernehmen“ speichert Spiel, fixierte Vorlage und Einstellungen gemeinsam und setzt die Bereitschaft zurück. Pro Spieler wird in einer neuen Lobby **ein aktiver Spielslot** geführt. Ein Wechsel aktualisiert den bestehenden Slot, statt einen zweiten zu erzeugen; die bisherige Auswahl bleibt bis zur Übernahme erhalten.

Der Host darf den Seed nur erzeugen, wenn **alle beigetretenen Mitspieler ein Spiel gewählt haben** und sämtliche vorhandenen Slots nach der Konfigurationsprüfung bereit sind. Wer noch kein Spiel gewählt hat, wird in der Lobby gesondert angezeigt. Die Generierung schließt die Lobby; sie kann nach einem erfolgreichen Seed nicht wieder geöffnet werden. Für weitere Mitspieler oder eine neue Konfiguration eine neue Runde erstellen bzw. klonen.

### 4. Seed-Analyse und echte Itemverteilung

Nach einer erfolgreichen Generierung: **Seed-Historie → Seed-Analyse**. Ein eigener Menüpunkt **Seed-Analyse** listet die verfügbaren Builds.

Die Analyse verwendet **keine Demo-Zahlen** und liest keine beliebigen fremden ZIP-Pickles. Stattdessen erhält der bereits für die Generierung eingesetzte Archipelago-Unterprozess das vollständige MultiWorld-Objekt von `Main.main`, zählt dessen tatsächlich platzierte, adressierte Items und schreibt die **aggregierten** Daten als `item_distribution.json` neben dem Seed-ZIP. Das Flask-Backend übernimmt diese JSON-Statistik in den Build-Datensatz.

Anzeige:
- Anzahl der Spieler, echte gezählte Itemplatzierungen, Crossworld-Items und deren Anteil.
- **Item-Matrix:** Zeilen = Spiel/Welt des Fundorts; Spalten = Empfänger. Diagonale = Items in der eigenen Welt.
- **Itemklassen:** Progression, Useful, Trap und Filler pro Empfänger.
- Es werden ausschließlich platzierte Items mit numerischen Location-/Item-IDs berücksichtigt. Event-Locations, Startinventar und gesonderte Item-Link-Gruppen-Slots sind **nicht enthalten**; daraus folgt, dass „Itemplatzierungen“ nicht zwangsläufig alle internen Spiele-Checks umfassen.
- **Race-Modus:** Analytics ist absichtlich deaktiviert, um spoilerhaltige Itemplatzierungen nicht offenzulegen.
- Fehlende oder ältere Seed-Daten: `Keine verifizierten Statistikdaten verfügbar`, keine geschätzten Werte.

### 5. Hosting und lokaler Test

Der Hosting-Ablauf bleibt wie zuvor: ZIP vom Host herunterladen → auf https://archipelago.gg/uploads hochladen → dort `Create Room` → echte Host-/Portdaten und optional Raum-URL im Hub speichern. Es gibt keine behauptete offizielle Upload-API.

Unter „Aktive Lobby“ bestätigt jeder Spieler mit „Ich bin fertig“, dass er sein
Spielziel für alle eigenen Slots erreicht hat. Das ist eine manuelle Bestätigung;
der Hub liest keinen Live-Spielabschluss vom Archipelago-Server. Bis alle fertig
sind, kann man mit „Ich spiele doch noch“ die eigene Bestätigung zurücknehmen.
Wenn alle Seed-Teilnehmer bestätigt haben, wird die Runde im Hub abgeschlossen
und aus den aktiven Lobbys entfernt. Seed, Analyse und Downloads bleiben erhalten;
der externe Archipelago-Server wird nicht gestoppt. Der Host kann die Lobby zur
Vorbereitung einer neuen Runde wieder öffnen; abgeschlossene Seeds bleiben archiviert.

Unter Windows im geklonten Projektordner (vorher `data/` sichern):

```powershell
git pull
py -3.13 -m unittest discover -s tests -v
.\start.ps1
```

Teste danach mit mindestens zwei getrennten Browser-Sessions die Registrierung, Bibliotheks-Uploads, Host-Freigabe, offenen Beitritt, Slotoptionen, Bereitschaft und Seed-Analyse. Die automatisierten GitHub-Tests verwenden einen **Mock-Generator**; die echte Multiworld-Generierung und statistische Ausgabe mit euren Custom APWorlds muss auf deinem Windows-Host geprüft werden.

Die Website ist weiterhin für ein **privates, vertrauenswürdiges LAN oder VPN** gedacht, nicht für ungeschütztes Internet. Die gemeinsame Anmeldung ist keine eigenständige, sichere Benutzeridentität. Eigenständige Passwörter, HTTPS, Rate-Limits und echte Ausführungsisolation sind für öffentlichen Betrieb erforderlich.
