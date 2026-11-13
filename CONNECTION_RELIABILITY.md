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
Slots; keine automatische erneute Anmeldung nach einer solchen Beendigung.

Die Verbindungsdiagnose zeigt Zustand, letzten Paketkontakt, Wiederholungsversuch
und nächsten Termin. Protokolle enthalten keine Passwörter oder rohen Fehlerpakete.
Das Raumpasswort bleibt für notwendige Wiederanmeldungen nur während der ausdrücklich
aktivierten Verbindung im Arbeitsspeicher und wird am Ende verworfen. Nach einem
Prozessneustart ist eine erneute ausdrückliche Verbindung erforderlich.

## Nachrichten und Lücken

Jeder neue Socket prüft Seed und Teilnehmer neu und synchronisiert die Empfangsliste
sowie Server-Checks. ItemSend-Meldungen werden anhand gespeicherter Ereignisschlüssel
dedupliziert. Unterbrechungen und Wiederherstellung stehen im persönlichen Protokoll.
Eine synchronisierte Empfangsliste ersetzt kein vollständiges ItemSend-Archiv:
fehlende Sendungen während eines Ausfalls werden nicht rekonstruiert.

Chatnachrichten und Befehle werden einmal gesendet. Ausstehende Befehle werden beim
Socketwechsel verworfen und nicht automatisch erneut eingereiht. Bei unklarem
Versandstatus entscheidet der Benutzer, ob er eine Aktion erneut senden möchte.

Der gemeinsame Item-Feed sammelt bestätigte Sendungen ausdrücklich verbundener,
berechtigter Mitglieder. Eine zusätzliche Beobachteranmeldung wurde bewusst nicht
eingeführt: Sie würde ohne vorhandene separate Beobachterberechtigung ein anderes
Slotmodell voraussetzen. Private Antworten bleiben pro Benutzer getrennt.

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
5. Nach einem Raumwechsel den aktuellen Raum verbinden. Nach einem Hub-Neustart
   bestehen keine automatisch wiederhergestellten Textanmeldungen.

## Validierung und Grenzen

Automatische Prüfungen verwenden isolierte Daten und einen lokalen AP-Protokollserver:
Handshake, Unterbrechung/Wiederverbindung, Empfangssynchronisation, Deduplizierung,
einmaligen Chatversand, explizites Trennen, Rechte-/Abschlussänderung während des
Backoffs, Passwort-/Seedfehler und simulierte Browserinaktivität über 30 Minuten.
API-Prüfungen verwenden kontrollierte 429/5xx-, Cache-, Timeout- und Trackerantworten.
Das ist kein realer Mehrspieler-Langzeittest mit installierten Spielclients oder
einer tatsächlichen WLAN-/Hamachi-Unterbrechung; diese manuelle Abnahme bleibt offen.

Protokollgrundlage: [Archipelago-Netzwerkprotokoll](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md).
Socket-Lebenszyklus: [websockets-Sync-Client](https://websockets.readthedocs.io/en/13.1/reference/sync/client.html).
