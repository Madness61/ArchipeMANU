# Archipelago-Konsole und JSON-API

Stand: 10. November 2026 · Konsole als Hauptansicht laufender Runden.

## Benutzung

1. Eine laufende Runde unter **Meine Runden** öffnen. Die erste Ansicht ist **Konsole**.
2. Der Host hinterlegt den tatsächlichen Archipelago-Spielserver und Port.
3. In der Konsole den eigenen Slot wählen und gegebenenfalls das
   **Raumpasswort** eingeben. Das ist nicht das persönliche Benutzerpasswort.
4. **Mit Archipelago verbinden** drücken. **Automatisch** versucht zuerst
   verschlüsseltes WSS (auch für archipelago.gg) und bei einem inkompatiblen
   Transport unverschlüsseltes WS. Ungültige TLS-Zertifikate führen zum Abbruch.
   Die gewählte Verbindung wird im Status angezeigt; WS/WSS bleiben manuell wählbar.
5. Item-Sendungen mit Finder, Empfänger, Item und konkretem Check lesen oder
   eine Nachricht schreiben. **Befehl einfügen** oder Tippen von `/` (auch `!`)
   öffnet passende Vorschläge. Auswahl füllt nur das Feld; erst **Senden** führt
   den Befehl aus. Die Auswahl ist auch per Pfeiltasten, Enter und Escape bedienbar.

Die gemeinsame Jinja-Komponente `console_workspace.html` wird in der Rundenzentrale
und auf der bisherigen Konsolen-Detailseite verwendet. In Vorbereitung bleibt die
Spielauswahl vorn; in einer Runde mit hinterlegter Verbindung erhält die Konsole
den Vorrang und die Dashboard-Hauptaktion lautet „Konsole öffnen“. Spielstart,
Dateien und Abschluss folgen darunter, Fortschritt und Logik bleiben direkt
erreichbar. Race-Runden erhalten keine Konsole; abgeschlossene Runden behalten
das lesbare Archiv über die Detailansicht. Die bestehende Daten- und Rollenlogik
bleibt erhalten. Beim Wechsel der gespeicherten Verbindung wird der angezeigte
Verlauf neu geladen, statt Meldungen zweier Verbindungen zu vermischen.

Die Konsole ist ein zusätzlicher Textclient. Sie ersetzt den Spielclient nicht,
bestätigt keine Checks und sendet keine Spielziel-Meldungen. Ein Beobachter ohne
eigenen Spielslot darf das gemeinsame Itemprotokoll lesen, aber keine Befehle
als fremder Spieler senden, auch nicht als Administrator.

## Befehle

| Eingabe | Funktion |
|---|---|
| `/help` | Hilfe der Webkonsole; auch ohne Textverbindung |
| `/connect` | Gespeicherter Server und eigener Slot; freie Adressen werden hier nicht angenommen |
| `/disconnect`, `/exit` | Nur die Textverbindung trennen |
| `/received [Filter]` | Empfangsliste des eigenen Slots laut Server, einschließlich gemeldetem Startinventar |
| `/missing [Filter]` | Offene Checks des eigenen Slots laut Server, nicht aus dem lokalen Spielspeicher |
| `/items [Filter]`, `/locations [Filter]` | Namen aus dem Datenkatalog des Servers |
| `/hint [Item]` | Wird als `!hint` an den Server gesendet |
| `/hint_location [Check]` | Wird als `!hint_location` gesendet |
| `/status`, `/players` | Entsprechende Serverbefehle |
| Text ohne Präfix | Chat über `Say` |

Direkte Serverbefehle: `!help`, `!hint`, `!hint_location`, `!status`, `!players`,
`!remaining`, `!countdown`. Der Server bestimmt Unterstützung, Berechtigungen
und Hint-Kosten. Verwaltungs-, Cheat- und Spiel-Check-Pakete werden nicht gesendet.
Listen zeigen höchstens 200 passende Einträge und lassen sich mit Text filtern.

## JSON-API

Basis: `/sessions/{sid}/builds/{build_id}/console`.

| Methode und Pfad | Bedeutung |
|---|---|
| `GET /` | Konsolenseite |
| `GET /commands` | Befehle mit deutscher Beschreibung |
| `GET /data?after=ID&kind=items` | Neue sichtbare Nachrichten, höchstens 100 |
| `GET /data?before=ID` | Frühere Nachrichten, chronologisch sortiert |
| `POST /connect` | Formularfelder `slot`, `password` optional, `transport` = `auto` (Standard), `ws` oder `wss` |
| `POST /disconnect` | Eigene Textverbindung trennen |
| `POST /command` | Formularfeld `text`; bei `/connect` optional auch Verbindungsfelder |

Ohne Cursor werden die letzten 100 sichtbaren Nachrichten geladen. `after`
und `before` dürfen nicht zusammen gesetzt werden. `kind` erlaubt `all`,
`items`, `chat`, `system`, `sent`.

Die API verwendet die bestehende Anmeldung. POST benötigt `_csrf` oder den
Header `X-CSRF-Token`. Die Serveradresse stammt ausschließlich aus dem vom Host
gespeicherten Datensatz. `202` bestätigt die Annahme eines Befehls, nicht dessen
Ausführung im Spiel. API-Fehler enthalten einen HTTP-Fehlerstatus und `error`.
`GET /data` meldet zusätzlich `transport` (`ws`, `wss` oder vor dem Aufbau `null`).
Die automatische Transporterkennung erfolgt vor der Slot-Anmeldung. Bei falschem
Raumpasswort oder abgelehnter Slot-Anmeldung wird kein anderer Transport versucht.

