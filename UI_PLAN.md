# ArchipeMANU: UI-Plan

Stand: 7. November 2026 · Feature-Branch `feature/ui-refresh`.

## Leitlinien

Dunkelblaue Navigation, helle Inhaltsflächen und weiße Karten, unabhängig von
der Betriebssystem-Farbeinstellung. Indigo markiert die wichtigste Aktion,
Statusanzeigen kombinieren Text und Farbe. Systemschrift, klare Abstände,
sichtbarer Tastaturfokus und responsive Layouts ohne externe Schrift- oder Bilddienste.

Alle bestehenden Funktionen bleiben erreichbar. Häufige Spieleraktionen stehen
direkt auf der Seite, technische Extras in beschrifteten aufklappbaren Bereichen.
Keine Änderungen an gespeicherten Konten, Vorlagen, APWorlds oder Seeds.

## Umsetzung in Schritten

| Schritt | Konkrete Änderung | Prüfung |
|---|---|---|
| 1. Grundlayout | Vier Hauptlinks: Übersicht, Spielebibliothek, Lobbys, Seed-Analyse. Aktiver Bereich, getrennte Profil-/Adminaktionen, Sprunglink zum Inhalt. Konsolidiertes helles Stylesheet mit dunkler Navigation. | Tastatur, schmale Displays, bestehende Formulare |
| 2. Einstieg | Begrüßung, echte Kennzahlen, offene Lobbys und eigene Runden als Karten. Lobby-Erstellung an einer Stelle auf der Lobby-Seite. | Reale Teilnehmerzahlen und Zugriffsrechte |
| 3. Bibliothek | Suchfeld, Filter für Spielstatus und integrierte/hochgeladene Spiele. Status, Version und klare Aktion pro Karte. Auf der Spielseite zugängliche Anleitung und Presets; technische Vorlagenverwaltung eingeklappt. | Kombinierte Filter, Upload, Presetauswahl |
| 4. Lobby | Fortschrittsanzeige, eine Teilnehmerübersicht inklusive Spieler ohne Spiel. Auswahl und Einstellungen bleiben in der Lobby. Bereitschaft gut sichtbar, Hostbereich separat. Bekannte fehlende Bereitschaft deaktiviert den Startbutton; Serverprüfung bleibt verbindlich. | Zwei Spieler, Entwürfe, fehlende Bereitschaft, ungültige Optionen, Hostrechte |
| 5. Generierung | Deutsche Statusnamen, verständliche Hinweise und aufklappbare Fehlerprotokolle. Ausgaben in der Seed-Historie, keine doppelten Downloads desselben aktuellen Builds. | Mock-Generierung, Fehlerfall, bestehende Builds |
| 6. Analyse | Übersicht, Progression-Items, einzeln aufdeckbare konkrete Fundorte und explizite Spoileransicht bleiben erhalten. Tatsächliche Verbindungsdaten und Spielstart gut erreichbar. | Keine Fundorte vor Klick, Race-Schutz, echte Kennzahlen |

## Abnahmekriterien

- Kein Zwang, YAML oder APWorld-Technik zu verstehen, um eine vorhandene Runde
  vorzubereiten. Begriffe werden im passenden Kontext erklärt.
- Teilnehmer-, Bereitschafts-, Bibliotheks- und Seed-Zahlen stammen aus den
  vorhandenen Daten; keine erfundenen Statistiken, Cover oder Verfügbarkeitsangaben.
- Auf kleinen Displays umbrechende Navigation, einspaltige Karten, bedienbare
  Formulare. Breite Tabellen scrollen innerhalb ihres Bereichs.
- Python-Suite und Playwright-Flows laufen mit temporären Daten. Zusätzliche
  Browser-Prüfungen decken mobile Layouts, Filter und Rollen ab.
- Screenshots der umgesetzten Seiten werden anhand isolierter Testdaten erzeugt
  und visuell geprüft. Produktive Daten werden dafür nicht verwendet.

## Ergebnisse

- Schritte 1–6 umgesetzt. Das Stylesheet wurde konsolidiert; die Inhalte bleiben
  auch bei dunkler Betriebssystem-Einstellung hell. Primärnavigation und
  Spieler-/Hostaktionen sind getrennt. Import, Versionsverwaltung, Downloads,
  Klonen und Verwaltungsfunktionen bleiben erreichbar.
- Dashboard-Zahlen stammen aus der Datenbank. Eigene Runden werden anhand von
  Ersteller, Mitgliedschaft oder vorhandenem Spielslot ermittelt; fremde
  geschlossene Runden erscheinen nicht unter „Meine Runden“.
- Spielsuche und beide Filter lassen sich kombinieren. Gespeicherte Anleitungen
  und Presets sind auf der Spielseite zugänglich. Unpassende Presets bleiben
  erkennbar und werden nicht stillschweigend verwendet.
- Der Host sieht fehlende Spiele und Bereitschaft. Der Startbutton ist bei
  fehlender Bereitschaft deaktiviert; serverseitige Prüfungen bleiben bestehen.
  „Status aktualisieren“ liest die aktuelle Teilnahme und Bereitschaft neu ein.
- Teilnehmerzeilen werden mobil untereinander dargestellt, damit die
  Bereitschaftsaktion direkt erreichbar bleibt. Weitere breite Statistiktabellen
  scrollen innerhalb ihres Bereichs.
- 115 Python-Tests erfolgreich (25,7 Sekunden), einschließlich neuer Prüfungen
  für Dashboard, kombinierte Filter, gespeicherte Anleitungen und Hostrechte.
- 4 Playwright-Szenarien erfolgreich (31,5 Sekunden): Registrierung, gemeinsamer
  Zwei-Spieler-Ablauf samt Upload/Mock-Generierung/Analyse, Fehlerkorrektur sowie
  mobile Navigation/Filter/Rollentrennung bei 390 Pixeln Breite.
- Verbindungsdaten werden über das echte Hostformular gespeichert und in der
  Analyse überprüft. Spoiler werden ein- und ausgeblendet; konkrete Fundorte
  bleiben bis zur ausdrücklichen Aufdeckung verborgen.
- Desktop- und Mobil-Screenshots wurden visuell geprüft. Sie verwenden nur
  isolierte Testdaten und liegen unter `test-results/ui/`: `overview-desktop.png`,
  `lobby-desktop.png`, `analysis-desktop.png`, `overview-mobile.png`,
  `library-mobile.png` und `lobby-mobile.png`.
- `git diff --check` erfolgreich. Kein Push oder Merge. Die CI-Konfiguration
  führt die Browser-Suite weiterhin mit temporärer Datenbank und Mock-Generator
  aus; GitHub Actions wurde lokal nicht als ausgeführt behauptet.
