# Spielebibliothek: Informationen und Einrichtung

Die Bibliothek unterscheidet den technischen APWorld-Status von der lokalen
Spieleinrichtung. „Optionen verfügbar“ bestätigt ausschließlich, dass die
Spieloptionen eingelesen wurden. Die Anwendung erkennt weder eine installierte
Spielkopie noch vorhandene ROMs, Emulatoren, Mods oder eine aktive Spielverbindung.

Die 82 bekannten Spiele besitzen in `hub/game_catalog.py` eine deutsche
Beschreibung, mehrere passende Genre-Tags, eine Einrichtungsart sowie konkrete
Voraussetzungen und Einrichtungsschritte. Diese Angaben werden auf den
Spielseiten und bei generierten Runden verwendet. Inaktive Uploads haben eine
eigene Seite unter `/games/<slug>/setup`.

`hub/game_catalog_sources.json` enthält die dazugehörigen Setup- und Download-Links.
Die Basis sind die offiziellen, mit Archipelago 0.6.8 ausgelieferten Dokumente;
die jeweilige Quelldatei ist direkt verlinkt. Borderlands 2 verweist auf die
Anleitung des BouncyLootGod-Projekts. Zusätzlich hinterlegte Gruppenanleitungen
bleiben sichtbar. Versionen von Spiel, Client, Mod und APWorld müssen zueinander
passen; ein Link auf „latest“ ist keine Kompatibilitätsgarantie für ältere Seeds.

Neue, unbekannte Uploads erhalten „Noch nicht zugeordnet“ und „Einrichtung noch
undokumentiert“. Die beim Upload angegebene HTTP(S)-Projektquelle wird angeboten.
Es werden keine Genres oder Installationsanforderungen aus dem Namen geraten.
Für eine neue kuratierte Integration sind beide Katalogdateien zu ergänzen.

Die Filtermöglichkeiten stammen aus der tatsächlich vorhandenen Bibliothek.
Suche, Genre, Einrichtungsart, Herkunft und Unterstützungsstatus wirken gemeinsam.
JavaScript filtert bereits geladene Karten sofort, erhält den Eingabefokus und
speichert die Auswahl in der URL. Ohne JavaScript funktioniert dieselbe Filterung
über das GET-Formular mit der Schaltfläche „Filtern“.

Prüfungen: `tests/test_game_catalog.py`, die Bibliothekstests in
`tests/test_community.py` und die Browser-Szenarien in
`browser_tests/test_players.py`. Der Browser-Test mit 82 Karten verwendet nur
inaktive Beispieldaten im isolierten temporären Testserver, keine echten ROMs,
keine APWorld-Ausführung und keine Produktivdaten.
