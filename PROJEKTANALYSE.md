# Projektanalyse vom 6. November 2026

## Architektur und Features

ArchipeMANU ist eine Flask-Anwendung mit SQLite und serverseitigen Jinja-Templates.
`hub/app.py` enthält Anmeldung, Vorlagen, Profile, Session-Routen und Administration.
Die Blueprints `community.py` und `mvp.py` ergänzen die gemeinsame Bibliothek,
offene Lobbys, Einladungen, Slotoptionen, Bereitschaft, Seed-Historie, Hostingdaten
und Spielanleitungen. `yamlgen.py` kapselt Formularverarbeitung, Optionsprüfung,
YAML-Import/-Export und die Zusammenführung von Optionen.

`apworld_library.py` prüft ZIP-Strukturen ohne Codeimport und archiviert APWorlds
nach SHA-256 in einem eigenen SQLite-Katalog. Die Anwendungsdatenbank bleibt davon
getrennt. `ap_bridge.py` synchronisiert aktive Archive und serialisiert
Schemaextraktion und Generierung mit einem Prozess-Lock. `ap_runner.py` läuft im
Archipelago-Unterprozess und liest die tatsächlichen World-Optionen aus. Bei der
Generierung aggregiert `stats.py` adressierte Itemplatzierungen nach Fundwelt,
Empfänger und Itemklasse. Race-Seeds veröffentlichen keine Verteilungsstatistik.

Die Trennung vom Archipelago-Import ist sinnvoll. Die Grenzen zwischen den beiden
SQLite-Datenbanken, Archivdateien, Schema-Cache und Hintergrundthreads sind jedoch
die wichtigsten Fehlerquellen: Änderungen sind nicht über alle Speicher hinweg
atomar. Die globale Flask-Instanz und Pfadkonstanten erschweren außerdem den Betrieb
mehrerer unabhängig konfigurierter Instanzen im selben Prozess.

## Behobene Fehler

| Bereich | Fehler und Änderung |
|---|---|
| Bibliothek | Ein identischer APWorld-Upload konnte eine bereits gespeicherte YAML überschreiben, während der Datenbankeintrag unverändert blieb. Duplikate werden unter dem AP-Lock abgewiesen. Original-YAMLs werden exklusiv und bytegenau gespeichert, einschließlich BOM und Zeilenenden. |
| Lobby-Klon | Die Mitgliedschaften wurden nicht mitkopiert. Damit fehlten Teilnehmer ohne Spiel in der Preflight-Prüfung; kopierte Spieler konnten ihre Auswahl nicht regulär wechseln. Der Klon übernimmt Mitglieder, Slotbesitzer und den neuen Host. Geschlossene fremde Lobbys lassen sich nicht mehr ohne Zugriffsrecht klonen. |
| Sloteditor | Beim Bearbeiten eines fremden Slots benutzte der Host sein eigenes Profil und seinen Slotnamen. Der Editor verwendet jetzt den tatsächlichen Besitzer. |
| Löschen | Sessions mit Builds verursachten einen Fremdschlüsselfehler. Sie bleiben nun mit verständlicher Rückmeldung erhalten; auch fehlgeschlagene Builds gehören zur Historie. Leere Sessions einschließlich Einladungen bleiben löschbar. |
| SQLite | `with sqlite3.Connection` schließt die Verbindung nicht. Migrationen und Worker hielten deshalb unter Windows Datenbankdateien offen. Ein eigener Transaktionskontext garantiert Commit/Rollback und Schließen. |
| APWorld-Synchronisierung | Dateigröße und Zeitstempel konnten geänderte Archivbytes übersehen. Nun entscheidet SHA-256 über die Aktualisierung. |
| APWorld-Deaktivierung | Bereits kopierte Worlds blieben im Archipelago-Ladeverzeichnis. Eine Verwaltungsdatei erfasst nun Hub-Kopien. Deaktivierte unveränderte Kopien werden unter `.hub-inactive` aufbewahrt; manuell veränderte Kopien blockieren den Lauf statt überschrieben oder entfernt zu werden. |
| Statistik | Die bisherige Prüfung akzeptierte unvollständige oder widersprüchliche JSON-Daten und konnte beim Rendern abstürzen. Backend und Import prüfen jetzt Spieler, Matrix, Kategorien sowie Zeilen-, Spalten- und Gesamtsummen. Fehlerhafte Daten führen zur Anzeige fehlender Statistik, ohne einen erfolgreichen Seed zu verwerfen. |
| Browser | Ein Aufruf von `$` statt des definierten `$$` brach das gesamte Skript ab. Kopierbuttons, Formularkomfort und Statusaktualisierung können wieder initialisieren. |

## Tests und Datenerhalt

Die ursprünglichen 25 Tests wurden um 9 Regressionstests ergänzt. Die 34 Tests
decken unter anderem Archivvalidierung und Versionswechsel, Bibliotheks-Uploads,
Lobbyzugriff, Mitgliedschaften, Bereitschaft, Slotbesitzer, Seed-Snapshots,
manuelles Hosting, Statistik-Konsistenz und Datenbank-Rollback ab.

Ausgeführt unter Windows mit Python 3.15 und einer lokalen `.venv`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Alle Anwendungstests verwenden temporäre Datenverzeichnisse oder Mock-Daten.
Der echte `data`-Ordner wurde bei dieser Analyse nicht angelegt, migriert,
überschrieben oder gelöscht. Die vorhandene unversionierte Datei
`.github/copilot-instructions.md` wurde nicht verändert. `.venv/` ist jetzt ignoriert.

## Grenzen der Prüfung und weitere Architekturarbeit

- Ein echtes Archipelago-Setup war hier nicht verfügbar. Generierung, reale
  APWorld-Optionen und Statistikextraktion sind deshalb nicht durch einen echten
  Multiworld-Lauf bestätigt. Die vorhandenen Integrationstests verwenden einen
  Fake-Generator. Die CI nutzt Python 3.13; der lokale Lauf erfolgte mit 3.15.
- Der JavaScript-Fehler wurde im Quellcode korrigiert. Ein interaktiver Browserlauf
  gehört nicht zu dieser Verifikation.
- Die neue APWorld-Verwaltungsdatei kann nur künftig erfasste Kopien sicher als
  Hub-Dateien erkennen. Alte, bisher nicht erfasste Dateien im externen
  `Archipelago/custom_worlds` bleiben zum Schutz manueller Installationen erhalten.
- Schema-Cache und APWorld-Versionierung sollten künftig explizit über den
  Archivhash verbunden werden. Die aktuelle World-Prüfung schützt die Archivbytes
  während der Generierung; die Schemaextraktion ist ein separater Schritt.
- Die Thread-Locks koordinieren einen Serverprozess. Für mehrere Workerprozesse
  wären eine persistente Jobwarteschlange und prozessübergreifende Sperren nötig.
- Benutzername plus Gruppenpasswort und Custom-World-Unterprozesse behalten die
  bereits dokumentierten Vertrauensgrenzen: individuelle Identitäten und eine
  OS-/VM-Isolation sind damit nicht umgesetzt.
