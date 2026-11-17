> Historischer Stand bis 17.11.2026. Keine aktive Anleitung oder Aufgabenliste. Aktuell: [Dokumentation](../DEVELOPMENT.md).

# Universelle Progression-Hilfe und globaler Item-Finder

Stand: 16. November 2026. Die Verbesserung der Empfehlungen liegt auf
`feature/progression-recommendations`, auf dem vollständigen Stand von PR #15
einschließlich Upgrade-Reparatur (`3a40e1b`). PR #15 ist weiterhin offen;
`main` steht bei Beginn dieser Erweiterung auf `28d9c80`.

## Benutzung und tatsächlich implementierter Umfang

Direkt über dem Itemprotokoll der laufenden Rundenzentrale stehen **Item suchen**
und **Was bringt mich weiter?**. Beide öffnen dieselbe ergänzende Ansicht,
ohne Seitenwechsel oder zusätzlichen Eintrag in der Hauptnavigation. Die Konsole
bleibt bestehen; ungesendete Nachrichten werden durch die Hilfe nicht verändert.

Nach ausdrücklicher persönlicher Spoilerfreigabe gibt es drei Bereiche:

1. **Item-Finder:** Suche über Itemnamen, beide Spieler, beide Spiele und den
   konkreten Fundort im gesamten gespeicherten Seed. Alle/meine Items,
   Progression/Useful/Filler/Trap und Checkzustände lassen sich kombinieren.
   Jede Platzierung ist ein eigenes Ergebnis, auch bei gleichen Itemnamen.
2. **Meine nächsten Möglichkeiten:** Eigener Slot, aktuell logisch erreichbare
   offene Checks, Simulation noch nicht bestätigter Progression-Items und
   begrenzter Zweierkombinationen. Die Spieler müssen keinen Itemnamen kennen.
   Optional kann ein offener Check oder ein Bereich ausgewählt werden.
3. **Spielziel:** Aktuelle APWorld-Zielbedingung und geprüfte Entfernung einzelner
   konkreter Itemexemplare aus den erreichbaren zukünftigen Itemketten.

Zusätzliche Checks und Bereiche sind aufklappbar; Empfehlungen führen direkt zu
konkreten Fundorten einschließlich Finder, Spiel und beobachtetem Check-Status.
DE/EN, zentrale Theme-Tokens, Systemmodus und Spielerfarben werden weiterverwendet.

Die historische UT-Installation wird weder verwendet noch heruntergeladen.
`hub/logic_routes.py` bleibt deaktiviert (HTTP 410). Es gibt keine Spieladapter
und keine speziellen Itemnamen oder Zugangsregeln im Produktionscode.

## Bestehende Daten und Itemstatus

`hub.stats.valid_distribution()` und `valid_item_details()` validieren weiterhin
`item_distribution.json` und `item_placements.json`. Der Finder verwendet
ausschließlich diese vorhandenen, übereinstimmenden Daten. Historische Seeds ohne
vollständige Platzierungen zeigen eine verständliche Meldung.

Diese Daten enthalten adressierte Platzierungen zwischen echten Spielerslots.
Events, Startinventar und Gruppenempfänger sind in dieser bestehenden Statistik
nicht enthalten; die Oberfläche nennt diese Grenze ausdrücklich. Bei Seeds mit
Item-Link-Gruppen darf die angezeigte Teilmenge nicht als vollständiger Pool
einschließlich Gruppeninventar verstanden werden.

Ein erledigter Fundort und ein beim Empfänger bestätigtes Item sind verschiedene
Felder. Empfang wird nur anhand des vollständigen Inventar-Snapshots dieses
Empfängers und des Tupels `(Item-ID, Finder-Slot, Location-ID)` bestätigt. Ein
`ItemSend`-Logeintrag allein ist kein Empfangsnachweis. Gleiche Itemnamen und
gleiche Item-IDs an unterschiedlichen Orten bleiben unterscheidbar.

Die Statusquellen sind:

