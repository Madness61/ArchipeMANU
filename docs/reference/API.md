# Archipelago-Konsole und JSON-API

Konsole als Hauptansicht laufender Runden; unveränderte Befehle und Endpunkte.

## Benutzung

1. Eine laufende Runde unter **Meine Runden** öffnen. Die erste Ansicht ist **Konsole**.
2. Der Host hinterlegt den tatsächlichen Archipelago-Spielserver und Port.
3. Der gemeinsame Leser verbindet sich automatisch. Verlauf und öffentliche Meldungen
   sind ohne persönliche AP-Anmeldung sichtbar. Nur bei geschützten Räumen hinterlegt
   der Host das gemeinsame **Raumpasswort** in den optionalen Raumeinstellungen.
4. Die Transporterkennung versucht zuerst WSS und bei einem inkompatiblen Transport WS.
   Ungültige TLS-Zertifikate führen zum Abbruch. Der Host kann WS/WSS ausdrücklich wählen.
   Persönliche Befehle werden bei Bedarf über den zugeordneten eigenen Seed-Slot gesendet;
   nur bei mehreren eigenen Slots ist die optionale Befehls-Zielauswahl nötig.
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
| `POST /command` | `text` genügt für die automatische Befehlsverbindung. Bei mehreren eigenen Slots ist `slot` optional. Eine explizit per `/connect` aufgebaute Verbindung ist weiterhin verwendbar |
| `POST /recording/start` | Host/Admin: `automatic=1`, `transport`, optional `password` aktualisieren den gemeinsamen Leser; kein eigener Slot nötig. Alte Aufrufe mit eigenem `slot` und `consent=1` bleiben gültig |
| `POST /recording/stop` | Host/Admin: gemeinsamen Leser ausdrücklich pausieren; über die Raumeinstellungen wieder aktivierbar |

Ohne Cursor werden die letzten 100 sichtbaren Nachrichten geladen. `after`
und `before` dürfen nicht zusammen gesetzt werden. `kind` erlaubt `all`,
`items`, `chat`, `system`, `sent`, `for_me`, `from_me`, `others`.

Die API verwendet die bestehende Anmeldung. POST benötigt `_csrf` oder den
Header `X-CSRF-Token`. Die Serveradresse stammt ausschließlich aus dem vom Host
gespeicherten Datensatz. `202` bestätigt die Annahme eines Befehls, nicht dessen
Ausführung im Spiel. API-Fehler enthalten einen HTTP-Fehlerstatus und `error`.
`GET /data` meldet zusätzlich `transport` (`ws`, `wss` oder vor dem Aufbau `null`).
Die bisherigen Top-Level-Verbindungsfelder beschreiben aus Kompatibilitätsgründen
die persönliche Verbindung; `room_connection` enthält den Status des gemeinsamen
Lesers. `players` ordnet tatsächliche Slotnamen den Website-Konten zu. Persönliche
Ereignisse enthalten bei bekannter Zuordnung `actor`; `packet_type` kennzeichnet
typisierte persönliche Serverantworten. Öffentliche Ereignis-IDs sind für alle
Besucher gleich, Markierungen `for_me`/`from_me` bleiben benutzerspezifisch.
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
  Universal-Logikberechnung. Der gemeinsame Leser fordert keine Slotdaten an.
  Kein APWorld-Import im Webprozess und kein Shellzugriff über Befehle.
- Vor Befehlen werden Seedname, Spielerslots, Spiele und der eigene Slot geprüft.
  Lokale Seeds verwenden Team 0. Abweichende Räume werden abgelehnt.
- Automatische persönliche Verbindungen synchronisieren vor dem ersten Befehl
  Inventar und Datenkatalog. Da AP leere `ReceivedItems` unterdrückt, dient die
  nach `Sync` angeforderte Katalogantwort als geordnete Synchronisierungsgrenze.
  Nach zwei Minuten ohne Befehle wird die persönliche Verbindung freigegeben.
- Der Leser speichert Sendungen aus `PrintJSON/ItemSend` und belegte Empfänge
  seines verifizierten Seed-Slots. Automatische Befehlsverbindungen speichern
  persönliche Antworten und können Inventar für die Progression liefern.
  Mehrere verbundene Spieler erzeugen für denselben Check keine Duplikate.
- Ein vollständiges vergangenes Serverlog ist nicht abrufbar. Empfangsbestätigungen
  werden ausdrücklich als nachträglich erkannt markiert, ohne Fundzeitpunkt.
  Startinventar und synthetische negative Locations erzeugen keine Sendungen.
  `/received` zeigt weiterhin die eigene vollständige Empfangsliste einschließlich
  Startinventar; `/missing` liefert offene Checks, keine Erreichbarkeitsberechnung.
