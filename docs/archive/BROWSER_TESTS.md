> Historischer Stand bis 17.11.2026. Keine aktive Anleitung oder Aufgabenliste. Aktuell: [Dokumentation](../DEVELOPMENT.md).

# Automatische Browser-Tests

## Progression-Hilfe und globale Itemsuche (16.11.2026)

Der Empfehlungs-Test prüft inzwischen auch die clientseitige Kompatibilität mit
älteren API-Ergebnissen: ein dominantes Einzelitem mit wirkungslosem Zusatz wird
unterdrückt, echte partielle Synergie und reine Zielsynergie bleiben erhalten.
Gleiche Ergebnismengen werden als Alternativen gruppiert; gleich große Mengen
unterschiedlicher Checks bleiben getrennt. Gesamteffekt, exklusiver Zusatznutzen,
Suchabdeckung und aufklappbare lange Listen werden in DE/EN und allen Themes
geprüft. Dies sind ausdrücklich UI-Fixtures; echte Regeln werden separat geprüft.
Die reale Integration umfasst zusätzlich das DS3-Basin-Szenario mit Seed 20261116,
`late_basin_of_vows=off/after_small_doll` und deaktivierten DLCs. Das
Regel-Testinventar ist kontrolliert gesetzt und wird nicht als echter Live-
Inventarzustand ausgegeben. Die konkrete Checkanzahl wird nicht fest codiert.

Abnahme der Empfehlungskorrektur: **271 Python-Tests (131,7 Sekunden)**,
**21 Browser-Szenarien (308,1 Sekunden)** und **4 echte AP-Integrationen
(79,7 Sekunden)** erfolgreich. Ein zusätzlicher gezielter Progression-Lauf
erzeugte Detail-Screenshots des Paar-Zusatznutzens in DE/EN und allen Themes;
Desktop und Mobil wurden visuell geprüft. Im ersten Browser-Gesamtlauf wurde
ein bestehender Mobil-Test-Rennfall nach einer Formularweiterleitung erkannt;
nach gezielter Synchronisierung besteht der gesamte Lauf.

Die Suite umfasst zusätzlich den Ablauf `test_progression.py`: zwei getrennte
Konten, Itemsuche unmittelbar aus der Rundenzentrale, persönliche Spoilerfreigabe,
Suche über mehrere Empfänger, eigene Items, historische Seeds ohne Logikdaten,
unveränderter Konsolenentwurf und serverseitige Sperre nach Widerruf.
Ergebnisansichten werden in DE/EN, Light/Dark/System und bei 390/1440 px geprüft;
Screenshots liegen im jeweiligen Test-Logordner. Native Item-/Spielnamen bleiben
unverändert. Die Suchanfragen bedienen die echte API mit dem isolierten
Mock-Generator; dynamische Ergebniskarten werden ausdrücklich mit einer UI-Fixture
gerendert. Sie ersetzen keinen echten Engine-Test.

Die separate Suite `python -m unittest discover -s integration_tests -v` erzeugt
echte isolierte Seeds für ChecksFinder, Meritous und Custom-Pseudoregalia und
rekonstruiert sie mit Original-YAML, Seed, Modellhash und Regelproben. Für
ChecksFinder wird außerdem der vollständige angemeldete API-/Hintergrundprozess
inklusive Cachewechsel nach einem Empfang getestet. Eine fehlende APWorld-Datei
wird vor Auswertung abgelehnt. Benötigt den installierten lokalen AP-Checkout;
die Suite kopiert ihn in ein temporäres Verzeichnis und verwendet weder
Produktivdaten noch echte Online-Räume. Die regulären GitHub-Actions-Jobs erfassen
die neuen Python- und Playwright-Tests automatisch; die echte AP-Suite bleibt
eine gesonderte Integrationsprüfung.

Aktuelle Architektur, gemessene Check-Zuwächse und Grenzen:
[PROGRESSION_ENGINE.md](PROGRESSION_ENGINE.md).

