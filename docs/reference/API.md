# Archipelago-Konsole und JSON-API

Konsole als Hauptansicht laufender Runden; unveränderte Befehle und Endpunkte.

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
Dateien und Abschluss folgen darunter, Fortschritt und offene Server-Checks bleiben direkt
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
| `GET /commands` | Befehle mit Beschreibung in der Kontosprache |
| `GET /data?after=ID&kind=items` | Neue sichtbare Nachrichten, höchstens 100 |
| `GET /data?before=ID` | Frühere Nachrichten, chronologisch sortiert |
| `POST /connect` | Formularfelder `slot`, `password` optional, `transport` = `auto` (Standard), `ws` oder `wss` |
| `POST /disconnect` | Eigene Textverbindung trennen |
| `POST /command` | Formularfeld `text`; bei `/connect` optional auch Verbindungsfelder |
| `POST /recording/start` | Nur Host/Admin mit eigenem Slot: `slot`, `transport`, optional `password`, ausdrücklich `consent=1` |
| `POST /recording/stop` | Nur Host/Admin: dauerhafte Aufzeichnungsfreigabe beenden |

Ohne Cursor werden die letzten 100 sichtbaren Nachrichten geladen. `after`
und `before` dürfen nicht zusammen gesetzt werden. `kind` erlaubt `all`,
`items`, `chat`, `system`, `sent`, `for_me`, `from_me`, `others`.

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
`source=received_items` kennzeichnet nachträglich belegte Empfänge des angemeldeten
Slots; `receipt_index` ist deren Reihenfolge innerhalb seiner Empfangsliste.
`source=live` beziehungsweise fehlendes `source` bei älteren Einträgen bezeichnet
beobachtete ItemSend-Meldungen. Gleiche Ereignisse bleiben einmalig, auch wenn
Live-Meldung und Empfangssynchronisierung beide eintreffen.

`GET /data` ergänzt `recording` und `webhost` mit unabhängigen Zustandsinformationen.
Die Browser-/Hub-Erreichbarkeit wird im Browser gemessen; der lokale Spielclient
bleibt unbekannt. `journal_limit=null` bedeutet ungekürzte persistente Historie;
die unveränderte API-Seitengröße ist weiterhin 100.

## Identität, Daten und Grenzen

- Eigenständiger serverseitiger WebSocket-Client: `TextOnly`,
  `items_handling=7`, `slot_data=true`, unterstützte Protokollversion 0.6.8.
  Eigene Slotdaten persönlicher Verbindungen bleiben im Arbeitsspeicher und
  werden nicht im gemeinsamen Protokoll veröffentlicht. Es gibt keine aktive
  Universal-Logikberechnung. Der optionale Recorder fordert keine Slotdaten an.
  Kein APWorld-Import im Webprozess und kein Shellzugriff über Befehle.
- Vor Befehlen werden Seedname, Spielerslots, Spiele und der eigene Slot geprüft.
  Lokale Seeds verwenden Team 0. Abweichende Räume werden abgelehnt.
- Gemeinsame Sendungen stammen aus tatsächlichen `PrintJSON/ItemSend`-Paketen
  oder eindeutig belegten normalen `ReceivedItems` des angemeldeten Slots.
  Mehrere verbundene Spieler erzeugen für denselben Check keine Duplikate.
- Ein vollständiges vergangenes Serverlog ist nicht abrufbar. Empfangsbestätigungen
  werden ausdrücklich als nachträglich erkannt markiert, ohne Fundzeitpunkt.
  Startinventar und synthetische negative Locations erzeugen keine Sendungen.
  `/received` zeigt weiterhin die eigene vollständige Empfangsliste einschließlich
  Startinventar; `/missing` liefert offene Checks, keine Erreichbarkeitsberechnung.
- Nur strukturierte Item-Sendungen sind gemeinsam sichtbar. Chat und Antworten,
  insbesondere Hinweise, werden pro Benutzer gespeichert. Ein Wechsel der
  gespeicherten Serververbindung trennt den alten Verlauf von der aktuellen
  Ansicht. Im Race-Modus ist die Konsole gesperrt.
  Normale Chatnachrichten gehen weiterhin in den Archipelago-Raum und können
  dort für andere verbundene Spielclients sichtbar sein.
- Das Raumpasswort bleibt nur im Arbeitsspeicher der Verbindung; es steht nicht
  in Datenbank, URL oder Protokoll. Formularübertragung erfolgt per POST.
- Logout, abgelaufene Sitzung, entzogene Lobbyrechte, abgeschlossene Runde und
  geänderte Verknüpfung beenden die persönliche Verbindung. Transiente Ausfälle
  werden automatisch wiederholt; Browserinaktivität beendet sie nicht.