- Strukturierte Item-Sendungen sowie öffentliche Typen `Chat`, `ServerChat`, `Join`,
  `Part`, `TagsChanged`, `Goal`, `Countdown`, `Release`, `Collect`, `ItemCheat` sind
  gemeinsam sichtbar. Persönliche Hinweise und Befehlsantworten bleiben privat.
  Nicht eindeutig öffentliche oder untypisierte Meldungen des Lesers werden nicht
  geteilt; bestehende persönliche Nachrichten bleiben persönlich. Ein Wechsel der
  gespeicherten Serververbindung trennt den alten Verlauf von der aktuellen
  Ansicht. Im Race-Modus ist die Konsole gesperrt.
  Normale Chatnachrichten gehen weiterhin in den Archipelago-Raum und können
  dort für andere verbundene Spielclients sichtbar sein.
- Das Raumpasswort bleibt nur im Arbeitsspeicher der Verbindung; es steht nicht
  in Datenbank, URL oder Protokoll. Formularübertragung erfolgt per POST.
- Logout, abgelaufene Sitzung, entzogene Lobbyrechte, abgeschlossene Runde und
  geänderte Verknüpfung beenden die persönliche Verbindung. Bei transienten
  Ausfällen verbindet sich der Client erneut. Ausstehende Befehle werden verworfen.
- Der gemeinsame Leser läuft unabhängig von Browser und Login über einen verifizierten
  Seed-Slot ausschließlich lesend weiter. SQLite-Leases schützen die
  Wiederaufnahme nach einem Hub-Neustart. Passwortgeschützte Räume erfordern dann
  erneute Eingabe durch den Host; Passwörter werden nicht gespeichert. Der Leser
  führt keine Benutzerbefehle aus. Eigene Befehls-Slots stammen ausschließlich aus
  dem eingefrorenen Seed-Snapshot. Details und Grenzen:
  [CONNECTION_RELIABILITY.md](../OPERATIONS.md).
- Höchstens 32 Verbindungen im einzelnen Waitress-Prozess. Persönliche Verbindungen
  werden beim nächsten Befehl wieder aufgebaut; das SQLite-Protokoll bleibt erhalten.
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
| `GET /items` | `q`, `category=all/progression/useful/filler/trap`, `owner=all/mine`, `status=all/checked/unchecked/unknown`, `page`, `limit=1..50` (Standard 50, Inline-Suche 5) |
| `GET /analysis` | Eigener `slot`, `mode=items/goal`; liest Cache/Status, startet nichts |
| `POST /analysis` | Dieselben Felder; startet ausdrücklich einen begrenzten, separat gecachten Auftrag |

Die optionale eingeklappte Check-/Bereichsauswahl verwendet `target_kind/target_id/target_name`. Sie wird validiert und mit den bereits berechneten Check-/Regionsmengen verglichen (`target_reachable`, je Einzelitem `target_reached`). Sie startet keine zusätzliche Ziel-, Paar- oder Kandidatensuche und verändert die Sortierung nicht.

Itemantworten nennen Empfänger, Finder/Welt, konkreten Check, Itemklasse, getrennten Check-/Empfangsstatus und jeweiligen Beobachtungszeitpunkt. Itemresultate enthalten `singles`, `singles_tested`, `candidates_total`, `singles_complete`, `reachable`, `regions`, `targets`; keine Paar-/Notwendigkeitsarbeit. Zielresultate enthalten separat `goal_reachable`, `necessity`, `necessity_total`, `necessity_complete`.

## WebHost-API und Standard-Check-Vorschau

`hub/live_api.py` liest die offizielle WebHost-API; dynamischer Cache standardmäßig 60 s, statischer 300 s, Fehler lassen zuletzt gute Werte als veraltet erhalten. Benutzt werden Roomstatus, dynamischer und statischer Tracker. Keine kompletten vergangenen Sendungslogs und keine lokale Spielzustandsprüfung. [Offizielle Protokollquelle](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md).

`GET /api/games/<slug>/checks` liest Cache/Status; erst POST startet den Standard-Probelauf (Anmeldung, CSRF, Rate-Limit, AP-Lock). Referenzseed 20261110 mit APWorld-Standard ohne Profil/Lobby. Gezählt werden adressierte gefüllte Itemchecks, keine Events/Startitems. 120 s Timeout und versionsabhängiger Cache; es entstehen keine spielbaren Seeddateien oder Hub-Lobbys. Andere Optionen/Versionen können andere Zahlen liefern.

[Funktionen](../FEATURES.md), [Betrieb und Diagnose](../OPERATIONS.md), [Tests](../DEVELOPMENT.md).
