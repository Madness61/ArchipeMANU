# YAML-Konfiguration: Analyse und Verhalten

Implementiert auf `feature/yaml-configuration-reliability`. Die bereits
vorhandenen Änderungen für persönliche Benutzerkonten bleiben als Grundlage
erhalten. Es erfolgt kein automatischer Push und keine produktive Migration.

## Gefundene Fehler

- In `session_entries`, Sloteditor und Bereitschaftsprüfung wurde das Profil
  nach den Lobby-Werten angewendet. Dadurch konnte es diese überschreiben.
- Zwischenberechnungen und das Formular entfernten Werte, die dem AP-Standard
  entsprachen. Damit ging beispielsweise ein bewusstes `death_link: false`
  gegen ein Profil mit DeathLink verloren.
- YAML-Importe reduzierten Gewichtungen mit nur einem positiven Gewicht zu
  Einzelwerten und ignorierten unbekannte Optionen. Explizite Standardwerte
  wurden entfernt. Das Ergebnis war nicht mehr die ursprüngliche Vorlage.
- Session-Slots lösten veränderbare Vorlagen bei jedem Zugriff neu auf.
- Die Vorschau hatte einen anderen Beschreibungstext und verwendete nicht den
  für die gesamte Lobby berechneten, eindeutigen Slotnamen.
- Dateien wurden unter Windows im Textmodus geschrieben; die gespeicherten
  SHA-256-Werte basierten dagegen auf UTF-8 mit unveränderten Zeilenenden.
- Ein aktives Archiv war nicht mit dem tatsächlich extrahierten Schema verknüpft.
- Prüfung und Sperren der Lobby waren getrennte Schreiboperationen. Ein später
  eintreffendes Formular konnte trotz inzwischen gestarteter Generierung noch
  Einstellungen verändern.

## Verbindliche Priorität

1. Tatsächliche Standardwerte aus dem extrahierten APWorld-Schema.
2. Gewählte Vorlage einschließlich expliziter Standardwerte und Gewichte.
3. Persönliche Standardwerte aus dem Spielerprofil, soweit für das Spiel anwendbar.
4. Individuelle Änderungen des Lobby-Slots.

`yamlgen.effective_values` ist die gemeinsame Berechnung. Ganze Optionswerte
werden ersetzt; verschachtelte Dictionaries werden nicht unbemerkt miteinander
vermischt. Ein Gewichtungs-Dictionary ist ein Optionswert, keine zusätzliche
Konfigurationsebene. Unbekannte Optionsschlüssel bleiben zur Fehlerprüfung
erhalten und werden nicht aus der Konfiguration gefiltert.

Im Lobbyformular werden Abweichungen von Vorlage plus Profil gespeichert.
Explizite Rücksetzungen auf `false`, `0`, leere Listen oder Dictionaries bleiben
als Lobby-Änderungen erhalten, wenn die darunterliegenden Ebenen anders lauten.
„Für diesen Wert wieder Vorlage/Profil übernehmen“ entfernt den betreffenden
Lobby-Override. Die separate Schaltfläche zum Zurücksetzen aller Lobby-Änderungen
entfernt diese nur auf ausdrückliche Benutzeraktion.

## Vorlagen und Originaldateien

### Auswahl direkt in der Lobby

Beitritt und Lobby-Erstellung legen noch keinen Spielslot an. Unter „Deine
Spielauswahl“ wählt der Spieler Spiel und Vorlage und öffnet mit „YAML erstellen /
bearbeiten“ den Editor innerhalb der Lobby. Vorschau und Download sind ein
Entwurf; erst „Auswahl übernehmen“ speichert Spiel und Einstellungen gemeinsam.
Vorhandene Slots behalten bis dahin ihre Einstellungen und Bereitschaft.

Der Entwurf enthält eine signierte, auf Benutzer und Lobby beschränkte Kopie der
Vorlage. Veränderte Schemas, Profile, Slotnamen oder eine parallel geänderte
Auswahl erfordern ein erneutes Öffnen. Die endgültige Übernahme prüft unter
einer SQLite-Schreibsperre erneut Mitgliedschaft und Lobby-Sperre, aktualisiert
den bestehenden Slot und setzt die Bereitschaft zurück. Hierfür ist keine
Datenmigration erforderlich. Alte `/choose`-Links führen direkt zur Lobby.

### Vorlagen

Über `/import` hochgeladene Dateien werden als auswählbare Presets gespeichert,
einschließlich Originaltext, UTF-8/BOM/Zeilenenden, SHA-256 und Versionsvorgaben.
Gewichte werden nicht reduziert. Imports sind unveränderlich; „Anpassen (Kopie)“
erzeugt eine eigenständige Vorlage. Originaldateien sind herunterladbar.
Mehrere YAML-Dokumente für dasselbe Spiel bleiben getrennt auswählbar.

Auch die bei einem Community-Spiel hochgeladene Original-YAML erscheint als
Preset, sobald ein passendes World-Schema verfügbar ist. Der Originalhash wird
geprüft. Fehlende, veränderte oder inkompatible Originale werden kenntlich
gemacht; ein Ersatz durch AP-Standards erfolgt nicht stillschweigend.

Bei der Auswahl erhält jeder Lobby-Slot eine fixierte Kopie der Vorlagenwerte,
Bezeichnung und Versionsvorgaben. Spätere Bearbeitungen der Vorlage ändern diese
Kopie nicht. Wer die neue Fassung möchte, wählt die Vorlage erneut und muss die
Bereitschaft erneut bestätigen. Klonen übernimmt die fixierte Kopie und setzt
die Bereitschaft zurück.