Ergebnis des Grundstands vor der Empfehlungskorrektur: **258 Python-Tests (116,1 Sekunden)**,
**21 Browser-Szenarien (295,3 Sekunden)** und **3 echte AP-Integrationen
(60,0 Sekunden)** erfolgreich. Desktop- und Smartphone-Screenshots der neuen
Hilfe wurden zusätzlich visuell geprüft. Keine reale Spielclient-Abnahme.

## Verifizierter Feinschliff vom 15. November 2026

Der vollständige lokale Lauf besteht aus **243 erfolgreichen Python-Tests** und
**20 erfolgreichen Playwright-Szenarien**. Zusätzlich zu den Kernabläufen prüfen
die Tests ausdrücklich aktivierte Host-Aufzeichnung ohne offene Webseiten,
unabhängige API-/Konsolendiagnose, nachgewiesene Empfangsergänzungen und einen
tatsächlichen Neustart des isolierten Hub-Prozesses mit derselben SQLite-Datenbank.
Der Testserver hält dabei Schema und Konten fest, verwendet denselben lokalen
HTTP-Port und kontaktiert ausschließlich den lokalen Fake-AP-Protokollserver.

DE/EN und Light/Dark werden bei 390/768/1440/2560 px geprüft und als Screenshots
gespeichert; Systemmodus folgt dem emulierten Betriebssystem. Label-Kontraste,
Fokus, reduzierte Bewegung, Entwürfe und horizontales Überlaufen sind enthalten.
Für Theme-Screenshots wird das Ende der kurzen Farbtransition abgewartet.
Zentrale Konsolen-, Diagnose-, Bibliotheks- und Neustartansichten wurden visuell geprüft.

Artefakte dieses Laufs: `test-results/final-polish-browser-verified/`, Python-Ausgabe:
`test-results/final-polish-python-complete.txt`. Dies sind ignorierte lokale
Testartefakte. Reale Spielclients, WLAN-/Hamachi-Ausfälle und Mehrspieler-Langzeit-
betrieb auf echten Archipelago-Räumen wurden nicht ausgeführt. Ältere Ergebnisse
weiter unten sind historische Einzelstände.

## Erweiterung vom 9. November 2026: Archipelago-Konsole

Nach der Transportkorrektur: **181 Python-Tests erfolgreich (58,8 Sekunden)**;
der Konsolen-Browserablauf erneut erfolgreich (17,1 Sekunden). Automatische
Transporterkennung bevorzugt WSS; der Status zeigt WS/WSS. Der Browser prüft
zusätzlich die erneute Anmeldung nach falschem Raumpasswort und das Entfernen
der alten Fehlermeldung. Die lokale Testattrappe verwendet ausdrücklich WS.

Die Suite umfasst jetzt 12 Browser-Szenarien. Der zusätzliche Konsolentest
verbindet die echte Backend-WebSocket-Anbindung mit einem eigenen lokalen
Archipelago-Protokollserver: Item-Sendung Bob → Alice mit Item- und Check-Namen,
Chat, `/hint`, `/received`, private Antworten, sichere Textausgabe, Filter,
Trennen und mobile Darstellung. Der Spielclient wird nicht simuliert gesteuert;
es werden keine echten Spieler kontaktiert oder Spielchecks abgeschickt.

Gesamtergebnis: **175 Python-Tests erfolgreich (60,7 Sekunden)** und
**12 Browser-Szenarien erfolgreich (114,8 Sekunden)**. Ein im Gesamtlauf
gefundener Beschriftungsfehler im Katalog-Editor ist korrigiert. Screenshots:
`test-results/browser/logs/test_console_items_commands_private_hints_and_mobile-chromium-/`.
API und Einrichtung: [ARCHIPELAGO_CONSOLE.md](ARCHIPELAGO_CONSOLE.md).