- atomar gespeicherte vollständige `ReceivedItems`-Listen und Checked/Missing
  Locations des bestehenden, identitätsgeprüften Textclients;
- bereits gespeicherte WebHost-API-Daten, ausschließlich bei übereinstimmender
  Spieler-/Spiel-/Slotzuordnung. Es erfolgt kein zusätzlicher Upstream-Abruf.
  Fehlende Checks werden nur bei passender vollständiger Check-Anzahl abgeleitet.

Die Beobachtungszeit steht am Ergebnis. Unbekannte Zustände bleiben unbekannt.
Bei Raum-/Endpointwechsel werden alte Snapshots nicht dem neuen Endpoint
zugerechnet. Die vorhandene Portwechsel-/Reconnect-Logik bleibt unabhängig.
Bei Unterbrechung oder unvollständiger Inventarsynchronisierung wird ein alter
Snapshot für neue dynamische Auswertungen gesperrt; historische Finderangaben
bleiben mit ihrem Beobachtungszeitpunkt nutzbar. Eine neue vollständige
Synchronisierung hebt die Sperre auf. Bestehende Ping-Antworten halten einen
weiterhin synchronisierten Snapshot frisch, ohne zusätzliche Netzwerkanfragen.

## Generation: ursprüngliche Regeln und Herkunft

Nach erfolgreicher Nicht-Race-Generierung speichert `ap_runner.py` zusätzlich
`progression_seed.json` (Formatversion 1). Es enthält:

- tatsächlichen numerischen Generierungsseed und Archipelago-Version;
- SHA-256 der unveränderten ursprünglichen Spieler-YAMLs;
- tatsächlich aufgelöste Optionen aller Spieler, APWorld-Modulversion und bei
  Custom Worlds den SHA-256 des Archivs;
- Spieler, Gruppen, vorab gesammelte Items, alle Locations mit Items sowie
  Regionen und verbundene Ausgänge als reine JSON-Beschreibung;
- Hash dieses Modells;
- Fingerabdruck von AP-Quellcode, Spielressourcen, installierten APWorlds,
  Python und installierten Paketversionen;
- tatsächliche `get_spheres()`-Ergebnisse, soweit rechtzeitig berechenbar;
- vier deterministische Erreichbarkeitsproben mit verschiedenen Inventaren,
  einschließlich Regionen und Completion Conditions.

Es werden keine Python-Objekte, Lambdas oder Pickles gespeichert. Der bestehende
Seed-Snapshot in SQLite und die ursprünglichen YAML-Dateien bleiben unverändert.

Die zusätzliche Analyse ist optional: Fehler werden abgefangen. Die statische
Regelauswertung läuft im auslaufenden Generatorprozess als Daemon-Probe mit
höchstens fünf Sekunden Wartezeit; hängt eine fremde Regel, wird die Analyse als
nicht verfügbar gespeichert. Die erfolgreiche Spielausgabe wird deswegen nicht
verworfen. Die unmittelbare Herkunftserfassung selbst erfolgt ohne Regelaufrufe.
Race-Generierungen schreiben überhaupt keine dieser Spoilerdaten.

## Dynamischer Worker und Validierung

`hub/progression.py` koordiniert Hintergrundjobs; `progression_worker.py` läuft in
Archipelagos Python außerhalb des Flask-Prozesses. Er benötigt die ursprünglichen
YAML-Dateien, den numerischen Seed und die identische Laufzeit.

Der Worker erzeugt eine neue Multiworld über `Generate.main()` und `Main.main()`
mit `--skip_output`, ohne Patch, ROMausgabe oder neuen spielbaren Seed. Dadurch
werden sowohl gewichtete Optionen als auch die eigentliche Welt erneut gerollt.
Vor einer Bewertung werden folgende Bedingungen geprüft:

