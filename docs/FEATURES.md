# Funktionen und Grenzen

## Konten und Bibliothek

Registrierung mit frei gewähltem Benutzernamen und nicht leerem Passwort, ohne Einladungscode oder Mindestlänge. Passwort-Hashes, widerrufbare Sitzungen, CSRF und Rate-Limits schützen die individuelle Identität. Das erste Konto einer leeren Installation wird Admin; bestehende Adminrechte bleiben bei Migrationen erhalten.

Die gemeinsame Bibliothek bietet Suche/Filter, Versionen, Metadaten, Einrichtungsanleitungen und Presets. Authentifizierte Spieler dürfen APWorlds hochladen; vertrauenswürdige Uploads werden automatisch aktiviert und eingelesen. Vorversionen bleiben archiviert. Benutzerdefinierter APWorld-Code läuft mit Hostrechten, ohne Sandbox. Import-/Versionsfehler werden angezeigt.

„Spiel öffnen“ führt immer zur Spielübersicht: Titel, Beschreibung, Genres und Tags stehen vor Checks, Einrichtung und Vorlagen. Berechtigte Spieler ändern einzelne Katalogfelder direkt über den Stift daneben; dabei bleiben die anderen Felder erhalten. Die gemeinsame Installationsanleitung besitzt ihren eigenen Stift. Noch nicht eingelesene Spiele zeigen dieselbe Übersicht mit einem Hinweis auf die fehlenden Checks und Einstellungen. Alte Einrichtungs- und Bearbeitungslinks bleiben gültig.

Spielanleitungen können alle angemeldeten Mitglieder gemeinsam bearbeiten, auch für noch nicht geladene Spiele. Bei der Gruppenanleitung stehen der letzte Bearbeiter und das Änderungsdatum. Der Namensnachweis bleibt beim Löschen eines Kontos erhalten; bestehende Anleitungstexte werden bei der additiven Migration unverändert übernommen.

## Vorbereitung und Generierung

Spieler treten einer offenen Lobby zunächst ohne Spiel bei. Danach Spiel und Preset wählen, Einstellungen prüfen/ändern und **Auswahl übernehmen**. Der Host kann erst generieren, wenn alle Teilnehmer gültige Einstellungen bestätigt haben und bereit sind. Änderungen heben die betroffene Bereitschaft auf.

YAML-Reihenfolge: APWorld-Standard → gewählte Vorlage → persönliche Standards → Lobbywerte. Original-Uploads sind unveränderlich. Gewichtete/komplexe Werte und Schema-Prüfung bleiben erhalten. Vorschau und tatsächlich generierte Dateien verwenden denselben Snapshot. [YAML-Details](reference/YAML.md).

Der Hub generiert und archiviert Multiworld-ZIPs und persönliche Dateien. Hochladen/Hosting bei archipelago.gg geschieht manuell; Adresse/Port oder Raumlink werden im Hub hinterlegt. ROMs, Mods und lokale Spielclients müssen die Spieler selbst einrichten. Ein fehlendes benötigtes ROM kann die Generierung verhindern.

## Laufende Runde

Die Live-Konsole steht im Mittelpunkt: Item-Sendungen mit Finder, Empfänger und konkretem Check, Chat, Serverantworten und begrenzte Befehle wie `/hint`, `/received`, `/missing`. TextOnly-Verbindungen laufen unabhängig vom offenen Tab und verbinden sich nach vorübergehenden Ausfällen neu. Befehle werden nicht automatisch wiederholt.

Der WebHost-Tracker liefert getrennt Fortschritt, Checks und Empfangslisten. Diagnose unterscheidet Browser, Hub, WebHost-API, Textverbindung und unbekannten lokalen Spielclient. Eine funktionierende Textkonsole beweist keine Spielverbindung. Portänderungen desselben verifizierten Raums werden übernommen.

Optional kann der Host mit eigenem Slot ausdrücklich eine Aufzeichnung freigeben. Sie speichert belegte Itemereignisse auch ohne Browser/Anmeldung weiter, bis zum Widerruf, Raumwechsel oder Rundenabschluss. Passwörter bleiben ausschließlich im Speicher; nach Hub-Neustart müssen geschützte Räume erneut authentifiziert werden. Die Ereignishistorie wird nicht automatisch nach 10.000 Zeilen abgeschnitten. Es gibt kein abrufbares vollständiges vergangenes Serverlog. [API und Ereignisse](reference/API.md).

## Analyse und Progression

Seed-Statistiken zeigen tatsächlich gespeicherte Spieler, Spiele, Itemverteilung und Checkzahlen. Spoiler bleiben bewusst verborgen; Race-Sperren gelten serverseitig.

Die globale Itemsuche durchsucht verifizierte Seed-Platzierungen unabhängig von dynamischer Logik. Check und Empfang sind getrennte, zeitlich belegte Zustände. Startinventar, Events und Gruppenslots sind keine normalen Fundorte.

**Was bringt mich weiter?** simuliert je fehlender Progression-Itemart genau ein zusätzliches Exemplar. Sortierung: zusätzliche Checks absteigend, neue Regionen absteigend, Itemname alphabetisch. Region-only-Ergebnisse sind hilfreich. Zehn hilfreiche Karten erscheinen zuerst; weitere über **Mehr anzeigen**. Konkrete Fundorte/Spieler/Welten und belegte Zustände sind sichtbar, zusätzliche Kopien und Checklisten aufklappbar. Unmittelbar wirkungslose Items stehen separat eingeklappt: später oder gemeinsam können sie trotzdem wichtig sein.

Es gibt keine Paaranalyse oder Synergiekarten im normalen Ablauf. Alle fehlenden Typen werden bis zum Zeitlimit untersucht, ohne feste 40er-Grenze. Die Oberfläche zeigt geprüfte und gesamte Typenzahl. Die separate Spielziel-/Notwendigkeitsanalyse startet nur ausdrücklich. Mehr Checks bedeuten nicht zwingend ein notwendiges Zielitem.

Neue Seeds mit passender Rekonstruktion verwenden die originalen APWorld-Regeln. Fehlende Daten, veränderte APWorlds/YAMLs, unvollständiges Inventar oder Item-Link-Gruppen führen zur Ablehnung statt zu erfundenen Ergebnissen. Die theoretische Seed-Reihenfolge ist kein Live-Status. Details und Grenzen: [Progression](reference/PROGRESSION.md).

## Oberfläche

Deutsch/Englisch, Light/Dark/System, responsive Karten und Navigation, private Chatentwürfe, persönliche Downloads, Slotauswahl und gemeinsam sichtbare Lobbys. Eigene Namen, YAML-Werte und originale AP-Nachrichten werden nicht automatisch übersetzt. Die historische Universal-Tracker-Ansicht bleibt deaktiviert (HTTP 410).