Item-Ereignisse liefern neben `id`, `kind`, `at`, `visibility` und `text` ein
strukturiertes `delivery` mit `item_id`, `item`, `sender: {name,game}`,
`recipient: {name,game}`, `location: {id,name}`. Der Zeitpunkt ist die Beobachtung
durch den Hub, kein nachträglich bestimmter Fund- oder Zustellzeitpunkt.

## Identität, Daten und Grenzen

- Eigenständiger serverseitiger WebSocket-Client: `TextOnly`,
  `items_handling=7`, `slot_data=true`, unterstützte Protokollversion 0.6.8.
  Eigene Slotdaten bleiben im Arbeitsspeicher und ermöglichen die separate
  Logikberechnung; sie werden nicht im gemeinsamen Protokoll veröffentlicht.
  Kein APWorld-Import im Webprozess und kein Shellzugriff über Befehle.
- Vor Befehlen werden Seedname, Spielerslots, Spiele und der eigene Slot geprüft.
  Lokale Seeds verwenden Team 0. Abweichende Räume werden abgelehnt.
- Gemeinsame Sendungen stammen aus tatsächlichen `PrintJSON/ItemSend`-Paketen.
  Mehrere verbundene Spieler erzeugen für denselben Check keine Duplikate.
- Ein vollständiges vergangenes Serverlog ist nicht abrufbar. Gemeinsame
  Sendungen werden ab der ersten verbundenen Konsole aufgezeichnet. `/received`
  synchronisiert die Empfangsliste des eigenen Slots; daraus werden keine
  Sendungszeiten oder weltweite Historien erfunden.
- Nur strukturierte Item-Sendungen sind gemeinsam sichtbar. Chat und Antworten,
  insbesondere Hinweise, werden pro Benutzer gespeichert. Ein Wechsel der
  gespeicherten Serververbindung trennt den alten Verlauf von der aktuellen
  Ansicht. Im Race-Modus ist die Konsole gesperrt.
  Normale Chatnachrichten gehen weiterhin in den Archipelago-Raum und können
  dort für andere verbundene Spielclients sichtbar sein.
- Das Raumpasswort bleibt nur im Arbeitsspeicher der Verbindung; es steht nicht
  in Datenbank, URL oder Protokoll. Formularübertragung erfolgt per POST.
- Logout, abgelaufene Sitzung, entzogene Lobbyrechte, abgeschlossene Runde und
  geänderte Serveradresse beenden die Verbindung. Netzverlust erfordert eine
  erneute Verbindung. Nach 30 Minuten ohne offene Konsole wird sie beendet.
- Maximal 32 Verbindungen im einzelnen Waitress-Prozess. Nach einem Neustart
  neu verbinden; das SQLite-Protokoll bleibt erhalten. Mehrprozess-Betrieb
  benötigt einen gemeinsamen Worker und wird hier nicht behauptet.
- Additive Tabellen: `console_events` und `console_packages`. Bestehende Konten,
  Vorlagen, APWorlds und Seeds werden nicht überschrieben. Letzte 10.000
  Nachrichten pro Runde, 100 pro API-Seite. Namen werden über Datenpakete
  aufgelöst; unbekannte Namen bleiben ausdrücklich `Item #ID` oder `Check #ID`.
- Eingaben, Frames, Listen und Warteschlangen sind begrenzt; Kontolimits schützen
  Verbindungen und Befehle. DNS wird fest aufgelöst; Metadaten-/Link-Local-Ziele
  werden abgelehnt. Eigene lokale Spielserver bleiben nutzbar.
- Servertexte werden als Text angezeigt, niemals als ausführbares HTML.

Quellen: [Archipelago-Protokoll 0.6.8](https://github.com/ArchipelagoMW/Archipelago/blob/0.6.8/docs/network%20protocol.md),
[offizieller Textclient](https://github.com/ArchipelagoMW/Archipelago/blob/0.6.8/CommonClient.py),
[WebSocket-Bibliothek](https://websockets.readthedocs.io/en/13.1/reference/sync/client.html).

## Tests

`python -m unittest discover -s tests -v` und `python -m browser_tests`.
Temporäre Datenbanken, Mock-Generator und eigener lokaler WebSocket-Protokollserver;
kein fremder Raum wird kontaktiert, keine APWorld ausgeführt und keine Nachricht
an echte Spieler gesendet. Tests für Anmeldung, Passwörter, Seedprüfung,
Item-Sendungen, Deduplizierung, Befehle, private Hinweise, Rechte/CSRF, Race-Schutz,
Cursor, Aufbewahrung, Logout, sichere Textanzeige und Mobilansicht.

Ergebnis nach der Transportkorrektur: 181 Python-Tests erfolgreich (58,8 Sekunden)
und der betroffene Konsolen-Browserablauf erfolgreich (17,1 Sekunden), einschließlich
erneuter Verbindung nach falschem Raumpasswort und Entfernen der Fehlermeldung.
Regressionen prüfen automatische WSS-Auswahl, WS-Fallback vor Anmeldung,
Zertifikatsfehler ohne Fallback, manuelle Auswahl und verständliche Fehler.
Der vorherige Browser-Gesamtlauf bestand mit 12 Szenarien (114,8 Sekunden).
Desktop- und Mobil-Screenshots zeigen ausschließlich isolierte Testdaten.
