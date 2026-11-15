# Verbindungen und Wiederherstellung

Vier voneinander unabhängige Verbindungen werden unterschieden:

| Verbindung | Verhalten |
| --- | --- |
| Browser → Hub | Ein ausgeblendeter Tab pausiert UI-Polling. Nicht gesendeter Text bleibt beim Nachladen der Daten erhalten. HTTP 401 zeigt die erneute Anmeldung; POST-Befehle werden nicht wiederholt. |
| Hub → WebHost-API | Gemeinsamer SQLite-Cache mit Leases, 60 s für dynamische und 300 s für statische Daten. Fehler lassen den letzten Fortschritt als veraltet sichtbar. Retry-After wird als Sekunden oder HTTP-Datum berücksichtigt. |
| Hub → Archipelago-Textserver | Nur ausdrücklich gestartete Verbindungen. Ein Worker hält den Socket unabhängig vom Browser und prüft mindestens alle fünf Sekunden Anmeldung, Mitgliedschaft, Seed-Abschluss, Race-Regeln und aktuelle Raumverknüpfung. |
| Lokaler Spielclient → Archipelago | Vom Hub nicht zuverlässig messbar; Verbindungszustand bleibt unbekannt. Eine verbundene Textkonsole bestätigt keine Spielverbindung. |

## Zustandsmodell der Textkonsole

`connecting → authenticating → connected`

Vorübergehende Socket-, DNS-, Timeout-, Ping- und Handshakefehler führen zu
`reconnecting`, nach mehreren erfolglosen Versuchen zu `temporarily_unavailable`.
Der nächste Versuch wartet exponentiell ab zwei Sekunden, mit Jitter und einer
Obergrenze von 60 Sekunden. Auch während des Wartens wird die Berechtigung geprüft.
Nach einer mindestens 60 Sekunden stabilen Verbindung beginnt die Fehlerfolge neu.
Der achtsekündige TCP-Verbindungsaufbau-Timeout wird vor Übergabe des Sockets an
den WebSocket-Reader entfernt. Sonst beendet websockets 13.x bei unverschlüsseltem
WS auch eine gesunde, aber ruhige Verbindung nach acht Sekunden ohne Daten.

Falsches Raumpasswort, ungültiger Slot, Seed-/Spielerabweichung, ungültige Pakete
oder ein nicht überprüfbares TLS-Zertifikat führen zu `action_required`.
Explizites Trennen, Logout, Ablauf der Anmeldung, Rechteentzug, Abschluss und
Änderung des gespeicherten Raums beenden den Worker. Keine Anmeldung an fremden
Slots; keine automatische erneute persönliche Anmeldung nach einer solchen Beendigung.

Die Verbindungsdiagnose zeigt Zustand, letzten Paketkontakt, Wiederholungsversuch
und nächsten Termin. Protokolle enthalten keine Passwörter oder rohen Fehlerpakete.
Das Raumpasswort bleibt für notwendige Wiederanmeldungen nur während der ausdrücklich
aktivierten Verbindung im Arbeitsspeicher und wird am Ende verworfen. Nach einem
Prozessneustart ist für persönliche Chatverbindungen eine erneute ausdrückliche Verbindung erforderlich.

## Optionale Rundenaufzeichnung (15.11.2026)

Der Host kann unabhängig von seiner persönlichen Chatverbindung einen nur lesenden
TextOnly-Client aktivieren. Freigabe und Slot sind ausdrücklich bestätigt. Verwendet
wird ausschließlich ein eigener Spielslot des freigebenden Hosts oder Administrators;
ein Host ohne eigenen Slot kann keine fremde Identität verwenden. Der Recorder sendet
keine Chats, Hinweise, Spielchecks, Ziele oder Speicherabfragen. Private Servertexte,
Chats und Hint-Antworten werden vom Recorder verworfen. Datenpakete dienen nur der
Auflösung von Item- und Location-IDs; Slotdaten werden nicht angefordert.

Die Freigabe, Slot, UUID, Transport und Diagnose stehen additiv in
`console_recordings`. Ein Passwort bleibt nur im Arbeitsspeicher. Der Recorder prüft
weiterhin Hostrechte, eigenen Slot, Seed, Race-Regeln, Abschluss und aktuelle
Verknüpfung. Logout beendet persönliche Verbindungen, die bewusst freigegebene
Aufzeichnung läuft weiter. Beenden der Aufzeichnung widerruft ihre Freigabe.

