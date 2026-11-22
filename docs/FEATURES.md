# Funktionen und Grenzen

## Konten und Bibliothek

Registrierung mit frei gewähltem Benutzernamen und nicht leerem Passwort, ohne Einladungscode oder Mindestlänge. Passwort-Hashes, widerrufbare Sitzungen, CSRF und Rate-Limits schützen die individuelle Identität. Das erste Konto einer leeren Installation wird Admin; bestehende Adminrechte bleiben bei Migrationen erhalten.

Die gemeinsame Bibliothek bietet Suche/Filter, Versionen, Metadaten, Einrichtungsanleitungen und Presets. Admins und als vertrauenswürdig markierte Benutzer aktivieren APWorlds direkt. Andere Benutzer reichen archivierte Uploads zur Freigabe ein. Admins vergeben und entziehen Vertrauen in der Benutzerverwaltung. Neue Konten starten ohne diese Berechtigung. Vorversionen bleiben archiviert. Benutzerdefinierter APWorld-Code läuft mit Hostrechten. Import-/Versionsfehler werden angezeigt.

„Spiel öffnen“ führt zur Spielübersicht. Dort stehen Titel, Beschreibung und Genres vor Checks, Einrichtung und Vorlagen. Berechtigte Spieler bearbeiten Beschreibung und Genres einzeln über den jeweiligen Stift. Die gemeinsame Installationsanleitung besitzt ihren eigenen Stift. Noch nicht eingelesene Spiele zeigen dieselbe Übersicht mit einem Hinweis auf die fehlenden Checks und Einstellungen. Alte Einrichtungs- und Bearbeitungslinks bleiben gültig.

Spielanleitungen können alle angemeldeten Mitglieder gemeinsam bearbeiten, auch für noch nicht geladene Spiele. Bei der Gruppenanleitung stehen der letzte Bearbeiter und das Änderungsdatum. Der Namensnachweis bleibt beim Löschen eines Kontos erhalten; bestehende Anleitungstexte werden bei der additiven Migration unverändert übernommen.

## Vorbereitung und Generierung

Spieler treten einer offenen Lobby zunächst ohne Spiel bei. Danach Spiel und Preset wählen, Einstellungen prüfen/ändern und **Auswahl übernehmen**. Der Host kann erst generieren, wenn alle Teilnehmer gültige Einstellungen bestätigt haben und bereit sind. Änderungen heben die betroffene Bereitschaft auf.

YAML-Reihenfolge: APWorld-Standard → gewählte Vorlage → persönliche Standards → Lobbywerte. Original-Uploads sind unveränderlich. Gewichtete/komplexe Werte und Schema-Prüfung bleiben erhalten. Vorschau und tatsächlich generierte Dateien verwenden denselben Snapshot. [YAML-Details](reference/YAML.md).

Der Hub generiert und archiviert Multiworld-ZIPs und persönliche Dateien. Hochladen/Hosting bei archipelago.gg geschieht manuell; Adresse/Port oder Raumlink werden im Hub hinterlegt. ROMs, Mods und lokale Spielclients müssen die Spieler selbst einrichten. Ein fehlendes benötigtes ROM kann die Generierung verhindern.

## Laufende Runde

Die Live-Konsole steht im Mittelpunkt. Ein automatisch verwalteter Tracker je Runde speichert öffentliche Item-Sendungen, Chats und eindeutig öffentliche Serverereignisse für alle berechtigten Besucher. Beim Öffnen erscheinen gespeicherter Verlauf und neue Meldungen ohne Slot-Auswahl oder persönliche AP-Anmeldung. Tatsächliche Slotnamen sind farbig hervorgehoben und mit den Website-Konten verknüpft. Persönliche Befehle wie `/hint`, `/received` und `/missing` öffnen bei Bedarf eine getrennte, autorisierte Verbindung für den eigenen eingefrorenen Seed-Slot. Antworten bleiben privat. Befehle werden nach Unterbrechungen nicht automatisch wiederholt.

Die Rundenzentrale öffnet „Live“ ab dem erfolgreichen Seed-Build. „Spieler & Items“ zeigt zuerst den Check- und Zielstand des ausgewählten Slots und sortiert bestätigte Funde mit offenem Empfang nach oben. Nach Spoilerfreigabe erscheinen die zuständigen Spielerwelten und unter „Für andere“ die offenen Progression-Items für Mitspieler in dieser Welt. „Hilft jetzt“ nutzt für eigene Slots bereits berechnete, zum gemeldeten Inventar passende Einzeleffekte. Mehrere Exemplare bleiben einzeln nachvollziehbar. Ältere Fortschrittsstände sind gekennzeichnet. „Dateien & Setup“ bündelt eigenes Spiel, Patchdatei, Serveradresse, gemeinsame Dateien und Spielversionen. „Verwaltung“ (für Nicht-Hosts „Verlauf“) enthält Raumverbindung, Lobby-Verwaltung, Seed-Verlauf und neue Runden. Statistiken und Seed-Analyse sind direkt im Rundenkopf verlinkt.

