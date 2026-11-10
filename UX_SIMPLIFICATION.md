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
URL-Fragment ohne Dokumentnavigation: **Spielen**, **Fortschritt**,
**Mitspieler**, **Mehr**. Zurück/Vorwärts, direkte Fragmentlinks, Tastatur und
mobile Bedienung bleiben möglich. Ohne JavaScript stehen die Inhalte untereinander.

Eine offene oder wieder geöffnete Lobby priorisiert Spielauswahl, Grundwerte,
Bereitschaft und Generierung. Ein alter Seed verdrängt keine neue Vorbereitung.
Nach erfolgreicher Generierung zeigt „Spielen“ persönliche Spiele, Slotnamen,
Patchdownloads, Anleitung und die kompakte Verbindungsadresse. Nach Abschluss
entfallen Vorbereitung und Verbindungsformulare. Eine gespeicherte
Serveradresse wird nie als Online-Nachweis bezeichnet.

Historische Builds bleiben über `?build=<id>` auswählbar. Die bisherigen
`/sessions/<sid>/builds/<id>/play`-Links rendern dieselbe Rundenzentrale für genau
diesen Seed. Alle bisherigen Download-, Analyse-, Live-, Konsolen- und Logikrouten
bleiben erhalten. Umfangreiche Detailansichten besitzen einen Rückweg mit
Rundenname und Seed-ID zur passenden zentralen Ansicht.

## Persönliche Dateien

Die Zuordnung prüft vorhandene Patchcontainer (`archipelago.json`: Spiel und
Spieleridentität) oder exakt passende Archipelago-Dateinamen mit verifizierter
Generator-Spieler-ID. Die Lobbyposition oder ein Teilstring im Dateinamen
reichen nicht aus. ZIP-Inhalte werden begrenzt gelesen und nicht ausgeführt.
Unbekannte Formate und Dateien mit unklarer Identität bleiben transparent im
gemeinsamen Downloadbereich.

## Fortschritt und nächste Checks

Der zentrale Fortschrittsbereich verwendet die bisherigen Live-JSON-Endpunkte.
Gemeinsamer Cache, Abrufgrenzen, historische Snapshots, Reset-Abschnitte,
Race-Filter und Bedeutung aller Statistiken bleiben erhalten. Das kompakte
Diagramm verbindet keine Werte über einen Reset hinweg. Erweiterte Vergleiche,
Interaktionen und Präsentationsmodus bleiben in der Detailansicht.

Spieler können ihren eigenen Slot unmittelbar bei „Deine nächsten Checks“
verbinden. Slotname und Server sind bereits bekannt; nur ein gegebenenfalls
benötigtes Raumpasswort ist einzugeben. Private Meldungen bleiben privat.
Die vorhandenen Konsolen-Endpunkte prüfen weiterhin Mitgliedschaft, eigenen
Slot, CSRF, Ratenbegrenzung und Archivstatus. Das Öffnen der Oberfläche allein
verbindet keinen Slot und sendet keine Spielaktionen. Eine Webverbindung ist
keine Bestätigung einer Verbindung des lokalen Spielclients.

Danach nutzt die Oberfläche die vorhandene private Logik-API. Unbekannte,
fehlerhafte oder veraltete Ergebnisse entfernen frühere Checks und Go-Mode.
Die kompakte Liste enthält keine Itemplatzierungen. Deren ausdrückliche
Spoilerfreigabe bleibt ausschließlich in der vollständigen Logikansicht.
Race-Modus sperrt weiterhin Konsole und persönlichen Tracker.

## Verwaltung

„Mehr“ bündelt Analyse, vollständige Dateien, erweiterte Statistiken,
Konsole, Diagnose, historische Seeds und Host-Verwaltung. Host-Formulare werden
nur dem bisherigen berechtigten Personenkreis angezeigt. Generierung bleibt
bei der Vorbereitung prominent und verwendet den bestehenden Preflight.
Teilnehmeraktionen, Versionen, Vorlagen und Einstellungen bleiben erhalten.

Neue Dateien: `hub/rounds.py`, `round*.html`, `overview.html`, `round.js`,
`round.css`. Keine neue Datenbankmigration oder Frontend-Abhängigkeit.

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