1. Laufzeit und Paketversionen passen zum gesicherten Fingerabdruck.
2. Alle YAML-Dateien stimmen mit ihren SHA-256-Werten und dem DB-Snapshot überein.
3. Spieler/Spiele, aufgelöste Optionen, Gruppen, Startinventar, Location- und
   Item-IDs, **sämtliche** Platzierungen und Regionverbindungen ergeben denselben
   Modellhash.
4. Die vier gespeicherten Erreichbarkeitsproben ergeben identische Ergebnisse.
5. Der Serverzustand passt zum eigenen Slot und zur vollständigen Checkmenge.

Ein abweichendes Modell, fehlende Originaldaten, veränderte APWorld oder
abweichende Regelproben führen zu **keiner dynamischen Bewertung**. Finder und
statische Daten bleiben unabhängig verfügbar.

Die Proben sind zusätzliche Zeugen, kein mathematischer Beweis über alle
möglichen Inventare oder beliebige nichtdeterministische Drittanbieter-APWorlds.
Die Wiederherstellung setzt deterministisches Verhalten mit identischem Seed
und identischer Laufzeit voraus. APWorlds mit versteckten, nicht reproduzierbaren
externen Zuständen können keine universell garantierte Unterstützung erhalten.

## Inventar, Simulation und Events

`progression_model.analyze()` verwendet die installierten APIs von Archipelago
0.6.8: `CollectionState`, `collect(..., prevent_sweep=True)`,
`sweep_for_advancements()`, `can_reach()` und `has_beaten_game()`.

Die Ausgangsbasis ist das echte Startinventar aus der rekonstruierten Welt.
Die in `ReceivedItems` erneut gemeldeten Startkopien werden genau einmal
abgeglichen und nicht doppelt gesammelt. Danach werden ausschließlich bestätigte,
zum Seed passende eigene Empfänge gesammelt. Zusätzliche synthetische/Serveritems
oder nicht zuordenbare Empfänge führen zum sicheren Rückfall.

Nur adresslose Events der eigenen Welt werden für die aktuelle Erreichbarkeit
gesweept. Die Engine verleiht nicht stillschweigend Items aus erreichbaren
normalen Checks oder aus ungespielten Welten anderer Spieler. Bereits erledigte
Checks werden aus der offenen Erreichbarkeitsliste entfernt.

Jeder Kandidat wird mit `state.copy()` separat hinzugefügt. Die APWorld selbst
verarbeitet progressive Items und Zählbedingungen. Als Ergebnis werden konkret
neu erreichbare Check-IDs und Bereiche sowie die Zielbedingung verglichen.
Progression-Klassifikation allein ist kein Beweis für einen unmittelbaren Nutzen.

Es werden bis zu 40 Itemarten einzeln und bis zu 80 Paare aus höchstens zwölf
Arten getestet, einschließlich zweier gleicher Items bei genügend verbleibenden
Kopien. Die Auswahl verwendet die unten beschriebene deterministische Strategie;
nicht untersuchte Kandidaten oder
Paare werden ausdrücklich als unvollständig gekennzeichnet. Es gibt keine
Behauptung einer exakten Türvoraussetzung: belegbar ist eine Erreichbarkeit unter
der getesteten Inventarerweiterung. Tiefe drei und erschöpfende Suchen fehlen.

### Gesamteffekt und zusätzlicher Kombinationseffekt

Die Engine empfiehlt ein Paar **nicht**, nur weil es gegenüber dem aktuellen
Inventar Fortschritt ermöglicht. Sie vergleicht dessen echte Check- und
Regionsmengen zusätzlich mit den beiden zuvor vollständig ausgewerteten
Einzelergebnissen:

- `C0`: aktuell erreichbare offene Checks;
- `CA`, `CB`: mit einem zusätzlichen Exemplar von A beziehungsweise B erreichbar;
- `CAB`: mit beiden Exemplaren erreichbar;
- Gesamteffekt des Paars: `CAB - C0`;
- ausschließlicher Kombinationseffekt: **`CAB - (CA ∪ CB)`**.

