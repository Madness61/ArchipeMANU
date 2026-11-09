# Logik-Tracker

Einstieg: Live-Dashboard → Logik-Tracker oder Archipelago-Konsole →
Erreichbare Checks & Go-Mode. Spieler verbinden zuvor ihren eigenen Slot
in der bestehenden Textkonsole. Die Spielverbindung bleibt unabhängig.

Der Tracker verwendet Universal Tracker 0.3.3 aus dem Projekt
https://github.com/FarisTheAncient/Archipelago/releases/tag/Tracker_v0.3.3.
Das separate Archiv unter data/logic_tools wird gegen den veröffentlichten
SHA-256 a909f96404b0009865d39b87cec8bb749446783577d77bd4fa14431cef0c2140
geprüft. Es wird nicht als wählbares Spiel installiert. Zusätzlicher APWorld-Code
unterliegt derselben Vertrauensfreigabe wie die vorhandene Archipelago-Laufzeit.
Ein Admin kann die festgelegte Version über die Oberfläche einrichten.

## Daten und Berechnung

- Eigene serverseitige Empfangsliste inklusive Startinventar, offene und
  erledigte Check-IDs sowie eigene Slotdaten aus der Textverbindung.
- Datenkatalog des Servers, unveränderte Spieler-YAML aus dem Seed-Snapshot
  und passende lokale APWorld-Version. YAML-Hash, APWorld-Archiv und gespiegelte
  Version werden geprüft.
- Universal Tracker rekonstruiert die Spielregeln in einem separaten Prozess.
  Es wird kein neuer Seed gefüllt und keine Itemverteilung an die Engine gegeben.
- Erreichbarkeit kommt aus der APWorld-CollectionState. Go-Mode kommt aus deren
  Zielbedingung, nicht aus Check-Prozent oder Itemanzahl. Ein erreichbares Ziel
  ist noch kein vom Spielclient bestätigter Abschluss.
- Die rekonstruierten Check-IDs müssen mit dem Server übereinstimmen. Fehler,
  fehlende Daten und Versionsabweichungen liefern keinen erfundenen Logikstatus.

Berechnungen laufen auf ausdrückliches Aktualisieren. Gleiche Eingaben werden
aus dem Cache bedient; neue Items oder Checks machen die alte Berechnung ungültig.
Die Oberfläche prüft den Status alle fünf Sekunden. Höchstens zwei Prozesse,
vier ausstehende Aufgaben und 90 Sekunden pro Prozess begrenzen die Last.

## API

Basis: /sessions/{sid}/builds/{build_id}/live/logic

| Endpunkt | Bedeutung |
| --- | --- |
| GET Basis | Persönliche Tracker-Oberfläche |
| GET /data?slot=NAME | Berechnung oder ehrlicher Datenzustand |
| POST /refresh, slot=NAME | Aktuellen Serverstand berechnen |
| POST /placements, slot=NAME | Iteminhalte ausdrücklich aufdecken |
| POST /install | Admin: feste Engine-Version herunterladen und prüfen |

POST verwendet die bestehende CSRF-Prüfung. Antworten sind no-store.
Nur der im Seed gespeicherte Besitzer eines Slots kann dessen Daten anfragen.
Race-Runden sind vollständig gesperrt. Iteminhalte stehen nie in /data;
sie benötigen eine gesonderte Anfrage und aktivierte Spoiler im Seed.
Verbindungen werden niemals anhand einer frei eingegebenen URL aufgebaut.

## Grenzen

Universal Tracker benötigt je nach Spiel passende Slotdaten, YAML und
UT-Unterstützung der APWorld. Insbesondere zufällige Weltverbindungen können
zusätzliche, vom Spiel gemeldete Daten benötigen. Noch unbekannte Verbindungen
werden angezeigt. Unvollständige oder nicht unterstützte Modelle bleiben
unbekannt. Der Hub liest keinen lokalen Spielspeicher und behauptet keine
lokale Itemzustellung. Nicht jede APWorld unterstützt UT oder Go-Mode zuverlässig.

Tests verwenden isolierte Konten und Testdaten. Ein erfolgreicher UI-/API-Test
ersetzt keinen Test aller unterstützten Spiele mit echten Spielclients.