Beim Start des Hubs übernimmt ein Supervisor bestehende Freigaben. SQLite-Leases
(20 Sekunden, regelmäßige Erneuerung) verhindern parallele Recorder verschiedener
Prozesse. Nach einem Prozessabbruch kann die Wiederaufnahme entsprechend warten.
War der Raum passwortgeschützt, wird die Aufzeichnung mit einer konkreten Meldung
angehalten; der Host muss das Passwort erneut eingeben. Ein Raumwechsel oder
fehlende Rechte erfordern ebenfalls eine neue bewusste Freigabe. Normale
Socketunterbrechungen und API-Portwechsel desselben Raums werden automatisch behandelt.

## Automatischer Portwechsel bei Archipelago-Räumen

Ein gültiger offizieller Raumlink zusammen mit `archipelago.gg` verwendet beim
Speichern standardmäßig den API-Port. Die Host-Option „Port manuell festlegen“
schaltet diese Übernahme ausdrücklich ab. Eigene Serveradressen bleiben manuell.
Bei bereits früher manuell gespeicherten Verbindungen muss die Automatik einmal
über den Raumlink oder durch Speichern ohne diese Option aktiviert werden.

Der Collector übernimmt einen gültigen `last_port` direkt nach dem Raumstatus-Abruf,
auch wenn der Tracker nicht verfügbar ist. Dynamische API-Abrufe behalten ihren
60-Sekunden-Cache und API-Fehler ihren Backoff. Ungültige oder fehlende Ports löschen
die letzte gültige Adresse nicht. Ein API-Port bestätigt keine Erreichbarkeit und
startet keinen schlafenden Archipelago-Raum.

Eine Portänderung desselben Raums aktualisiert die bestehende Verknüpfung und
setzt die frühere manuelle Verbindungsbestätigung zurück. Dadurch bleiben Verlauf
und Deduplizierung erhalten. Der ausdrücklich gestartete Text-Worker erkennt die
Änderung auch ohne Browser-Polling, schließt den bisherigen Socket, verwirft
ausstehende Befehle und verbindet sich erneut. Seed und Teilnehmer werden neu
geprüft; das Passwort bleibt ausschließlich im Arbeitsspeicher. Das gilt auch
während der Wiederholungsversuche nach einer Verbindungsablehnung.

Server-/Port-Anzeige und Kopierziele folgen den neuen Daten ohne Seitenreload.
Ein anderer Raum, eine manuell neu gespeicherte Verbindung oder Rechteentzug
beenden weiterhin den alten Worker. Lokale Spielclients müssen Spieler selbst
auf den neuen Port umstellen.

## Nachrichten und Lücken

Jeder neue Socket prüft Seed und Teilnehmer neu und synchronisiert die Empfangsliste
sowie Server-Checks. ItemSend-Meldungen werden anhand gespeicherter Ereignisschlüssel
dedupliziert. Unterbrechungen und Wiederherstellung stehen im persönlichen Protokoll.
Eine synchronisierte Empfangsliste ersetzt kein vollständiges ItemSend-Archiv.
`ReceivedItems` bestätigt nur die Empfänge des angemeldeten Slots. Normale Einträge
mit bekanntem Sender und positivem/Null-Location-Identifier können ergänzt werden.
Sie erscheinen als **nachträglich bestätigt · Fundzeit unbekannt**. Startinventar,
synthetische negative Locations und nicht zuordenbare Einträge erzeugen keine
erfundenen Sendungen. Dieselbe Ereignisidentität dedupliziert Live-Meldungen und
Empfangsbestätigungen auch über mehrere Leser und Neustarts hinweg.

Die Empfangsreihenfolge wird pro Slot gespeichert; daraus entsteht keine globale
Fundreihenfolge. `at` ist stets der Beobachtungs-/Bestätigungszeitpunkt im Hub,
kein rückgerechneter Fundzeitpunkt. Eine nachträglich bestätigte Sendung kann
deshalb nach neueren Live-Meldungen in der Beobachtungsreihenfolge stehen.

Chatnachrichten und Befehle werden einmal gesendet. Ausstehende Befehle werden beim
Socketwechsel verworfen und nicht automatisch erneut eingereiht. Bei unklarem
Versandstatus entscheidet der Benutzer, ob er eine Aktion erneut senden möchte.

Der gemeinsame Item-Feed sammelt belegte Sendungen berechtigter Leser. Es gibt
keine anonyme oder fremde Beobachteranmeldung. Private Antworten persönlicher
Textverbindungen bleiben pro Benutzer getrennt; die optionale Host-Aufzeichnung
erfasst ausschließlich gemeinsame Item-Ereignisse und eigene Betriebsmarkierungen.