Für Regionen gilt dieselbe Mengenoperation. Es werden IDs beziehungsweise
Regionsnamen verglichen, keine bloßen Anzahlen. Ein Paar mit gleich vielen,
aber anderen Checks bleibt deshalb ein anderes Ergebnis. Gleiche Kopien eines
progressiven Items werden als A + A geprüft: Der Einzeleffekt kommt dann von
einer, der Paareffekt von zwei weiteren verfügbaren Kopien.

Ein Paar wird nur behalten, wenn es exklusive Checks oder Regionen erschließt,
erstmals die Completion Condition erfüllt oder das ausgewählte Ziel erstmals
erreichbar macht, während das **keines** seiner Einzelitems schafft. Ein bereits
erreichbares Ziel ist kein neuer Nutzen. Fehlende Einzelversuche gelten als
unbekannt und niemals als Nullwirkung.

Beispiele: A +15, B +0, Paar +15 wird unterdrückt. A +10, B +5, Paar +15 wird
bei unabhängigen Effekten ebenfalls unterdrückt. Öffnet das Paar fünf Checks
außerhalb der vereinten Einzeleffekte, werden Gesamteffekt und diese fünf
exklusiven Checks getrennt ausgewiesen. Die Prüfung ist nach
`progression_recommendations.py` ausgelagert, verwendet aber ausschließlich die
von AP-Regeln tatsächlich berechneten Ergebnisse.

### Auswahl und Reihenfolge der Kandidaten

Alphabetische Reihenfolge ist kein Wichtigkeitskriterium mehr. Vor den
Einzelversuchen werden fehlende Itemarten nach der frühesten gespeicherten
theoretischen Seed-Sphere ihrer Platzierungen eingeplant. Gleichstände und
fehlende Sphereinformationen werden über einen stabilen SHA-256 aus Seed,
Spielslot und Itemname geordnet. Die ersten höchstens 40 Arten werden simuliert.
Spheres sind ein Planungshinweis, kein aktueller Zustand anderer Spieler.

Danach gelten für die maximal zwölf Paar-Kandidaten folgende Kriterien:

1. Tatsächlich gemessene Wirkung für ausgewähltes Ziel und Spielabschluss.
2. Falls budgetierbar: zusätzliche Auswahlprobe in einem optimistisch mit den
   **bereits einzeln geprüften** verbleibenden Items vervollständigten Inventar.
   Verhindert die Entfernung einer gesamten Itemart dort das ausgewählte Ziel
   beziehungsweise ohne Zielwahl den Abschluss, erhält sie Auswahlpriorität.
   Diese Probe ist ausdrücklich **kein** endgültiger Notwendigkeitsnachweis.
3. Reservierte Auswahlplätze: bis zu sechs kritische Arten, bis zu zwei Arten
   mit mehreren verbleibenden Kopien, bis zu vier ohne einzelne Check-/Regions-
   Wirkung, danach nach Einzelwirkung priorisierte Arten bis zum Gesamtlimit.
   Bereits gewählte Arten werden nicht doppelt belegt.
4. Gültige Paare werden nach Beteiligung priorisierter Arten, Zweitkopien,
   Paaren einzeln wirkungsloser Arten und gemessener Einzelwirkung eingeplant.

Die zusätzliche Zielprobe darf höchstens 20 Prozent des zu diesem Zeitpunkt
verbleibenden Zeitbudgets belegen. Teure einzelne AP-Regeln bleiben durch das
harte Prozesslimit abgesichert. Die Reihenfolge ist deterministisch; bei
Zeitablauf bleibt nur der vollständig ausgewertete Präfix des Suchlaufs erhalten.
Kein Auswahlverfahren garantiert, unter diesen Grenzen jede Kombination zu finden.