Die Itemsuche neben der Konsole durchsucht nach bewusster Spoilerfreigabe alle Welten des Seeds. Sie zeigt bis zu fünf Treffer pro Seite mit Empfänger, Fundort, Welt und Fundstatus. Eine passende öffentliche Item-Sendung bestätigt den Fund. Die Bestätigung des Empfangs stammt aus der Empfangsliste. Die erweiterte Suche zeigt die verfügbaren Zeitstempel und Filter.

Der WebHost-Tracker liefert Fortschritt, Checks und Empfangslisten. Verifizierte Zielabschlüsse erscheinen einmal im gemeinsamen Liveprotokoll, auch wenn Tracker und Konsole dasselbe Ziel melden. Beim Öffnen einer laufenden Runde prüft der Hub den verknüpften offiziellen Raum im Hintergrund. Bei einer bestätigten Pause kann er den Raum aufwecken und im automatischen Portmodus die aktualisierte Adresse übernehmen.

Der gemeinsame Leser läuft auch ohne offene Browser oder angemeldeten Host weiter und wird über SQLite-Leases gegen doppelte Leser abgesichert. Archipelago verlangt für Live-Ereignisse eine Anmeldung mit gültigem Seed-Slot und führt den Leser auch mit `Tracker` unter diesem Slot. Bei der ersten Einrichtung bevorzugt der Hub einen vorhandenen Slot des Hosts und behält eine gültige Zuordnung für denselben Raum bei. Die Hub-Konsole erkennt die Verbindungsereignisse des Lesers am Tag `ArchipeMANU-Reader`. Sie zeigt den Status über die Verbindungsdiagnose und protokolliert eine zusammenhängende Aufzeichnungslücke bis zur stabilen Wiederverbindung. Echte Spielerbeitritte am selben Slot bleiben sichtbar.

Archipelagos eigene Clients und der WebHost-Tracker können die Tracker-Verbindung unter dem Slot weiterhin anzeigen. Der Server setzt beim Anmelden auch für Tracker den Verbindungsstatus des Slots. [MultiServer 0.6.8](https://github.com/ArchipelagoMW/Archipelago/blob/0.6.8/MultiServer.py#L956-L1007)

Ein geschütztes Raumpasswort hinterlegt nur der Host einmal für den Hub. Es bleibt ausschließlich im Speicher und muss nach einem Hub-Neustart erneut eingegeben werden. Alte Aufzeichnungs-Endpunkte bleiben kompatibel. Nicht eindeutig öffentliche Meldungen und alte persönliche Nachrichten werden nicht nachträglich veröffentlicht. [API und Ereignisse](reference/API.md).

## Analyse und Progression

Seed-Statistiken zeigen tatsächlich gespeicherte Spieler, Spiele, Itemverteilung und Checkzahlen. Spoiler bleiben bewusst verborgen; Race-Sperren gelten serverseitig.

Die globale Itemsuche durchsucht verifizierte Seed-Platzierungen unabhängig von dynamischer Logik. Check und Empfang sind getrennte, zeitlich belegte Zustände. Startinventar, Events und Gruppenslots sind keine normalen Fundorte.

**Was bringt mich weiter?** simuliert je fehlender Progression-Itemart genau ein zusätzliches Exemplar. Sortierung: zusätzliche Checks absteigend, neue Regionen absteigend, Itemname alphabetisch. Region-only-Ergebnisse sind hilfreich. Zehn hilfreiche Karten erscheinen zuerst; weitere über **Mehr anzeigen**. Konkrete Fundorte/Spieler/Welten und belegte Zustände sind sichtbar, zusätzliche Kopien und Checklisten aufklappbar. Unmittelbar wirkungslose Items stehen separat eingeklappt: später oder gemeinsam können sie trotzdem wichtig sein.

Es gibt keine Paaranalyse oder Synergiekarten im normalen Ablauf. Alle fehlenden Typen werden bis zum Zeitlimit untersucht, ohne feste 40er-Grenze. Die Oberfläche zeigt geprüfte und gesamte Typenzahl. Die separate Spielziel-/Notwendigkeitsanalyse startet nur ausdrücklich. Mehr Checks bedeuten nicht zwingend ein notwendiges Zielitem.

Neue Seeds mit passender Rekonstruktion verwenden die originalen APWorld-Regeln. Fehlende Daten, veränderte APWorlds/YAMLs, unvollständiges Inventar oder Item-Link-Gruppen führen zur Ablehnung statt zu erfundenen Ergebnissen. Die theoretische Seed-Reihenfolge ist kein Live-Status. Details und Grenzen: [Progression](reference/PROGRESSION.md).

## Oberfläche

Deutsch/Englisch, Light/Dark/System, responsive Karten und Navigation, private Chatentwürfe, persönliche Downloads, Slotauswahl und gemeinsam sichtbare Lobbys. Eigene Namen, YAML-Werte und originale AP-Nachrichten werden nicht automatisch übersetzt. Die historische Universal-Tracker-Ansicht bleibt deaktiviert (HTTP 410).
