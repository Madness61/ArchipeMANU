# Multiworld Hub – Designsystem

Seit dem UX-Refactoring vom 10.11.2026 führen drei Hauptbereiche zur zentralen
Rundenoberfläche. Deren vier Bereiche wechseln im selben Dokument. Kompakte
Karten priorisieren Slotnamen, persönliche Downloads und Verbindung; technische
Verwaltung steht unter „Mehr“. Die bestehende Farbpalette bleibt erhalten.
Layout und Verhalten sind in [UX_SIMPLIFICATION.md](UX_SIMPLIFICATION.md) beschrieben.

Das Frontend ist eine gemeinsame Gaming-Lounge für Vorbereitung, Spielstart
und Live-Fortschritt. Flask, Jinja, Endpunkte und die vorhandenen Formulare
bleiben die Grundlage. Zusätzliche Frontend-Abhängigkeiten sind nicht nötig.
Eine additive Tabelle game_metadata speichert eigene Beschreibungen, Genres
und Tags unabhängig von APWorld-Versionen. Bestehende Katalogwerte bleiben
als Rückfall erhalten; vorhandene Spiel- und Rundendaten werden nicht ersetzt.

## Farbe und Typografie

Die zentralen Tokens liegen in hub/static/style.css:

| Token | Farbe | Verwendung |
| --- | --- | --- |
| --bg | #0D1323 | Seitenhintergrund |
| --panel | #192238 | Karten und Panels |
| --surface-raised | #222E47 | Erhöhte Flächen und sekundäre Aktionen |
| --accent | #7768EF | Primärakzent, Fortschritt, aktive Navigation |
| --accent-hover | #9488FF | Links, Fokus und Hover-Akzente |
| --text | #F4F6FF | Haupttext |
| --muted | #AAB6D0 | Erläuterungen und Metadaten |
| --ok | #5EE3B1 | Bereitschaft und positive Zustände |
| --warn | #F5BC79 | Hinweise und fehlende Voraussetzungen |
| --err | #F08D9B | Fehler und destruktive Aktionen |

Primärbuttons nutzen eine dunklere Akzentvariante für mindestens 4,5:1 Kontrast
mit weißer Schrift, auch beim Hover. Eingabefelder besitzen eine kontrastierende
Rahmenfarbe und alle interaktiven Elemente einen sichtbaren Fokus.

Der Font-Stack verwendet lokal verfügbares Inter, Segoe UI und Systemschriften.
Es werden keine Webfonts von Dritten geladen. Überschriften sind kräftig,
kurz und eng gesetzt; erläuternder Text bleibt ruhig. Zahlen nutzen tabellarische
Ziffern, technische Inhalte eine Monospace-Schrift.

## Komponenten

Wiederverwendbare Jinja-Makros in hub/templates/ui.html:

- icon: eigene SVG-Linienicons aus hub/static/icons.svg.
- badge und action: Statusanzeigen und verlinkte Aktionen.
- section_heading und empty_state: Abschnittshierarchie und ehrliche Leerzustände.
- progress: beschrifteter Fortschritt mit zugänglichen Zahlenwerten.
- game_art: deterministische grafische Titelbilder und kompakte Spiel-Icons.
- lobby_card: gemeinsame Darstellung von Lobbyname, Host, Teilnehmern und Einstieg.
- option_tools: Optionssuche und Übersicht angepasster Werte.

Cover-Fallbacks bestehen aus eigenen SVG-Geometrien, CSS-Farbe und dem
tatsächlichen Spielnamen. Sie haben keine fremden Coverbilder und benötigen
keine ungeklärten Bildrechte. Farbe und Titel hängen stabil vom jeweiligen
Spiel ab.

Karten verwenden 18 px Rundung, kleine Komponenten 11 px, gemeinsame Abstände
in Schritten von 4/8/12/16/24/32 px sowie dezente Schatten. Status wird immer
auch durch Text vermittelt. Hover-Bewegungen bleiben klein.

## Layout und Nutzerführung

Desktop: feste linke Sidebar mit Dashboard, Spielebibliothek, Lobbys,
aktiven Runden und Seed-Analysen. Profil und Administration sind getrennt.
Die aktive Seite hat einen farbigen Hintergrund und Randindikator.
Der angemeldete Inhaltsbereich nutzt die gesamte Breite neben der Sidebar,
auch bei 2560 und 3840 px. Dashboard-Bereiche verteilen sich auf verfügbare
Spalten; kurze Formulare behalten eine lesbare eigene Maximalbreite.

Dashboard: Eine echte laufende oder vorbereitete Runde steht im Vordergrund.
Die Hauptaktion ergibt sich aus Spielauswahl, Bereitschaft, Generierung und
Raumverknüpfung. Ältere aktive Runden stehen vor neueren Archiven. Statistiken
stammen aus bestehenden Daten; es gibt keine erfundenen Aktivitäten.

Lobby: Header mit Host und Bereitschaft, klare nächste Aktion, eigene
Spielauswahl und gemeinsame Spielerkarten. Die bestehende Teilnehmer-Tabelle
bleibt als semantische Struktur und DOM-Schnittstelle erhalten, erscheint
visuell als Kartenraster. Spieler ohne Spiel bleiben sichtbar.