`combinations_tested` zählt tatsächlich simulierte gültige Paare, auch verworfene
redundante Ergebnisse. Der Nenner `combinations_total` umfasst alle möglichen
Paare der noch fehlenden Itemarten: `n*(n-1)/2` plus die Arten mit mindestens zwei
verbleibenden Exemplaren. Ungültige A+A-Paare bei nur einer vorhandenen Kopie
werden nicht mitgezählt. Zusätzliche Metadaten nennen die Poolgröße und die
tatsächlich einzeln geprüften Arten. Die Website zeigt z. B. „69 von 81 möglichen
Itemkombinationen untersucht“; fehlende Empfehlungen beweisen keine Unmöglichkeit.

### Darstellung und Cache

Hilfreiche Einzelitems erscheinen immer vor echten Kombinationen. Innerhalb
jeder Kategorie haben neu erreichbare ausgewählte Ziele und Abschlüsse Vorrang,
danach Check- und Regionsgewinn; Paare werden zuerst nach ihrem exklusiven
Zusatznutzen bewertet. Die Anzeige nennt keinen bloßen Fortschrittsweg zwingend
notwendig; dafür bleibt die gesonderte Exemplar-Zielprüfung zuständig.

Identische tatsächliche Ergebnismengen werden als Alternativen gruppiert.
Unterschiedliche Check-IDs mit gleicher Anzahl werden nicht zusammengelegt.
Pro Kategorie sind zunächst höchstens sechs Ergebnisgruppen geöffnet sichtbar;
weitere Gruppen und gleichwertige Rezepte sind aufklappbar. Einzeln wirkungslose
Arten erscheinen nur in einer zusätzlichen aufklappbaren Liste. Bei Paaren
zeigen getrennte Drilldowns exklusive Checks/Regionen und den Gesamteffekt.

Die Ergebnisversion **2** fließt in den Job-Cache-Schlüssel ein. Alte erfolgreiche
Berechnungen werden nicht als neue Empfehlungen wiederverwendet; sie bleiben
gespeichert. GET berechnet weiterhin nichts automatisch. Die Browseranzeige
vergleicht auch ältere, bereits laufende API-Antworten defensiv mengenbasiert,
damit beim Update keine redundanten alten Paare wieder sichtbar werden.

Die JSON-Antwort enthält weiterhin `new_checks` und `new_regions` als
Gesamteffekt gegenüber dem aktuellen Inventar. Behaltene Paare tragen zusätzlich
`synergy: {checks, regions, goal, target}` mit dem ausschließlichen Paareffekt.
`goal_gain` und `target_gain` berücksichtigen den Ausgangszustand. `helpful`
markiert hilfreiche Einzelergebnisse; wirkungslose Einzelversuche bleiben für
Nachvollziehbarkeit erhalten. `effect_key` gruppiert identische tatsächliche
Ergebnismengen. `singles_tested`, `candidates_total`, `combinations_tested`,
`combinations_total` und `combinations_selected` beschreiben die Suchabdeckung;
die Anzahl sichtbarer Empfehlungen ist keine Anzahl ausgeführter Simulationen.

Die Logik beschreibt die APWorld mit den gewählten Fähigkeiten/Tricks. Sie liest
keine lokalen Spielstände und beweist nicht, dass ein Spieler eine Storyaktion
bereits ausgeführt hat oder einen schwierigen Trick beherrscht.

## Zielanalyse und Grenzen

Zunächst wird die echte Completion Condition mit dem gemeldeten eigenen Inventar
geprüft. Für die Notwendigkeit wird zusätzlich eine vollständige **logische**
Itemkette aus allen Welten gesweept. Danach wird jeweils eine konkrete
Platzierung entfernt und die gesamte erreichbare Kette von vorne ausgewertet.

Nur wenn das Ziel mit der vollständigen Kette erreichbar ist und ohne diese
Kopie nicht mehr, wird das Exemplar als nachweislich notwendig innerhalb dieses
Modells bezeichnet. Alternative Wege und andere Kopien bleiben enthalten.
Ist die Grundkette nicht erfolgreich, lautet das Ergebnis unbekannt.