Die Playwright-Tests bedienen die echte Flask-Website mit Chromium. Formulare,
Anmeldung, Cookies, CSRF, Uploads, Datenbank, Hintergrundjobs und JavaScript bleiben
aktiv. Ausschließlich Archipelago-Schemaextraktion und Seed-Generierung werden
im separaten Testserver simuliert. Ein Archipelago-Checkout ist nicht erforderlich.

## Lokal starten

Einmalig im Projektordner mit Python 3.13 einrichten:

```powershell
py -3.13 -m venv .venv-browser
.\.venv-browser\Scripts\python.exe -m pip install -r requirements-browser.txt
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD ".playwright-browsers"
.\.venv-browser\Scripts\python.exe -m playwright install chromium
```

Danach genügt ein Befehl:

```powershell
.\test-browser.ps1
```

Falls PowerShell die Skriptausführung sperrt, direkt das Python-Modul starten:

```powershell
.\.venv-browser\Scripts\python.exe -m browser_tests
```

Optional mit sichtbarem Browser oder nur einem Ablauf:

```powershell
.\test-browser.ps1 -Headed
.\test-browser.ps1 -Headed -SlowMo 700 -Filter shared_library
.\test-browser.ps1 -Filter shared_library
```

Unter Linux/macOS dieselben Pakete in einer venv installieren, dann:

```sh
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright-browsers"
python -m playwright install --with-deps chromium
python -m browser_tests
```

Der Runner setzt standardmäßig den Browsercache `.playwright-browsers` im
Projekt. Bei einer bestehenden Installation kann `PLAYWRIGHT_BROWSERS_PATH`
bewusst auf einen anderen Browsercache zeigen. Das ist kein Benutzerprofil;
sämtliche Browser-Kontexte werden pro Test neu angelegt.

## Abgedeckte Abläufe

| Browser-Szenario | Geprüfte Schritte |
|---|---|
| Registrierung und Identität | Registrierung nur mit Benutzername und Passwort, auch mit einem Zeichen; Logout; fehlerhafter und erfolgreicher Login; zwei getrennte Konten ohne vermischte Cookies; fehlende Adminrechte eines Spielers |
| Gemeinsame Multiworld | Spieler lädt APWorld und Original-YAML hoch; automatische Bibliotheksaktualisierung; anderer Spieler sieht das Spiel; Admin deaktiviert und aktiviert die bekannte Testversion; Alice erstellt eine Lobby ohne Spiel; Bob meldet sich erneut an, sieht sie und tritt ohne Spiel bei; beide wählen ihr Spiel direkt in der Lobby, bearbeiten und prüfen den YAML-Entwurf und klicken „Auswahl übernehmen“; Bereitschaft, simulierte Generierung, Seed-ZIP, Historie, Statistik, Spoiler und Item-Drilldown |
| Blockierung und Korrektur | Fehlende Bereitschaft erzeugt keinen Build und keinen Generatoraufruf; ungültige Zahlen und Nullgewichtungen werden nicht gespeichert; Bob bleibt unbereit; nach Korrektur und Bereitschaft funktioniert die Generierung ohne Reparatur oder Neustart |
| Mobile Oberfläche | Navigation und aktive Seite, kombinierte Bibliotheksfilter, Presets und Anleitung, zwei Spieler in einer Lobby, getrennte Hostaktionen, direkt bedienbare Teilnehmerliste und keine seitliche Seitenüberbreite bei 390 Pixeln; helle Inhalte auch bei dunkler Betriebssystem-Einstellung |

Das Mehrspieler-Szenario verwendet drei getrennte Kontexte: Alice, Bob und
einen administrativen Host. Die Spieler registrieren sich tatsächlich über die
Website und werden nicht per Cookie oder Test-Login eingeschleust. Nur der
anfängliche TestAdmin wird für die Testumgebung mit einem persönlichen Passwort
angelegt. Alice besitzt als Erstellerin Hostrechte für ihre Lobby, ohne Admin zu
sein. Die explizite Admin-Aktivierung wird zusätzlich zur automatischen
Upload-Aktivierung getestet; eine Freigabepflicht wird nicht wieder eingeführt.

