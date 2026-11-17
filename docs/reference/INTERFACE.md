# Gemeinsame Oberfläche

Jinja verwendet `_('Deutscher Ausgangstext')`, JavaScript `window.HUB_I18N.t(...)`. Die gepaarten Kataloge `hub/locales/de.json` und `en.json` besitzen stabile IDs; neue IDs anhängen statt umnummerieren. `scripts/ui_catalog.py` erfasst statische Texte, `python -m scripts.ui_checks` prüft nicht übersetzte UI-Literale. Neue Backendmodule werden ebenfalls rekursiv geprüft. Platzhalterwerte einmal ersetzen und sicher als Text ausgeben.

Benutzer-, Spiel-, Slot-, Item- und Checknamen, YAML-Werte, private Beschreibungen und native AP-Meldungen bleiben Daten und werden nicht automatisch übersetzt. Kuratierte Spielanleitungen besitzen englische Fassungen in `games_en.json`.

Sprache und Theme liegen kontobezogen in `users.overrides._interface`; sie ändern weder Spieloptionen noch Bereitschaft. Ohne Konto können Cookies die UI-Wahl speichern. Ein angemeldeter Spieler übernimmt nicht die Kontowahl eines vorherigen Benutzers im selben Browser. Konsolenentwürfe bleiben konto-/rundenbezogen im `sessionStorage`; Raumpasswörter nie.

`hub/static/themes.css` enthält die zentralen Farben für Light/Dark/System. Komponenten verwenden semantische Variablen, `style.css` gemeinsame Abstände/Typografie. `ui.html` liefert Icons, Aktionen, Status, Spiel- und Lobbykarten. Neue Seiten erben `base.html`; die Konsole bleibt die Hauptfläche einer laufenden Runde.

Mobile Navigation mit Escape/Fokus, sichtbarer Tastaturfokus, verständliche Statusbeschriftungen und `prefers-reduced-motion` erhalten. Breite Tabellen scrollen im Panel, nicht die gesamte Seite. Die Browser-Suite prüft DE/EN, Themes, Kontraste, Entwürfe und Seitenbreiten 390/768/1440/2560 px. Eine vollständige Screenreader-Abnahme ist damit nicht ersetzt.

Historische Gestaltungsentscheidungen: [Designbericht](../archive/DESIGN_SYSTEM.md). Verbindliche Architektur und Prüfungen: [Entwicklung](../DEVELOPMENT.md).