Bis zu 20 konkrete Exemplare werden geprüft. Ersetzbare Einzelkopien können
zusammen notwendig sein; die Engine behauptet keine vollständige Liste minimaler
Zielkombinationen und führt keine erschöpfenden Mehrfachentfernungen durch.

Item-Link-Gruppen sind für die dynamische Inventar-/Zielbewertung derzeit bewusst
nicht unterstützt. Andere Teilnehmerinventare werden nicht geraten. Das Modell
hat keine Spiele-Sonderregeln und kann Grenzen einer APWorld nicht korrigieren.

## Unterstützungsstufen

| Stufe | Tatsächlich verfügbare Funktionen |
|---|---|
| Basis | Verifizierte gespeicherte Platzierungen und globale Suche, falls vorhanden |
| Teilweise | Zusätzlich statische Spheres oder eine geprüfte, begrenzte dynamische Auswertung |
| Verifizierte Logikhilfe | Rekonstruktion und Inventarprüfung erfolgreich, alle innerhalb der gesetzten Grenzen relevanten Einzel-, Paar- und Exemplarprüfungen abgeschlossen |

Die letzte Bezeichnung ist kein Versprechen vollständiger Unterstützung jeder
beliebigen APWorld oder beliebig großer Kombinationen. Bei typischen größeren
Seeds bleibt die Kennzeichnung wegen der Berechnungslimits **Teilweise**.
Für historische Seeds werden fehlende Rekonstruktionsdaten nicht nachträglich
erfunden und keine gespeicherten Seeds ersetzt.

## Sicherheit, Isolation und Betrieb

- Nach dem Wechsel auf diesen Branch den **Hub-Prozess** neu starten, damit
  Routen und additive Tabellen geladen werden. Ein laufender älterer Python-
  Prozess kennt neue Routen auch dann noch nicht, wenn er neue Vorlagen liest.
  Die Hilfe wird deshalb nur bei gesetztem Backend-Verfügbarkeitsmerkmal
  eingeblendet; ältere Prozesse behalten ihre Rundenzentrale und Konsole.
  Der externe Archipelago-Spielserver benötigt dafür keinen Neustart.
- Bestehende Lobby-/Adminrechte und persönliche Slotrechte gelten serverseitig.
- Race blockiert sämtliche neuen Ansichten und APIs, auch direkte URLs.
- Platzierungen und Analysen erfordern vorher einen angemeldeten, CSRF-geschützten
  POST für persönliche Spoilerfreigabe. Erneutes Sperren schützt auch JSON-Abrufe.
- Persönliche Analysen sind auch für Admins ausschließlich für eigene Slots.
- Keine Berechnung beim Seitenbesuch oder GET; Start nur per explizitem POST.
- Ein Workerprozess je Ausführung, ein Job gleichzeitig pro Hub-Prozess, maximal
  vier ausstehende Jobs in SQLite. Queue-Zustand und Resultate bleiben gespeichert.
- 90 Sekunden Prozesslimit und hartes Speicherlimit von 2 GiB. Linux nutzt
  `RLIMIT_AS`, Windows ein Job Object. Fehlende Begrenzung führt zum Rückfall.
- Ausgaben werden begrenzt eingelesen; native Worker-Logs werden nicht als
  ungefilterte Benutzerfehler oder öffentliche Servertexte ausgegeben.
- Die vorhandene AP-Sperre schützt vor gleichzeitigen APWorld-Änderungen. Ist sie
  belegt, wartet die Hilfe höchstens zwei Sekunden und meldet Auslastung.
- Cache nach Seed, Inventar, Checks und ausgewähltem Ziel. Beobachtungszeit allein
  löst keine neue Berechnung aus. Ein neuer Empfang/Check macht den Cache ungültig.
  Erfolgreiche Ergebnisse werden wiederverwendet; Fehler können nach 15 Sekunden
  bewusst erneut angefragt werden. GET startet auch dann keinen neuen Worker.
- Additive Tabellen `progression_live` und `progression_jobs`, Fremdschlüssel mit
  Cascade. Kein Reset vorhandener Konten, Seeds, Vorlagen oder Einstellungen.
