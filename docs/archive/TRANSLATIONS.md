> Historischer Stand bis 17.11.2026. Keine aktive Anleitung oder Aufgabenliste. Aktuell: [Dokumentation](../DEVELOPMENT.md).

# Sprache und Darstellung

## Gemeinsame Ressourcen

`hub/locales/de.json` und `en.json` enthalten gepaarte, stabile Nachrichten-IDs.
Jinja verwendet `_('Deutscher Ausgangstext')`, JavaScript
`window.HUB_I18N.t('Deutscher Ausgangstext')`. Beide lesen dieselben Ressourcen.
Die aktuelle Seite erhält sicher serialisierte JSON-Daten; Übersetzungen werden
als Text und niemals als HTML interpretiert.

Platzhalter wie `{v0}` werden einmal ersetzt. Benutzerwerte werden nicht erneut
übersetzt oder als weitere Platzhalter ausgewertet. Dynamische Fehler werden
anhand bekannter Vorlagen lokalisiert. Unbekannte Nachrichten bleiben im Original;
die dokumentierte Standardsprache ist Deutsch. Die Browser-Sprache übersteuert
keine Kontowahl.

`scripts/ui_catalog.py` erfasst statische UI-Texte und bekannte Status-/Fehlermeldungen.
`--write` bindet passende statische Texte an die API an. Neue IDs werden angehängt,
vorhandene nicht umnummeriert. Neue Einträge anschließend in `en.json` übersetzen.
Tests prüfen Schlüssel, Platzhalter und statische Aufrufe in produktiven Templates
und Skripten. Historische, nicht ausgelieferte Logik-UI ist ausgenommen.

`python -m scripts.ui_checks` findet produktive JavaScript-Literale und Jinja-Ausdrücke,
die die gemeinsame Übersetzungsfunktion umgehen. Zusätzliche Tests prüfen statische Backend-Fehler und
fehlende UI-IDs. Dynamische Rundenzustände, API-/Verbindungsdiagnosen und Vorschau-
Beschriftungen verwenden dieselben Ressourcen. Standard-HTTP-Fehler werden ebenfalls
für DE/EN formuliert. Gezielt unveränderte Fachbegriffe und Nutzerinhalte sind keine
fehlenden Übersetzungen.

Neue Hub-Konsolenmeldungen können Ausgangstext und Werte getrennt speichern. Hilfe
und Ergebniszahlen werden beim Lesen in der aktuellen Kontosprache formatiert.
Itemlisten, Slotnamen und gesendeter Chat bleiben dabei unveränderte Daten. Originale
Servermeldungen erhalten keine Hub-Herkunftsmarkierung und werden nicht übersetzt.

## Daten bleiben Daten

Spiel-, Slot-, Item- und Location-Namen, YAML-Schlüssel/-Werte, Protokollbefehle
und originale Archipelago-Meldungen bleiben unverändert. Eigene Beschreibungen,
Vorlagennamen und Gruppenanleitungen sind Nutzerinhalte. Genre-/Tag-Beschriftungen
können übersetzt werden; Filterwerte bleiben stabil.
Nur kuratierte Genre-/Tag-Begriffe werden übersetzt; freie Begriffe wie eigene
Tags bleiben unverändert. Suche berücksichtigt originale und übersetzte Labels.
Generierte Vorlagenbeschreibungen werden lokalisiert, eigene Namen und Beschreibungen nicht.

Alle 89 mitgelieferten Spielbeschreibungen, Voraussetzungen und Einrichtungsschritte
haben englische Fassungen in `hub/locales/games_en.json`. Quellenlinks sowie
Regions-/Versionsanforderungen bleiben erhalten. Eigene Beschreibungen übersteuern
redaktionelle Texte in beiden Sprachen. Native APWorld-Optionsnamen und Hilfen
werden so dargestellt, wie sie der Entwickler liefert.

## Konto und Browser

Sprache (`de`, `en`) und Theme (`dark`, `light`, `system`) werden unter
`users.overrides._interface` gespeichert. Keine Datenbankmigration. Der eigene
CSRF-geschützte Endpunkt `/preferences` verändert keine YAML-Einstellung oder
Bereitschaft. Die YAML-Schichtung akzeptiert ausschließlich ihre ausdrücklich
erlaubten Profiloptionen. Ohne Anmeldung speichern Cookies die Browserwahl;
angemeldete Konten verwenden ihre eigene Wahl, nicht die eines vorherigen Kontos.

Sprachwechsel laden die Seite nach dem Speichern neu. Konsolenentwürfe bleiben in
`sessionStorage`, getrennt nach Konto und Runde, erhalten. Raumpasswörter werden
dort nie gespeichert. Themes wechseln ohne Reload. System folgt
`prefers-color-scheme`; das initiale Theme steht bereits vor dem CSS-Render im HTML.

JavaScript verwendet `Intl` mit `de-DE` beziehungsweise `en-GB`. Die Jinja-Filter
`localdate` und `localnumber` formatieren Anzeigen; APIs behalten ihre Werte.
`<time>`-Elemente verwenden im Browser dessen Zeitzone. Technische IDs und
Eingabewerte werden nicht lokal formatiert.

## Prüfung

Python prüft Kontotrennung, CSRF, ungültige Einstellungen, unveränderte Spielwerte
und Bereitschaft, dynamische Namen, Ressourcen und persönliche Filter. Playwright
prüft DE/EN und beide Themes bei 390, 768, 1440 und 2560 px, System-Umschaltung,
Entwurfserhalt, Kontrast und über Seitenwechsel bestehende Textverbindungen.
Dies verwendet isolierte Daten und einen lokalen AP-Protokollserver, keine echten
Spielclients oder produktiven Räume.
