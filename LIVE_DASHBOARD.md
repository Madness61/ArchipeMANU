# Live-Dashboard

Das Dashboard ergänzt die aktive Lobby um Übersicht, Spieler, Interaktionen,
Verlauf, Ereignisse und Vergleiche. Der Präsentationsmodus zeigt das Cockpit
ohne Hauptnavigation; Browser-Vollbild ist optional. Seed-Analyse und persönliche
„Ich bin fertig“-Bestätigungen bleiben eigenständige Funktionen.

## Raum verbinden

1. Seed im Hub generieren.
2. Multiworld-ZIP manuell bei Archipelago hochladen und einen Raum erstellen.
3. Unter „Generierte Runden“ oder „Jetzt spielen / Verbindung“ den vollständigen
   HTTPS-Link in „Archipelago-Raum für Live-Statistiken“ eintragen.
4. „Raum verbinden“ wählen. Alle Teilnehmer erreichen anschließend über
   „Aktive Lobby“ und „Live-Dashboard öffnen“ die gemeinsame Auswertung.

Portfelder sind dafür nicht erforderlich. Der Hub ermittelt Trackerkennung und
letzten gemeldeten Port. Die Raum-API liefert **keinen Server-Hostnamen**:
Für die offizielle Website wird archipelago.gg verwendet. Abweichende Adressen
lassen sich weiterhin manuell eintragen. Manuelle Verbindungen überschreibt
der Collector nicht.

Bereits gespeicherte gültige Raumlinks werden beim Start übernommen. Die
Aufzeichnung beginnt mit dem ersten erfolgreichen Abruf. Es werden keine
Spielbefehle gesendet und keine Raumseiten zum Aufwecken von Servern aufgerufen.

## Verifizierte API