## Formulare und Prüfung

Choices erscheinen als Dropdown, Toggle als Checkbox, Range als Zahlenfeld und
Schieberegler. Kleine Auswahlmengen können als Checkboxliste erscheinen.
Für gewichtete oder komplexe Werte gibt es zusätzlich eine explizite YAML-Eingabe.
Vorhandene Gewichte und komplexe Werte öffnen die YAML-Darstellung automatisch.

Der Webserver prüft Optionsnamen, Typen, erlaubte Namen, Zahlenbereiche,
Spezialwerte, Versionsvorgaben und Gewichtungen anhand des extrahierten Schemas.
Gewichte müssen nichtnegative ganze Zahlen sein; mindestens eines muss positiv
sein. Auch Listen gleich wahrscheinlicher Alternativen werden unterstützt.
TextChoice darf benutzerdefinierte Texte enthalten. Strukturierte Werte behalten
ihren Typ. Doppelte Schlüssel, rekursive Verweise, NaN/Unendlich und nicht
verlustfrei speicherbare YAML-Typen werden mit Fehlermeldung abgewiesen.

Nicht unterstützte Top-Level-Mechanismen wie `triggers`, `linked_options` oder
Plando-Anforderungen werden explizit abgelehnt, statt einen Teil der Datei zu
ignorieren. Die Originaldatei eines Community-Uploads bleibt dennoch archiviert.
Ungültige Eingaben überschreiben keine gespeicherte Konfiguration.

Vor dem eigentlichen Seed-Build prüft `ap_runner.validate_player_files` die
Dateien zusätzlich über `from_any` und `verify` der tatsächlich geladenen
APWorld-Optionsklassen. Alle positiv gewichteten Alternativen werden geprüft.
Der RNG-Zustand wird dabei wiederhergestellt. Spielabhängige Prüfregeln, die
sich nicht generisch als Formularschema darstellen lassen, können deshalb noch
in dieser Worker-Prüfung einen Build mit Slot- und Optionsnamen ablehnen.

## Vorschau, Bereitschaft und Generierung

Gespeicherte Vorschau, YAML-Download und Generator benutzen denselben Export.
Er enthält die vollständigen Standardwerte, den tatsächlich zugewiesenen
Slotnamen und die Versionsanforderungen. Die World-Version wird über min=max
auf die extrahierte Version beschränkt. Unsafe Dateinamen und reservierte
Windows-Namen werden bei der Slotnamen-Zuweisung bereinigt.

„Vorschau aktualisieren“ berechnet einen noch nicht gespeicherten Formularstand
und kennzeichnet ihn entsprechend. Erst Speichern übernimmt ihn. Vorschau allein
ändert weder Konfiguration noch Bereitschaft. Bei gewichteten Optionen zeigt die
Vorschau die exakten Gewichte, nicht das später zufällig gezogene Ergebnis.

Gespeicherte Lobby-Änderungen, Vorlagen- oder World-Auswahl und Profiländerungen
setzen die Bereitschaft zurück. Der Bereitschaftshash prüft zusätzlich die
aufgelösten Werte, den Slotnamen, die Vorlage, die Anforderungen und das gesamte
Schema. Änderungen an einer World oder ihren Standards machen ihn ungültig.

Beim Seed-Start laufen Preflight, unveränderlicher Build-Snapshot und Lobby-Sperre
in einer SQLite-Schreibtransaktion. Der Hintergrundworker erhält ausschließlich
die dabei erzeugten YAML-Inhalte. Spätere Änderungen an Profilen oder Vorlagen
werden nicht nachgelesen. YAML-Dateien werden als UTF-8-Bytes geschrieben;
ihre SHA-256-Werte stimmen damit auch unter Windows mit dem Snapshot überein.
Verspätete Einstellungsformulare können eine inzwischen gesperrte Lobby nicht
mehr verändern.

## Migration und Grenzen

Die Migration ergänzt nur Spalten für Original-YAMLs, Hashes, Versionsvorgaben
und Vorlagen-Snapshots. Bereits gespeicherte Vorlagenwerte, Profile und
Lobby-Overrides werden nicht gelöscht oder umgeschrieben. Vorhandene Verweise
auf Datenbankvorlagen erhalten eine Kopie ihrer bisherigen Werte. Alte AP-Presets
ohne Kopie werden beim nächsten ausdrücklichen Bereitmelden fixiert.
Bestehende Seed-Dateien und Build-Snapshots werden nicht verändert.

Einmal nach dem Update die Optionen für bereits aktive Custom-Worlds neu einlesen:
Erst die neue Extraktion schreibt den Archivhash in das Schema. Bis dahin wird
eine Generierung mit unbestätigtem oder veraltetem Schema mit klarer Meldung
blockiert. Archivaktivierung und Schemaextraktion bleiben automatische Schritte
des vorhandenen Upload-/Aktivierungsablaufs.

Die Tests verwenden temporäre Datenverzeichnisse und einen Fake-Generator.
Sie vergleichen die Vorschau bytegenau mit den tatsächlich an diesen Generator
übergebenen Dateien. Die Optionsklassen-Prüfung wird ebenfalls mit kontrollierten
Testklassen geprüft; fremde APWorlds wurden für diese Änderung nicht ausgeführt.
Eine echte Generierung mit den verwendeten Custom-Worlds bleibt ein ergänzender
Integrationstest auf dem Host. Der produktive `data`-Ordner wurde nicht migriert
oder für Tests verwendet; der Produktivserver wurde nicht neu gestartet.