Spielauswahl: Suchbarer visueller Katalog plus natives Select. Schneller Weg
über Standardwerte oder fortgeschrittener Weg über „Einstellungen anpassen“.
Die Optionssuche entfernt oder deaktiviert keine Formularfelder. Vorlage,
Profil, Grundwerte, Validierung und Speichern behalten ihre bestehende Logik.
Erklärungen sind per Tastatur aufklappbar; neue Eingaben erhalten eine visuelle
Markierung, ohne den zugänglichen Feldnamen zu verändern.

Spielstart: Eigenes Spiel und Slotname, separate Server-/Portfelder mit
Kopieraktionen, Einrichtungsanleitungen, Dateien, Abschluss und Mitspieler.
Technische Daten sind nachrangig aufklappbar. Bereits verknüpfte Räume werden
über einen eingeklappten Host-Bereich verwaltet.

Live-Dashboard: dieselben sechs Ansichten und Datenbedeutungen, dunkle Diagramme,
großer Fortschrittsring und kompakte Spielerkarten in der Übersicht.
Präsentationsmodus entfernt Navigation und technische Nebendaten und vergrößert
Kennzahlen. Beobachtung, Empfangsliste und Online-Prüfung bleiben klar getrennt.

Seed-Analyse: gemeinsame KPI-, Balken- und Tabellenstile. Einzelne Fundorte,
Spoilerfreigabe, Race-Modus und zugeklappte Progression-Gruppen bleiben erhalten.
Anmeldung, Profil, Import, Vorlagen und Administration nutzen dieselben
Komponenten, Formularfarben und Fehlermeldungen.

## Responsive und zugängliche Bedienung

Ab 900 px erscheint ein mobiles Menü statt umbrechender Navigationszeilen.
Es unterstützt Escape, Fokusbegrenzung, Rückkehr zum Menübutton und einen
inaktiven Hintergrund. Ohne JavaScript bleibt die Navigation normal im
Dokumentfluss bedienbar.

Unter 600 px werden Karten und Formulare weitgehend einspaltig. Touch-Aktionen
sind mindestens 44 px hoch; kompakte sekundäre Aktionen verwenden 39 px.
Breite Datenmatrizen und Verwaltungstabellen scrollen innerhalb ihrer Panels,
anstatt die Seite zu verbreitern. Unwichtige Metadaten treten zurück.

prefers-reduced-motion unterdrückt Bewegung und Übergänge. Navigation,
Suchfelder, native Selects, Details und Aktionen bleiben mit Tastatur bedienbar.
SVG-Icons sind dekorativ ausgeblendet; Feldbeschriftungen und Statustext bleiben
zugänglich. Eine vollständige Screenreader-Prüfung ist damit nicht ersetzt.

## Erweiterung und Validierung

Neue Seiten erben base.html und verwenden die Makros und Tokens. Neue Symbole
werden im eigenen SVG-Sprite ergänzt. Zusätzliche Spiele benötigen kein
Cover-Download-System. Live-Darstellung erweitert live.css und live.js, ohne
Statistikberechnungen zu verändern.

Der isolierte Playwright-Test test_redesign.py prüft den kompletten Weg bis
zum Spielstart und erfasst wichtige Seiten bei 390, 768 und 1440 px.
Die Screenshots liegen unter test-results/browser/logs im jeweiligen Testordner.
Er kontrolliert Seitenüberlauf, mobiles Menü, Fokus, Optionssuche, erhaltene
versteckte Werte, Primärbutton-Kontrast und reduzierte Bewegung.

Bestehende Python- und Browser-Tests prüfen weiterhin Anmeldung, Rechte,
APWorld-Verwaltung, YAML, Bereitschaft, Generierung, Downloads, Live-Cache,
Historie, Spoiler und Race-Regeln mit isolierten Daten und Mock-Generatoren.
Ein echter Spieleabend und assistive Technologien müssen zusätzlich mit den
jeweiligen Spielclients geprüft werden.

Ausgeführte lokale Prüfung am 08.11.2026: 164 Python-Tests und alle 10
Playwright-Szenarien erfolgreich. Nach den letzten visuellen Korrekturen wurde
das Redesign-Szenario erneut erfolgreich ausgeführt. Es erzeugt 49 Screenshots
bei den drei Zielbreiten sowie für den Präsentationsmodus. Repräsentative
Aufnahmen von Dashboard, Katalog, Lobby, Editor, Spielstart, Verwaltung und
Live-Ansicht wurden visuell kontrolliert. Die Browser-Prüfung verwendet echte
Flask-Routen mit isolierten Testdaten und einem Testgenerator; sie ersetzt
keinen Verbindungs- und Spieltest mit echten Archipelago-Spielclients.

Ergänzung vom 09.11.2026: volle Desktop-Breite bis 3840 px, editierbare
Katalogmetadaten und persönlicher Logik-Tracker. Die Python-Suite umfasst
186 erfolgreiche Tests; 13 Browser-Szenarien decken zusätzlich Katalog,
Konsole und Logikansicht ab. Der echte UT-Subprozess wurde separat mit APQuest
geprüft: zwei erreichbare Checks ohne Items, sechs mit Zielausrüstung sowie
korrekter Wechsel in Go-Mode. Der Browser-Logiktest verwendet kontrollierte
API-Antworten und prüft Darstellung, Filter und ausdrückliche Spoilerfreigabe.
Zusätzlich wurden alle sieben Spielmodelle des aktiven Seeds mit dessen echten
unveränderlichen YAML-/Slotdaten offline rekonstruiert und geprüft. Für Skyward
Sword werden ausschließlich Layoutdaten aus dem eigenen generierten Patch
verwendet; die Engine erhält keine Itemplatzierungen oder Hinweise.