- [Offizielle API-Dokumentation](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/webhost%20api.md)
- [Raum-API: Quellcode](https://github.com/ArchipelagoMW/Archipelago/blob/main/WebHostLib/api/room.py)
- [Tracker-APIs: Quellcode](https://github.com/ArchipelagoMW/Archipelago/blob/main/WebHostLib/api/tracker.py)
- [ClientStatus und NetworkItem](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md)

| Endpunkt | Gelieferte / verwendete Daten |
| --- | --- |
| /api/room_status/{room_id} | Trackerkennung, geordnete Namens-/Spielliste, letzter Port und letzte Raumaktivität. |
| /api/tracker/{tracker_id} | Erledigte Location-IDs, Empfangslisten, Aliase, Clientstatus und Aktivitäts-/Verbindungszeitpunkte. |
| /api/static_tracker/{tracker_id} | Gesamtchecks und Spiele pro Team/Slot; Gruppen zählen nicht als Spieler. |
| /api/slot_data_tracker/{tracker_id} | Verfügbarkeit geprüft; im Betrieb nicht abgefragt, weil beliebige spielspezifische Daten unnötig sind und spoilern können. |

Der dynamische Tracker wird upstream 60 Sekunden, der statische 300 Sekunden
gecacht. Diese Grenzen werden eingehalten.

Am 08.11.2026 antworteten alle vier Endpunkte des angegebenen Beispielraums mit
HTTP 200. Die implementierte Berechnung ergab fünf Spieler, fünf Spiele,
0 erledigte von 2.347 Gesamtchecks und 0 erreichte Ziele. Das ist ein damaliger
Messstand, keine Aussage über spätere Änderungen.

## Kennzahlen

- **Gesamtfortschritt:** Summe erledigter Checks geteilt durch Gesamtchecks.
  Zusätzlich wird das ungewichtete Mittel der Slot-Prozente gezeigt.
- **Ziele:** ClientStatus 30 bedeutet vom Spielclient gemeldetes Ziel.
  Hundert Prozent Checks ersetzen diese Meldung nicht. Fehlender Status bleibt unbekannt.
- **Empfangen:** Anzahl gültiger Einträge in der Empfangsliste des Servers,
  einschließlich möglicher Sonderfälle. Dies ist kein Spielinventar und
  kein Beweis einer lokalen Zustellung.
- **Interaktionen:** Empfangseinträge werden einem Finder nur bei gleichem
  Team und passendem erledigtem Check zugeordnet. Doppelte Finder-/Location-/
  Empfänger-Bezüge zählen einmal. Eigenwelt und Fremdwelt bleiben getrennt.
- **Nicht zugeordnet:** Startinventar, negative Sonderlocations, Gruppenbezüge
  und unbestätigte Finder-Checks erscheinen nicht als normale Matrix-Kanten.
  Item-Links können mehrere Empfangsmeldungen aus einem Check erzeugen:
  Gezählt werden Meldungen pro Empfänger, keine einzigartige Seed-Verteilung.
- **Zuwachs:** Differenzen realer Beobachtungen im aktuellen Verlaufabschnitt.
  Der Stundenvergleich nutzt den letzten verfügbaren Stand vor der Grenze oder
  den Aufzeichnungsbeginn und nennt seinen tatsächlichen Vergleichsbeginn.
- **Ereignisse:** Check-/Empfangszuwachs, Ziel-/Statusmeldungen und
  25-/50-/75-/100-Prozent-Schwellen entstehen durch Snapshot-Vergleiche.
  Beobachtungszeit und Vergleichsintervall werden angezeigt, keine erfundenen
  exakten Zeitpunkte von Spielaktionen.

Nicht verfügbar sind verlässliche aktuelle Online-Präsenz, echte aktive
Spielzeit, lokale Inventare, Check-Schwierigkeit und rückwirkende Historie.
Letzte Verbindung/Aktivität sind keine Heartbeats. Itemnamen und zukünftige
Fundorte erscheinen im normalen Dashboard nicht.

Der Race-Modus blendet Empfangszahlen, Itemklassen, Beziehungen und Itemereignisse
auch in JSON und historischen Messpunkten aus. Namen aus der Raumliste werden
nur bei lückenlosen Slotnummern und passenden Spielzuordnungen übernommen;
sonst gilt der Alias oder eine neutrale Slotbezeichnung. Abweichungen zwischen
Raum und lokalem Seed werden angezeigt. Statische Seed-Platzierungen fließen
niemals in die Live-Berechnungen ein.

## Aktualisierung und Speicherung

Ein zentraler Hintergrund-Collector prüft fällige Verbindungen und sammelt etwa
alle 60 Sekunden, auch ohne geöffneten Browser. Er startet mit python -m hub
oder beim ersten Dashboardzugriff im WSGI-Betrieb.

Browser lesen den gemeinsamen Backend-Stand alle 30 Sekunden, beim ersten Abruf
oder einem fälligen Refresh kurzzeitig häufiger. „Jetzt aktualisieren“ liest
denselben Cache und weckt den Collector; API-Cachegrenzen werden nicht umgangen.
SQLite-Leases bündeln gleichzeitige Zugriffe pro Raum und API-Endpunkt auch
über mehrere Browser, Räume und Serverprozesse.

Bei Ausfällen bleibt der letzte erfolgreiche Stand erhalten. Timeouts,
HTTP 404/403/429, fehlende Tracker und unvollständige Antworten werden behandelt.
Rate-Limits und fehlende Räume führen zu längeren Pausen.

Jede neue erfolgreiche Beobachtung erhält einen Snapshot. Unveränderte Werte
bilden echte Ruhephasen ab, erzeugen aber keine doppelten Ereignisse. Sinkende
Checkzahlen oder eine neue Trackerkennung beginnen einen neuen Verlaufabschnitt.
Kurven verbinden keine unterschiedlichen Abschnitte.

Die Historie bleibt in SQLite erhalten. Lange Zeiträume zeigen höchstens etwa
420 ausgewählte echte Messpunkte. Tooltips, Zeitregler und Datentabelle bieten
Details. Es werden keine historischen Zwischenwerte gespeichert oder erfunden.

Ein anderer Raumlink erhält eine eigene Historie; frühere Aufzeichnungen werden
nicht mit dem neuen Raum vermischt. Nach dem manuellen Rundenabschluss endet
die Sammlung. Seed-/Rundenlöschung entfernt zugehörige Live-Verbindungen,
Snapshots und Ereignisse per Fremdschlüssel-Kaskade. Der API-Cache ist gemeinsam
und enthält keine Hints, Slotdaten, Downloadlisten oder Datapackages.

Alle Migrationen sind additiv. Benutzer, Seeds, YAML-Werte und manuelle
Verbindungen bleiben erhalten. Keine neuen Python-Abhängigkeiten und keine
externen JavaScript-CDNs sind erforderlich.

## Sicherheit

Nur Host oder Administrator ändern Links. Dashboard und JSON benötigen
Mitgliedschaft oder Verwaltungsrechte; eine lediglich sichtbare offene Lobby
genügt nicht. Schreibende Aktionen verlangen CSRF-Tokens.

Erlaubt sind nur HTTPS-Raumlinks von archipelago.gg bzw. www.archipelago.gg mit
kanonischer 22-stelliger SUUID, ohne Port, Zugangsdaten, Query oder Fragment.
Der Client konstruiert drei feste offizielle API-URLs, folgt keinen
Weiterleitungen und verwendet TLS-Prüfung, 8 Sekunden Timeout und ein 12-MiB-
Antwortlimit. Beliebige externe URLs sind nicht abrufbar.

## Tests

    $env:PYTHONPATH='tests'
    .venv/Scripts/python.exe -m unittest discover -s tests -q
    .venv-browser/Scripts/python.exe -m browser_tests

API-geformte Fixtures prüfen TTLs, parallele Abrufe, Mehrspieler-/Teamdaten,
Beziehungen, fehlende Werte, ungestartete und fehlende Räume, Ausfälle,
Race-Modus, CSRF, Berechtigungen, Reset-Erkennung und persistente Historie.

Der Browser-Test verwendet zwei getrennte Spieler, alle sechs Ansichten,
Raumlink ohne Portfelder, Tooltip, gemeinsame Aktualisierung, Fehlerzustand,
Präsentationsmodus und mobile Darstellung. Er läuft ausschließlich an einem
isolierten temporären Testserver; Archipelago-Ausführung und WebHost sind gemockt.

Validierungsstand vom 08.11.2026: 162 Funktionstests und alle 9 Chromium-
Browser-Szenarien bestanden. Der gezielte Live-Browsertest wurde nach den
abschließenden Darstellungsanpassungen erneut erfolgreich ausgeführt.
