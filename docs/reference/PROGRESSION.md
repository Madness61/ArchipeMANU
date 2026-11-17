# Progression und Item-Finder

## Regulärer Ablauf

`progression_worker.py` rekonstruiert den Seed aus ursprünglichem Seedwert und archivierten Spieler-YAMLs. Version, ausführbare AP-Quellen/APWorld-Bytes, Modellhash, Optionen, Platzierungen und deterministische Regelproben müssen übereinstimmen. Bei Abweichung wird abgebrochen. Die Proben sind begrenzte Zeugen, kein formaler Beweis sämtlicher Inventare.

`progression/inventory.py` gleicht das vollständige beobachtete Inventar mit dem eigenen Slot ab. Unveränderliches Startinventar und negative Start-Empfänge zählen genau einmal. Echte Empfänge müssen zu Finder/Check/Item/Empfänger passen. Fehlende, doppelte oder nicht zuordenbare Empfänge sowie unvollständige Checklisten werden abgelehnt. Nur eigene adresslose Events werden gesweept; erreichbare normale Checks und fremde Inventare werden nicht stillschweigend vergeben.

`progression/engine.py` bildet pro fehlender Progression-Itemart genau einen Versuch: Kopie des aktuellen `CollectionState`, ein zusätzliches Exemplar mit der registrierten APWorld sammeln, eigene Events auswerten, offene erreichbare Check-IDs und Regionen vergleichen. Alle verbleibenden Fundorte dieser Art bleiben verknüpft. Progressive Items berücksichtigen vorhandene Kopien. Die Ausgangskopie wird nicht verändert.

Ergebnisse werden nach Anzahl neuer Checks absteigend, dann neuen Regionen absteigend und Itemname alphabetisch sortiert. Region-only-Ergebnisse sind hilfreich. Alle Typen werden bis zum Zeitlimit geprüft; es gibt keine feste 40er-Grenze. Eine unvollständige Analyse nennt die genaue geprüfte/gesamte Typenzahl, z. B. 38 von 52. Nicht geprüfte Typen sind unbekannt, nicht wirkungslos. Sphären bestimmen bei begrenzter Zeit lediglich die Prüf-Reihenfolge.

Normale Aufträge importieren weder Paarlogik noch Ziel-/Notwendigkeitsanalyse. `progression/extensions/combinations.py` und `progression_recommendations.py` bewahren ausschließlich die deaktivierte Erweiterung mit Regressionen. Es gibt keine produktive Route für Kombinationen.

Ein bestimmter Check oder Bereich kann weiterhin optional eingeklappt ausgewählt werden. Die Anzeige vergleicht ihn ausschließlich mit den bereits berechneten Mengen pro Einzelitem. Sie ändert weder Sortierung noch Prüf-Reihenfolge und benötigt keine weiteren AP-Regelaufrufe.

## Eigener Zielauftrag

Nur `mode=goal` ruft `progression/goals.py` auf. Der eigene Button startet diesen Auftrag ausdrücklich; ein Tabwechsel/GET liest nur den vorhandenen Cache. Das aktuelle Inventar wird gegen das AP-Abschlussziel geprüft. Für Notwendigkeit werden erreichbare vollständige Itemketten einmal mit und einmal ohne ein konkretes platziertes Exemplar ausgewertet. Ein notwendiges Exemplar ist daher eine Aussage über genau diesen Seed und diese Kopie. Ersetzbare Einzelkopien können gemeinsam trotzdem nötig sein. Keine Gegenprobe bei nicht erreichbarem Vollziel wird als sicher notwendig ausgegeben.

## Grenzen und Ressourcen

- Ein separater Prozess, 90 Sekunden harte Gesamtlaufzeit, 2 GiB Prozessspeicher; 12 Sekunden weiches Analysebudget.
- Eine Worker-Warteschlange, maximal vier aktive/ausstehende Aufträge; gemeinsamer AP-Lock. Ein hängender einzelner AP-Regelaufruf kann erst durch das Prozesslimit gestoppt werden.
- Cache-Schlüssel enthält Modus, Algorithmusversion, Seed-Evidenz, Inventar und Checkzustand. Veraltete Paar-Caches werden nicht wiederverwendet. Empfangs-/Checkänderungen erzeugen einen neuen Schlüssel.
- GET startet niemals einen Job; POST benötigt Anmeldung, eigene Slotrechte, Spoilerfreigabe, CSRF und Rate-Limit. Race sperrt auch direkte API-Aufrufe.
- Item-Link-Gruppen bleiben ausdrücklich nicht unterstützt. Echte lokale Story-/Speicherzustände werden nicht gelesen. Ein in AP erreichbarer Check kann lokale Spielaktionen voraussetzen.
- Bereitschaft, Konsole, Suchfunktion und Seed-Generierung sind von einem fehlgeschlagenen Hilfsjob unabhängig. Historische Seeds ohne Evidenz behalten die Itemsuche, sofern verifizierte Platzierungen vorliegen.

## Oberfläche und Daten

Zehn hilfreiche Items sichtbar, weitere per **Mehr anzeigen**. Jede Karte nennt konkrete Fundorte, Finder/Welt und separat bestätigten Check-/Empfangsstatus; zusätzliche Kopien und neue Checks bleiben aufklappbar. Typen ohne Einzeleffekt sind eingeklappt und können später/in Kombination wichtig sein. Keine Aussage, dass viele Checks ein notwendiges Zielitem beweisen.

Der globale Finder nutzt ausschließlich validierte `item_placements.json`-Daten. Events, Startinventar und Gruppenslots sind keine normalen Platzierungen. Zeitstempel kennzeichnen Beobachtungsstände, keine erfundenen Fundzeiten. [API-Vertrag](API.md), [Tests und native Spiele](../DEVELOPMENT.md).
