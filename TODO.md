# TODO / Roadmap – ArchipeMANU

Stand: 11. November 2026. Dies ist die **priorisierte Aufgabenliste**, kein Nachweis bereits implementierter Funktionen.
Technische Stabilisierung und visuelles Redesign sind **zwei getrennte Arbeitspakete**. Die Archipelago-WebHost-Tracker-API und der experimentelle Universal-Logik-Tracker sind **verschiedene Komponenten**.

## Aktuelle Entwicklungszweige prüfen

- [ ] [PR #7: Rundenzentrale / vereinfachte Navigation](https://github.com/Madness61/ArchipeMANU/pull/7) prüfen und integrieren.
- [ ] [PR #8: Standard-Check-Vorschau](https://github.com/Madness61/ArchipeMANU/pull/8) anschließend prüfen und integrieren.
- [ ] [PR #9: Itemprotokoll und Chat im Mittelpunkt](https://github.com/Madness61/ArchipeMANU/pull/9) anschließend prüfen und integrieren.
- [ ] Vor neuen Featurearbeiten den tatsächlichen Stand von `main` und der offenen PR-Kette kontrollieren. #8 basiert auf #7, #9 auf #8; nicht unabhängig oder ungeprüft auf `main` anwenden.
- [ ] Die reale Nutzerführung mit mindestens zwei Spielern und einer existierenden Runde im Browser abnehmen. Mock-Tests ersetzen keinen echten Spielclient.

## Arbeitspaket A – Verbindungsstabilität und Logik-Tracker deaktivieren

**Priorität: höchste. Eigenständiger Feature-Branch und PR, vor dem UX-Redesign.**

### A1 – Ursache der Verbindungsabbrüche reproduzieren

- [ ] Vier Verbindungsarten auseinanderhalten: Browser ↔ Hub, Hub ↔ WebHost-API, Hub ↔ Archipelago-WebSocket, lokaler Spielclient ↔ Archipelago-Server.
- [ ] Nachstellen: Browser im Hintergrund/anderer Tab, Spiel im Vordergrund, 30+ Minuten, kurzzeitiges WLAN-/VPN-Problem, abgelaufene Authentifizierung, Server nicht erreichbar, Raum gewechselt.
- [ ] In `hub/ap_console.py` die 30-Minuten-Inaktivitätslogik (`IDLE_SECONDS` / `last_seen`) prüfen; die Textverbindung darf nicht nur wegen eines nicht sichtbaren Browserfensters enden.
- [ ] Bei jedem Ausfall Ursache, Zeitpunkt, Verbindungsart und Wiederherstellungsstatus nachvollziehbar protokollieren, ohne Passwörter oder private Nachrichten zu loggen.

### A2 – Zuverlässiger Archipelago-WebSocket

- [ ] Eine **ausdrücklich gestartete** serverseitige Textverbindung während einer aktiven Runde unabhängig vom sichtbaren Browser erhalten; Autorisierung weiterhin regelmäßig prüfen.
- [ ] Automatische Wiederverbindung für **transiente** Netzwerk-, Socket-, Ping- und Timeoutfehler mit begrenztem exponential Backoff plus Jitter implementieren.
- [ ] Bei falschem Passwort, ungültigem Slot, Seed-Mismatch, fehlenden Rechten, Logout, absichtlichem Trennen und abgeschlossenen Runden **nicht** automatisch erneut anmelden.
- [ ] Bestehende Slot-/Seedprüfung, Race-Schutz, WS/WSS-TLS-Regeln und Rechte erhalten; keine automatische Wiederholung bereits gesendeter Chatnachrichten oder Befehle.
- [ ] Nach Reconnect Serverzustand und Empfangsliste erneut synchronisieren, Deduplizierung fortsetzen, alten Socket und Worker zuverlässig entsorgen; pro Benutzer/Seed keine parallelen Reconnect-Schleifen.
- [ ] Verpasste ItemSend-Ereignisse **nicht erfinden**: Unterbrechungszeitraum im Protokoll erkennbar machen, vergangene Sendungen nur anzeigen, wenn tatsächlich nachweisbar.
- [ ] Prüfen, ob eine bewusst aktivierte serverseitige Beobachterverbindung den gruppenweiten Item-Feed robuster macht. Keine fremden Slots ohne Autorisierung verwenden.
- [ ] Authentifizierungsgeheimnisse nur solange nötig im Arbeitsspeicher behalten; nach Beendigung verwerfen. Nach Prozessneustart keine nahtlose Verbindung ohne erforderliche Daten behaupten.

### A3 – WebHost-API und Statusanzeige

- [ ] `hub/live_api.py` / `hub/live_store.py` auf Timeout, HTTP 429/5xx, unvollständige Antworten, Raum-/Trackerwechsel, Collector-Neustart und mehrere parallele Browser überprüfen.
- [ ] Vorhandene gemeinsame Caches und upstream TTLs (dynamisch ca. 60 s, statisch ca. 300 s) erhalten; kontrollierte Retries/Backoff und `Retry-After` berücksichtigen, soweit vorhanden.
- [ ] Letzten erfolgreichen Fortschrittsstand weiter anzeigen, aber als **veraltet** markieren; WebHost-Fehler dürfen die WebSocket-Konsole nicht als „offline“ markieren.
- [ ] In der Konsole den Unterschied zwischen `connected`, `reconnecting`, `temporarily unavailable`, `action required` und absichtlich `disconnected` nachvollziehbar darstellen.
- [ ] Letzten erfolgreichen Kontakt, Fehlerursache und nächsten Versuch in einer kompakten Diagnoseansicht anzeigen.
- [ ] Lokale Spielclient-Verbindung **unbekannt** nennen, solange sie nicht verlässlich gemessen wird. Konsole ≠ Spielclient.
- [ ] Browser-Polling auf überlappende Requests, Tab-Wechsel, Sessionablauf und Verlust von nicht gesendeten Chatentwürfen testen.

### A4 – Experimentellen Universal-Logik-Tracker aus dem Produkt nehmen

- [ ] Universal-Logik-Tracker / „Erreichbare Checks“ / Go-Mode aus produktiver Navigation, Rundenzentrale und Spielstart entfernen.
- [ ] Automatische Universal-Tracker-Berechnungen, zugehörige Worker und unnötige Logik-Endpunkte deaktivieren; alte URLs verständlich umleiten oder mit Hinweis beantworten.
- [ ] Historischen Code über Git verfügbar lassen; keine produktiven Benutzer-, Seed- oder Eventdaten unnötig löschen.
- [ ] **Nicht entfernen:** offizielle WebHost-Tracker-API, Check-/Fortschrittszähler, Live-Dashboard, Itemprotokoll, Chat, `/received`, `/missing`, `/hint`, Seed-Statistiken und Standard-Check-Vorschau.
- [ ] Tests und Dokumentation an die neue Produktgrenze anpassen; nicht mehr vorhandene Trackerfunktionen nicht weiter in README/Navigation anpreisen.

### A5 – Technische Abnahme

- [ ] Mit isoliertem Archipelago-Testserver testen: kurze und längere Abbrüche, simulierte 30-Minuten-Hintergrundzeit, Ping-Timeout, Reconnect, wiederholte Events, falsches Passwort, falscher Slot, Logout, Raumwechsel, Re-Login.
- [ ] Sicherstellen, dass Chat- und Serverbefehle nicht doppelt gesendet werden.
- [ ] API-Tests für HTTP 429, Timeout, 5xx, stale cache, mehrere offene Browser und Reset/Trackerwechsel.
- [ ] Gesamte Python- und Playwright-Suite ausführen; realen Mehrspieler-Langzeittest **separat** kennzeichnen.
- [ ] `CONNECTION_RELIABILITY.md` mit Zustandsmodell, Grenzen, Backoff, Fehlerdiagnose und manueller Fehlerbehebung ergänzen.

**Definition of Done A:** Während eines Spieleabends bleibt eine aktivierte Textverbindung auch ohne sichtbaren Browser bestehen; vorübergehende Verbindungsabbrüche werden automatisch behoben, irreparable Fehler korrekt erklärt, vergangene Nachrichten nicht dupliziert oder erfunden. Der experimentelle Logik-Tracker ist aus der produktiven Oberfläche entfernt.

## Arbeitspaket B – UX-Redesign, DE/EN, Light/Dark

**Priorität: nach A. Eigenständiger Feature-Branch und PR auf dem stabilisierten Stand.**

### B1 – Laufende Runde neu priorisieren

- [ ] Die **Live-Konsole** als Herzstück laufender Runden behalten: Finder → Empfänger, Item, Check, Chat und Befehle direkt sichtbar.
- [ ] Konsole auf Desktop im Hauptbereich priorisieren; persönliches Spiel, Slot, Verbindung, Downloads und Fortschritt kompakt daneben. Auf Mobilgeräten Konsole zuerst.
- [ ] Vorbereitung, laufende Runde und Abschluss visuell und funktional unterscheiden; in der Vorbereitung Spielauswahl/Bereitschaft und beim Abschluss Ergebnisse priorisieren.
- [ ] Gleichartige große Karten, redundante Host-/Portanzeigen und unnötige Scrollstrecken reduzieren; Features **nicht** in zusätzliche verschachtelte Tabs verstecken.
- [ ] Die Archipelago-Fachbegriffe **beibehalten**; die Gruppe kennt Seed, Slot, Check, APWorld und Go-Mode.

### B2 – Konsole als soziales Erlebnis

- [ ] Schnellfilter: Alle, Für mich, Von mir, Andere Spieler, Chat und System. Bestehende Suche/Protokollhistorie erhalten.
- [ ] Persönlich empfangene Items visuell hervorheben; konsistente Spielerfarben in Konsole, Spielerkarten und Charts nutzen.
- [ ] Vollständigen Finder-/Empfänger-/Item-/Location-Kontext anzeigen, wenn vom Server geliefert; keine erfundenen Namen/Zeiten.
- [ ] Status aus Arbeitspaket A (verbunden, Reconnect, Unterbrechung, letzter Kontakt) unaufdringlich im Konsolenkopf anzeigen.
- [ ] Bestehende private Nachrichten, Rollen, Race- und Spoilerregeln unangetastet lassen.

### B3 – Deutsch / Englisch

- [ ] Zentralisierte Übersetzungsressourcen und einheitliche Übersetzungs-API für **Jinja und JavaScript** implementieren.
- [ ] Beide Sprachen vollständig abdecken: Navigation, Formulare, Hilfen, Fehlermeldungen, Status, Admin, Konsolen-UI und kuratierte Installationsanleitungen.
- [ ] Sprache direkt umschaltbar; Einstellung im Profil speichern, Browser-Sprache beim ersten Besuch optional nutzen; dokumentierter Fallback.
- [ ] Zeit-, Datums- und Zahlenformate lokalisieren. Spiel-, Slot-, Item- und Location-Namen, YAML-Schlüssel sowie originale Archipelago-Servermeldungen und -Befehle **nicht übersetzen**.
- [ ] Tests für fehlende Übersetzungen und dynamisch erzeugte Fehlermeldungen ergänzen.

### B4 – Light / Dark / System

- [ ] Beide Themes vollständig über zentrale Design-Tokens umsetzen, inklusive Konsole, Diagrammen, Tabellen, Formularen und Statusfarben; nicht nur CSS-Farben invertieren.
- [ ] Wahl `light` / `dark` / `system` anbieten, im Profil speichern, ohne Seitenreload wechseln und vor dem sichtbaren Rendern anwenden (kein Theme-Flash).
- [ ] Lesbare Kontraste, Tastaturfokus, responsive Layouts und `prefers-reduced-motion` prüfen.
- [ ] Desktop/Tablet/Mobil bei 390, 768, 1440 und 2560 px mit DE/EN und beiden Themes visuell testen.

### B5 – Abnahme

- [ ] Von einer neuen Lobby bis zum Spielstart und gemeinsamen Item-Austausch den tatsächlichen User-Flow prüfen.
- [ ] Automatisierte Tests für Sprache, Theme-Persistenz, Konsolenfilter, Spielerkarten, Rechte, Setup-/Download-Aktionen und Verbindungsstatus.
- [ ] `DESIGN_SYSTEM.md`, Übersetzungshinweise und README aktualisieren.

**Definition of Done B:** Eine laufende Runde öffnet direkt die große, gut lesbare Konsole; ergänzende Aufgaben bleiben schnell erreichbar. Jede wesentliche Seite funktioniert in DE und EN sowie Light und Dark einschließlich dynamischer Meldungen.

## Später / optional – nicht in die beiden Hauptaufträge mischen

- [ ] Opt-in-Benachrichtigungen für Items an den eigenen Slot (keine ungefragten Sounds oder Benachrichtigungen).
- [ ] Optionale Spieleravatare und stabile, gut unterscheidbare Spielerfarben.
- [ ] Persönliche Einrichtungs-Checkliste pro Spiel (manuell bestätigte Schritte klar von automatisch geprüften trennen).
- [ ] Präsentations-/Stream-Ansicht mit Item-Feed und Gruppenfortschritt.
- [ ] Reale Ende-zu-Ende-Tests mit ausgewählten Spielclients und einem längeren Spieleabend; Ergebnisse und bekannte Versionskombinationen dokumentieren.

## Nicht Teil des aktuellen Umfangs

- Kein neuer Universal-Tracker oder versprochene exakte Erreichbarkeitsberechnung.
- Keine automatische lokale Mod-/ROM-Installation.
- Keine unbestätigten Online- oder Zustellungsnachweise und keine erfundenen Eventzeiten.
- Keine direkte Umgestaltung der komplexen Seed-Generierung im Rahmen des UI-Redesigns.
- Kein ungeprüfter Merge der voneinander abhängigen offenen PRs.

**Arbeitsregel:** Für A und B jeweils einen eigenen PR mit nachvollziehbaren Tests und einer klaren Beschreibung, was *wirklich* mit echten Spielclients geprüft wurde.