- Textclient, Reconnect, Chat, Host-Recorder und WebHost-Polling bleiben unabhängig
  vom Worker. Die Live-Anbindung sammelt keine neuen Checks für das Spiel.

## API

Basis: `/sessions/{sid}/builds/{bid}/progression`.

| Methode / Pfad | Funktion |
|---|---|
| GET Basis | Hilfsansicht, noch ohne offengelegte Platzierungen |
| GET `/state` | Freigabe und statische Verfügbarkeit, ohne Spoilerdaten |
| POST `/consent` | `reveal=1` freigeben, `reveal=0` erneut sperren |
| GET `/items` | `q`, `owner=all/mine`, `category`, `status`, `page`; maximal 50 Ergebnisse |
| GET `/analysis` | Status/Cache für eigenen `slot`; erzeugt keinen Job |
| POST `/analysis` | Eigenen `slot` analysieren; optional `target_kind=location/region` und `target_id/target_name` |

Alle Antworten sind `no-store`. Statusangaben sind Beobachtungen, keine
erfundenen Fundzeiten. `new_checks` enthält echte Location-IDs; `items.placements`
verknüpft Empfehlungen mit den vorhandenen validierten Platzierungen.

## Tests und überprüfte Spielmodule

Standardtests: `python -m unittest discover -s tests -v`.
Browser: `python -m browser_tests`.
Reale AP-Integration: `python -m unittest discover -s integration_tests -v`.

Die regulären Tests verwenden temporäre DBs und inerte Testserver. Die Browser-
Suche verwendet die echte API und den vorhandenen Mock-Generator. Zusätzlich
wird die Ergebnisdarstellung mit ausdrücklich markierten UI-Fixtures geprüft;
dieser UI-Test ist kein Beweis einer echten AP-Generierung.

Die echten Integrationen kopieren den lokalen AP-Checkout in ein temporäres
Verzeichnis, erzeugen tatsächlich Spiel-ZIPs, rekonstruieren sie ohne Ausgabe,
vergleichen Modellhash und Regelproben und lehnen einen manipulierten Hash ab.
ChecksFinder wird zusätzlich durch die vollständige angemeldete Flask-API und
den Hintergrundprozess geprüft, einschließlich Cachewechsel nach Empfang.
Keine produktiven Konten, Datenordner oder Online-Räume werden verwendet.

Gesamtlauf des Grundstands vor der Empfehlungskorrektur: **258 Python-Tests erfolgreich (116,1 s)**,
**21 Playwright-Szenarien erfolgreich (295,3 s)** und **3 echte AP-Integrationen
erfolgreich (60,0 s)**. Screenshots der neuen Hilfe in DE/EN, Light/Dark/System
und bei 390/1440 px wurden erzeugt; Desktop und Smartphone wurden visuell geprüft.

Gemessener Einzelspieler-Startzustand mit Seed **20261116**, Archipelago **0.6.8**:

| Modul | Checks | Erreichbar | Bestes einzelnes Item | Bestes geprüftes Paar | Einschränkung |
|---|---:|---:|---:|---:|---|
| ChecksFinder, integriert | 25 | 5 | +1 | +2 | Zielprüfung auf 20 konkrete Exemplare begrenzt |
| Meritous, integriert | 104 | 25 | +0 | +26 | Einzelfortschritt genügt hier am Start nicht |
| Pseudoregalia, Custom-APWorld | 50 | 4 | +9 | +15 | Nur begrenzte Auswahl an Paaren |

Das sind beobachtete Ergebnisse dieser Konfigurationen, keine allgemeingültigen
Kennzahlen der Spiele. Nicht getestet sind echte Spielclients, lokale Story-
Synchronisierung und beliebige fremde APWorlds/Versionen. Item-Link-Gruppen und
nicht reproduzierbare Seeds sind bewusst Rückfallfälle statt behaupteter Erfolge.