Die im Browser angezeigten YAMLs werden mit den tatsächlich an den Mock-Generator
übergebenen Dateien verglichen. Der heruntergeladene ZIP-Inhalt wird ebenfalls
geprüft. Die synthetischen Statistikdaten existieren ausschließlich im
wegwerfbaren Testserver und werden nicht in die normale Anwendung eingebaut.

## Isolation und Datenerhalt

- Jeder Browser-Test startet einen eigenen Serverprozess mit eigener SQLite-DB,
  Uploads, Schema-Cache, AP-Attrappe und Seed-Verzeichnis in einem OS-Tempordner.
- Der Server bindet nur `127.0.0.1` und einen vom Betriebssystem zugewiesenen freien
  Port. Port 8080 und vorhandene Server werden nicht angesprochen oder beendet.
- Alle `HUB_`- und `AP_`-Umgebungswerte werden vor dem Teststart entfernt und die
  Testpfade gesetzt, bevor das `hub`-Paket importiert wird.
- Der Server akzeptiert nur absolute, markierte OS-Tempordner mit dem Präfix
  `archipemanu-browser-`. Arbeitsverzeichnis, relativer `data`-Pfad und
  Produktivdaten sind als Testwurzel ausgeschlossen. Unit-Tests prüfen das.
- Netzwerk-Routing der Browser blockiert Zugriffe außerhalb des eigenen lokalen
  Testservers. Es gibt keine externe Registrierung, keinen Upload und keine
  Verbindung zu archipelago.gg.
- Die APWorld ist ein deterministisches, inertes ZIP. Der Mock akzeptiert nur
  bekannte Fixture-Hashes. APWorld-Code wird nicht importiert und kein echter
  Archipelago-Unterprozess gestartet.
- Nach jedem Test werden nur dessen Serverprozess und temporäre Dateien
  aufgeräumt. Windows beendet dabei den konkret gestarteten Prozessbaum.
- Artefakt-, JUnit- und optional angegebene pytest-Temp-Pfade müssen unter
  `test-results/` liegen. Gefährliche Overrides werden vor dem Start der Fixtures
  abgewiesen, da Playwright sein Ausgabeverzeichnis bereinigt.

## Fehlerdiagnostik