`console_events` wird nicht mehr automatisch bei 10.000 Nachrichten gekürzt.
HTTP-Abfragen bleiben auf 100 Einträge pro Seite begrenzt, Listen und Frames auf
ihre bestehenden Sicherheitslimits. Frühere, bereits vor diesem Update abgeschnittene
Einträge sind ohne neue Belege nicht wiederherstellbar. Explizite administrative
Löschaktionen bleiben unverändert; dieses Update löscht keine bestehenden Daten.

`console_streams` hält den Zustand der Leser und Heartbeats. Gemeinsame Lücken-
und Wiederaufnahmemarkierungen entstehen bei Wechseln zwischen null und mindestens
einem aktiven Leser, nicht bei jedem einzelnen Spielerwechsel. Nach einem abrupten
Prozessausfall ist der genaue Unterbrechungsbeginn unbekannt; die nächste Aufnahme
markiert die mögliche Lücke ausdrücklich.

## Unabhängige Diagnose

Die Konsole zeigt Aufzeichnungsstatus und letzten erfassten Item-Zeitpunkt kompakt.
Der ausklappbare Bereich nennt Browser-/Hub-Erreichbarkeit und letzten erfolgreichen
HTTP-Kontakt, API-Abruf und Cache-/Fehlerzustand, geplante Aktualisierung, persönliche
Textverbindung und ihren letzten Kontakt/Reconnect sowie den separaten Recorder.
Der lokale Spielclient bleibt unbekannt. Diagnoseabfragen lesen den gemeinsamen
Cache; sie lösen keine zusätzlichen Upstream-Abrufe aus. Fehler behalten den
letzten erfolgreichen Datenstand. Nachweis einer Textverbindung und API-Erreichbarkeit
bleiben voneinander unabhängig.

## Produktgrenze

Der experimentelle Universal-Logik-Tracker wird nicht mehr aufgerufen oder importiert.
Seine alten URLs beantworten berechtigte Anfragen mit HTTP 410 und einem Hinweis;
sie starten keine Worker, Downloads oder Platzierungsabfragen. Historischer Code
bleibt für Nachvollziehbarkeit erhalten. WebHost-Fortschritt, Seed-Analysen,
Standard-Check-Vorschau und `/received`, `/missing`, `/hint` bleiben verfügbar.

## Diagnose

1. Bei einem Browserfehler die Hub-Erreichbarkeit und eigene Anmeldung prüfen.
2. Bei API-Fehlern den als veraltet gekennzeichneten Fortschritt berücksichtigen;
   dies sagt nichts über die Textkonsole aus.
3. Bei `reconnecting` den nächsten Versuch abwarten. Nicht mehrfach manuell verbinden.
4. Bei `action_required` Raum, Port, Slot und Passwort prüfen und bewusst neu verbinden.
5. Nach einem Raumwechsel den aktuellen Raum verbinden und eine Aufzeichnung neu
   freigeben. Nach einem Hub-Neustart die persönliche Chatverbindung erneut starten;
   ein geschützter Recorder benötigt das Raumpasswort erneut.

## Validierung und Grenzen

Automatische Prüfungen verwenden isolierte Daten und einen lokalen AP-Protokollserver:
Handshake, Unterbrechung/Wiederverbindung, Empfangssynchronisation, Deduplizierung,
einmaligen Chatversand, explizites Trennen, Rechte-/Abschlussänderung während des
Backoffs, Passwort-/Seedfehler und simulierte Browserinaktivität über 30 Minuten.
API-Prüfungen verwenden kontrollierte 429/5xx-, Cache-, Timeout- und Trackerantworten.
Der vollständige Feinschliff-Lauf vom 15.11.2026 umfasst 243 erfolgreiche Python-
Tests und 20 erfolgreiche Playwright-Szenarien. Dazu gehören echte lokale Sockets,
kurze und wiederholt fehlschlagende Wiederverbindungen, Deduplizierung mit alten
Ereignisschlüsseln und geänderten Klassifizierungsflags, mehr als 10.000 bleibende
Einträge, Recorderrechte und Passwort-Neueingabe sowie ein tatsächlicher Neustart
des isolierten Hub-Prozesses. Nach dem Start gelten alte persistierte
„verbunden“-Zustände ohne frischen Heartbeat nicht als aktive Verbindung.
Das ist kein realer Mehrspieler-Langzeittest mit installierten Spielclients oder
einer tatsächlichen WLAN-/Hamachi-Unterbrechung; diese manuelle Abnahme bleibt offen.

Protokollgrundlage: [Archipelago-Netzwerkprotokoll](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md).
Socket-Lebenszyklus: [websockets-Sync-Client](https://websockets.readthedocs.io/en/13.1/reference/sync/client.html).