### Zusätzliche Abnahme der Empfehlungen

Die überarbeitete Engine ist mit denselben drei tatsächlichen Spielmodulen
geprüft. Für ChecksFinder wurden 6 von 6 gültigen Paaren untersucht, für Meritous
36 von 36 und für Pseudoregalia 69 von 81. Der jeweils größte **exklusive**
Check-Zusatznutzen eines behaltenen Paars beträgt 1, 26 beziehungsweise 6 Checks.
Diese Werte beschreiben wiederum nur die konkreten Test-Seeds und Inventare.

Ein vierter Integrationstest lädt das installierte **Dark Souls III**-Modul,
generiert mit Seed 20261116 ohne Ausgabe und prüft seine echten Regeln mit
`late_basin_of_vows=off` und `after_small_doll`, jeweils ohne DLCs. Das explizite
Regel-Testinventar enthält die übrigen generierten Items und hält Basin of Vows,
Black Eye Orb, Blacksmith Hammer sowie beide genannten Braille Divine Tomes
zurück. Es ist **kein** behaupteter Live-Inventarzustand.

In diesem isolierten Szenario eröffnet Basin of Vows allein 213 Checks und vier
Regionen. Alle vier untersuchten Zusätze liefern keinen exklusiven Paar-Nutzen
und werden unterdrückt. Keine dieser Zahlen ist im Test fest codiert. Eine
weitere Probe ohne Small Doll zeigt den Optionsunterschied: Mit Basin ist
Lothric Castle bei `off` erreichbar, bei `after_small_doll` nicht. Die Engine
erfindet dafür keine eigenen DS3-Regeln. Die aus der laufenden Runde berichteten
73 Checks sind inventar-/optionsabhängig und werden nicht verallgemeinert.

Die regulären Regressionen enthalten redundante, unabhängige und teilweise
synergetische Effekte, Null+Null-Paare, gleiche Anzahlen bei verschiedenen IDs,
reine Regions-/Zielgewinne, Mehrfachkopien, Zielpriorität, deterministische
Kandidatenauswahl, Zeitablauf während der Paarsuche und Cacheversionswechsel.
Ein im Browser-Gesamtlauf offengelegter bestehender Mobil-Test wartet nun auf
die tatsächliche Formularweiterleitung, bevor er das neue Menü öffnet.

Abschließende Abnahme dieser Korrektur: **271 Python-Tests erfolgreich (131,7 s)**,
**21 Playwright-Szenarien erfolgreich (308,1 s)** und **4 echte AP-Integrationen
erfolgreich (79,7 s)**. Der erste Browser-Gesamtlauf hatte den oben beschriebenen
Mobil-Test-Rennfall (20 bestanden, einer fehlgeschlagen); nach der gezielten
Synchronisierung besteht die komplette Suite. Ein zusätzlicher gezielter
Progression-Lauf mit Detail-Screenshots bestand ebenfalls. Desktop/Mobil sowie
DE/EN und alle Themes wurden visuell kontrolliert. Keine Tests mit produktiven
Spielclients oder Online-Räumen.

## Sinnvolle nächste Erweiterungen

- Explizit verifizierte Item-Link-Auflösung inklusive Gruppeninventaren.
- Mehrspieler-Integration mit mehreren tatsächlich generierten Spielmodulen in
  derselben Multiworld, zusätzlich zur vorhandenen Remote-Item-Regelfixture.
- Breitere zielgerichtete Auswahl jenseits des Zwölfer-Pools und Tiefe drei;
  aktuelle Priorisierung bleibt absichtlich begrenzt und transparent.
- Exakte Zielkombinationen unter Entfernung mehrerer konkreter Exemplare.
- Archivierte, isolierte Laufzeitumgebungen pro Seed statt notwendiger identischer
  aktiver AP-Installation; keine stillschweigende Versionsannäherung.
- Reale Abnahme mit Spielclients; keine automatische Ausführung lokaler Aktionen.
