> Historischer Stand bis 17.11.2026. Keine aktive Anleitung oder Aufgabenliste. Aktuell: [Dokumentation](../DEVELOPMENT.md).

# Rundenzentrale und vereinfachte Navigation

Die bestehende Dark-Gaming-Gestaltung bleibt erhalten. Die Oberfläche richtet
sich nach Aufgaben und dem Zustand der Runde statt nach technischen Modulen.

## Einstieg und Navigation

- Drei Hauptbereiche: **Übersicht**, **Meine Runden**, **Spiele entdecken**.
- Profil und Administration bleiben unten getrennt.
- `/rounds` und der bisherige Link `/lobbies` zeigen dieselbe Übersicht.
  Eigene Runden stehen getrennt nach Vorbereitung, laufend und abgeschlossen.
  Offene fremde Lobbys erscheinen einmal unter den offenen Gruppenlobbys.
- Auf der Übersicht erscheint jede Runde höchstens einmal. Die hervorgehobene
  Karte verlinkt in die Rundenzentrale und zeigt eine passende Hauptaktion.

## Eine Oberfläche pro Runde

`/sessions/<sid>` ist der primäre Einstieg. Vier Bereiche wechseln per
URL-Fragment ohne Dokumentnavigation: **Konsole** (bei laufender verknüpfter Runde, sonst **Spielen**), **Fortschritt**,
**Mitspieler**, **Mehr**. Zurück/Vorwärts, direkte Fragmentlinks, Tastatur und
mobile Bedienung bleiben möglich. Ohne JavaScript stehen die Inhalte untereinander.

Eine offene oder wieder geöffnete Lobby priorisiert Spielauswahl, Grundwerte,
Bereitschaft und Generierung. Ein alter Seed verdrängt keine neue Vorbereitung.
Nach erfolgreicher Generierung und hinterlegter Verbindung steht die Konsole im
Mittelpunkt. Persönliche Spiele, Slotnamen, Patchdownloads, Anleitung und die
Verbindungsadresse liegen direkt darunter in einem aufklappbaren Bereich. Nach Abschluss
entfallen Vorbereitung und Verbindungsformulare. Eine gespeicherte
Serveradresse wird nie als Online-Nachweis bezeichnet.

Historische Builds bleiben über `?build=<id>` auswählbar. Die bisherigen
`/sessions/<sid>/builds/<id>/play`-Links rendern dieselbe Rundenzentrale für genau
diesen Seed. Download-, Analyse-, Live- und Konsolenrouten bleiben erhalten;
alte Logik-URLs erklären die Deaktivierung mit HTTP 410. Detailansichten besitzen einen Rückweg mit
Rundenname und Seed-ID zur passenden zentralen Ansicht.

## Persönliche Dateien

Die Zuordnung prüft vorhandene Patchcontainer (`archipelago.json`: Spiel und
Spieleridentität) oder exakt passende Archipelago-Dateinamen mit verifizierter
Generator-Spieler-ID. Die Lobbyposition oder ein Teilstring im Dateinamen
reichen nicht aus. ZIP-Inhalte werden begrenzt gelesen und nicht ausgeführt.
Unbekannte Formate und Dateien mit unklarer Identität bleiben transparent im
gemeinsamen Downloadbereich.

## Fortschritt und offene Checks

Der zentrale Fortschrittsbereich verwendet die bisherigen Live-JSON-Endpunkte.
Gemeinsamer Cache, Abrufgrenzen, historische Snapshots, Reset-Abschnitte,
Race-Filter und Bedeutung aller Statistiken bleiben erhalten. Das kompakte
Diagramm verbindet keine Werte über einen Reset hinweg. Erweiterte Vergleiche,
Interaktionen und Präsentationsmodus bleiben in der Detailansicht.

Spieler können ihren eigenen Slot unmittelbar in der Konsole verbinden.
Slotname und Server sind bereits bekannt; nur ein gegebenenfalls
benötigtes Raumpasswort ist einzugeben. Private Meldungen bleiben privat.
Die vorhandenen Konsolen-Endpunkte prüfen weiterhin Mitgliedschaft, eigenen
Slot, CSRF, Ratenbegrenzung und Archivstatus. Das Öffnen der Oberfläche allein
verbindet keinen Slot und sendet keine Spielaktionen. Eine Webverbindung ist
keine Bestätigung einer Verbindung des lokalen Spielclients.

`/received`, `/missing` und `/hint` verwenden den gemeldeten Serverstand.
Offene Checks sind keine berechneten erreichbaren Checks; Go-Mode wird nicht
berechnet. Race-Modus sperrt weiterhin Konsole und Itemprotokoll. Die separate
Seed-Analyse behält ihre ausdrückliche Spoilerfreigabe und Race-Regeln.

## Verwaltung

„Mehr“ bündelt Analyse, vollständige Dateien, erweiterte Statistiken,
Konsole, Diagnose, historische Seeds und Host-Verwaltung. Host-Formulare werden
nur dem bisherigen berechtigten Personenkreis angezeigt. Generierung bleibt
bei der Vorbereitung prominent und verwendet den bestehenden Preflight.
Teilnehmeraktionen, Versionen, Vorlagen und Einstellungen bleiben erhalten.

Die Rundenzentrale verwendet `hub/rounds.py`, `round*.html`, `overview.html`,
`round.js` und `round.css`, ohne neues Frontend-Framework. Die zusätzliche
Aufzeichnung und ihre additiven Tabellen beschreibt [CONNECTION_RELIABILITY.md](CONNECTION_RELIABILITY.md).

## Prüfung

Python-Tests prüfen Eindeutigkeit der Dashboardkarten, alte URLs, historische
Seeds, wieder geöffnete Lobbys und konservative Dateizuordnung. Die Browser-Suite
prüft die bisherigen Funktionen mit angepassten Zugangswegen sowie einen
vollständigen zentralen Ablauf. Dieser verwendet einen isolierten Generator,
einen lokalen Archipelago-Protokollserver und ausdrücklich kontrollierte
Logikergebnisse für den UI-Test. Das ist kein Test mit einem echten
Archipelago-Spielclient und keine neue Validierung der nativen Spielmodelle.
Screenshots entstehen bei 390, 768, 1440 und 2560 Pixeln.

Lokale Abnahme am 10.11.2026: **190 Python-Tests erfolgreich**, vollständige
Playwright-Suite **14 Szenarien erfolgreich**. Der zentrale Browserablauf erzeugt
16 Aufnahmen (vier Bereiche bei vier Breiten); repräsentative Desktop-, Tablet-
und Smartphone-Ansichten wurden visuell kontrolliert. Zusätzlich entstehen die
bestehenden Aufnahmen der übrigen Seiten. Es wurde kein echter Spielclient oder
externer Spieler verbunden und keine bestehende Produktivdatenbank verändert.