`pytest.ini` aktiviert Screenshots und Traces bei Fehlern. Die Kontexte werden
über die Playwright-`new_context`-Fixture erzeugt, damit auch alle zusätzlichen
Spielersitzungen in die automatische Fehlerdiagnostik aufgenommen werden.
Siehe [Playwright-Pytest](https://playwright.dev/python/docs/test-runners).

Ausgaben des letzten Laufs:

- `test-results/browser-junit.xml`: maschinenlesbarer Testbericht.
- `test-results/browser/…/`: Screenshots und Trace-ZIPs fehlgeschlagener Tests,
  getrennt nach Browser-Kontext.
- `test-results/browser/logs/<test>/server.log`: HTTP-Anfragen, Fehler und
  Mock-Extraktions-/Generierungsereignisse.
- `test-results/browser/logs/<test>/browser.log`: Browserkonsole, JavaScriptfehler,
  fehlgeschlagene Requests und HTTP-Fehlerantworten.
- `test-results/browser/logs/<test>/generator-input.jsonl`: tatsächlich an den
  Mock-Generator übergebene YAMLs, sofern eine Generierung gestartet wurde.

Unbehandelte JavaScriptfehler lassen einen Test ebenfalls fehlschlagen.
Erwartete HTTP 401/403 aus den Negativtests werden protokolliert und sind keine
unbehandelten JavaScriptfehler. Logs entstehen auch bei erfolgreichen Tests.
Screenshots und Traces werden nur bei Fehlern behalten. Der nächste Lauf ersetzt
die vorherigen Browserartefakte; relevante Fehlerdateien vorher sichern.

Eine Trace-Datei lokal öffnen:

```powershell
.\.venv-browser\Scripts\python.exe -m playwright show-trace PFAD_ZUR_TRACE.zip
```

## GitHub Actions

`.github/workflows/tests.yml` enthält getrennte Python- und Browser-Jobs für
Feature-Branches und Pull Requests. Der Browser-Job installiert die festgelegten
Testpakete sowie Chromium mit seinen Linux-Systemabhängigkeiten und startet
`python -m browser_tests`. `test-results/` wird auch bei Fehlern als Artefakt
hochgeladen und sieben Tage aufbewahrt. Das folgt dem
[Playwright-CI-Ablauf](https://playwright.dev/python/docs/ci).

Die bisherige Python-Suite bleibt unabhängig von Playwright:

```powershell
.\.venv-browser\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v
```

## Ergebnisse vom 7. November 2026

Lokal unter Windows mit Python 3.13.14, pytest 8.4.2, Playwright 1.64.1 und
pytest-playwright 0.10.0 ausgeführt. Chromium läuft standardmäßig headless.

| Prüfung | Ergebnis des abschließenden Laufs |
|---|---|
| Vollständige Python-Suite mit strenger Ressourcenprüfung | 115 Tests erfolgreich, 25,7 Sekunden |
| Playwright über `python -m browser_tests` | 4 Szenarien erfolgreich, 31,5 Sekunden |
| PowerShell-Syntaxprüfung und `git diff --check` | Erfolgreich |

- Vier Browser-Szenarien erfolgreich, einschließlich aller zwölf angeforderten
  Schritte und der Korrektur ungültiger Einstellungen.
- Host-Verbindungsformular, Anzeige der gespeicherten Serveradresse in der
  Analyse und Ausblenden der Spoiler werden über die Oberfläche geprüft.
- Erfolgreiche UI-Läufe speichern Desktop- und Mobil-Screenshots in ihren
  jeweiligen Log-Verzeichnissen. Geprüfte Vorschauen der UI-Überarbeitung sind
  zusätzlich unter `test-results/ui/` abgelegt; sie zeigen isolierte Testdaten.
- Die Statistik zeigt Progression-Items nach Empfängerspiel. Der Browser deckt
  gezielt den konkreten Check samt Spieler und Spiel eines Crossworld-Schlüssels auf und prüft, dass die Anzeige vorher
  leer und nach dem erneuten Zuklappen verborgen ist. Die Spielseite zeigt echte
  Check-Zahlen. Python-Tests prüfen Mehrfachexemplare, fehlende Daten, Rechte und
  die Sperre im Race-Modus.
- Die Python-Suite enthält zusätzlich Regressionstests für die sichere
  Testwurzel, Artefaktpfade und den authentifizierten Fortschrittsendpunkt.
- Screenshots und Traces aller Kontexte sowie Logs wurden im zunächst
  fehlgeschlagenen Browser-Lauf tatsächlich erzeugt. Ein mehrdeutiger Link wurde
  im Test präzisiert; die Navigation erhielt dabei einen zugänglichen Namen.
- Website-Korrektur: Nach APWorld-Uploads aktualisieren Bibliothek und
  Spielauswahl jetzt automatisch den Status `queued/running`. Der neue
  Gruppen-Fortschrittsendpunkt liefert ausschließlich den Status; ausführliche
  Worker-Logs bleiben im geschützten Adminbereich.

Der GitHub-Actions-Job ist konfiguriert, aber ohne Push hier nicht auf GitHub
ausgeführt worden. Eine echte Multiworld-Generierung mit fremden APWorlds wird
durch diese regulären CI-Tests bewusst nicht behauptet. Die Testläufe greifen
weder auf den produktiven `data`-Ordner noch auf den Produktivserver zu.
