# Verlässliche YAML-Konfiguration

Die vier Ebenen werden in dieser Reihenfolge zusammengeführt; spätere Werte gewinnen:

1. Standardwerte der installierten APWorld.
2. Ausgewählte APWorld-/Gruppen-/Upload-Vorlage.
3. Persönliche Standardeinstellungen des Spielers.
4. Individuelle Lobbyänderungen.

Die höchste Priorität liegt immer bei der aktuellen Lobby. `hub/yamlgen.py` besitzt die gemeinsame Komposition, Parser und Schema-Validierung; `hub/services/selection.py` löst die konkrete unveränderliche Vorlage auf und erzeugt die Spieler-YAML. Keine zweite Komposition in Templates oder JavaScript.

Hochgeladene YAMLs erscheinen als auswählbare Presets. Originaltext, SHA-256 und Optionsanforderungen bleiben erhalten. Originalvorlagen sind unveränderlich; zum Ändern eine eigene Vorlage/Kopie anlegen. Hash und reparste Werte müssen übereinstimmen. Eine fehlende/inkompatible gewählte Vorlage wird nicht heimlich durch Standards ersetzt.

Optionsklassen liefern Checkboxen, Dropdowns und Zahlenfelder, soweit möglich. Gewichtete Werte bleiben Gewichtungen, verschachtelte/komplexe Werte sind über YAML-Eingaben bearbeitbar. Nullen, boolesche Werte und optionale Werte dürfen bei der Schichtung nicht durch Wahrheitsprüfungen verloren gehen. Persönliche UI-Präferenzen gelangen nicht in Spieloptionen.

Der Server validiert Werte mit den tatsächlichen APWorld-Optionsklassen im passenden AP-Prozess; Feldfehler bleiben verständlich angezeigt. Fehlende/inaktive/falsche APWorld-Versionen verhindern Speichern/Bereitschaft/Generierung entsprechend dem Datenvertrag.

Die Lobby speichert erst nach **Auswahl übernehmen**. Vorschau, gespeicherte Auswahl und Dateien des unveränderlichen Build-Snapshots müssen denselben Inhalt haben. Slot-, Template-, Profil-, YAML- und Versionsänderungen setzen Bereitschaft zurück oder machen den Fingerprint ungültig. Der Generator verwendet die archivierten Snapshot-YAMLs, keine später geänderten Profilwerte.

Die Unit- und Browsertests kombinieren die Ebenen, gewichten/verschachteln Werte und vergleichen Vorschau mit wirklich an den Generator übergebenen Dateien und ZIP-Inhalt. [Testanleitung](../DEVELOPMENT.md). Frühere Migrationsdetails bleiben im [historischen YAML-Bericht](../archive/YAML_CONFIGURATION.md).