- Die ausdrücklich aktivierte Host-Aufzeichnung läuft unabhängig von Browser und
  Login über einen eigenen freigegebenen Slot weiter. SQLite-Leases schützen die
  Wiederaufnahme nach einem Hub-Neustart. Passwortgeschützte Räume erfordern dann
  erneute Eingabe; Passwörter werden nicht gespeichert. Keine fremden Slots,
  keine Chat-/Befehlsaufzeichnung durch den Recorder. Details und Grenzen:
  [CONNECTION_RELIABILITY.md](../OPERATIONS.md).
- Maximal 32 Verbindungen im einzelnen Waitress-Prozess. Nach einem Neustart
  die persönliche Chatverbindung neu verbinden; das SQLite-Protokoll bleibt erhalten.
  Recorder werden über gemeinsame SQLite-Leases koordiniert; der gesamte
  Mehrprozessbetrieb persönlicher Chatverbindungen ist nicht Teil dieser Abnahme.
- Additive Tabellen: `console_events`, `console_packages`, `console_streams` und
  `console_recordings`. Bestehende Konten, Vorlagen, APWorlds und Seeds werden nicht
  überschrieben. Keine automatische Kürzung der Historie, 100 Einträge pro API-Seite.
  Bereits früher automatisch gelöschte Ereignisse lassen sich ohne Belege nicht
  wiederherstellen. Namen werden über Datenpakete
  aufgelöst; unbekannte Namen bleiben ausdrücklich `Item #ID` oder `Check #ID`.
- Eingaben, Frames, Listen und Warteschlangen sind begrenzt; Kontolimits schützen
  Verbindungen und Befehle. DNS wird fest aufgelöst; Metadaten-/Link-Local-Ziele
  werden abgelehnt. Eigene lokale Spielserver bleiben nutzbar.
- Servertexte werden als Text angezeigt, niemals als ausführbares HTML.

Quellen: [Archipelago-Protokoll 0.6.8](https://github.com/ArchipelagoMW/Archipelago/blob/0.6.8/docs/network%20protocol.md),
[offizieller Textclient](https://github.com/ArchipelagoMW/Archipelago/blob/0.6.8/CommonClient.py),
[WebSocket-Bibliothek](https://websockets.readthedocs.io/en/13.1/reference/sync/client.html).


## Progression-API

Präfix: `/sessions/<sid>/builds/<build_id>/progression`. Alle Antworten privat/no-store. Teilnahme, erfolgreiche Runde und Race-Regeln werden serverseitig geprüft.

| Methode/Pfad | Bedeutung |
| --- | --- |
| `GET /state` | Datenverfügbarkeit und persönliche Spoilerfreigabe |
| `POST /consent` | `reveal=1/0`; persönliche Freigabe/Widerruf, mit CSRF |
| `GET /items` | `q`, `category=all/progression/useful/filler/trap`, `owner=all/mine`, `status=all/checked/unchecked/unknown`, `page` |
| `GET /analysis` | Eigener `slot`, `mode=items/goal`; liest Cache/Status, startet nichts |
| `POST /analysis` | Dieselben Felder; startet ausdrücklich einen begrenzten, separat gecachten Auftrag |

Alte `target_kind/target_id/target_name`-Parameter bleiben validiert und cache-kompatibel, lösen aber keine Paar-Kandidatensuche aus. Die normale Oberfläche benötigt diese technischen Zielparameter nicht.

Itemantworten nennen Empfänger, Finder/Welt, konkreten Check, Itemklasse, getrennten Check-/Empfangsstatus und jeweiligen Beobachtungszeitpunkt. Itemresultate enthalten `singles`, `singles_tested`, `candidates_total`, `singles_complete`, `reachable`, `regions`, `targets`; keine Paar-/Notwendigkeitsarbeit. Zielresultate enthalten separat `goal_reachable`, `necessity`, `necessity_total`, `necessity_complete`.

## WebHost-API und Standard-Check-Vorschau

`hub/live_api.py` liest die offizielle WebHost-API; dynamischer Cache standardmäßig 60 s, statischer 300 s, Fehler lassen zuletzt gute Werte als veraltet erhalten. Benutzt werden Roomstatus, dynamischer und statischer Tracker. Keine kompletten vergangenen Sendungslogs und keine lokale Spielzustandsprüfung. [Offizielle Protokollquelle](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md).

`GET /api/games/<slug>/checks` liest Cache/Status; erst POST startet den Standard-Probelauf (Anmeldung, CSRF, Rate-Limit, AP-Lock). Referenzseed 20261110 mit APWorld-Standard ohne Profil/Lobby. Gezählt werden adressierte gefüllte Itemchecks, keine Events/Startitems. 120 s Timeout und versionsabhängiger Cache; es entstehen keine spielbaren Seeddateien oder Hub-Lobbys. Andere Optionen/Versionen können andere Zahlen liefern.

[Funktionen](../FEATURES.md), [Betrieb und Diagnose](../OPERATIONS.md), [Tests](../DEVELOPMENT.md).
