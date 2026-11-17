# ArchipeMANU

Privater Archipelago-Multiworld-Hub für dich und deine Freunde: gemeinsame Spielebibliothek, persönliche Konten, YAML-Einstellungen, Lobbys, Seed-Generierung und eine Live-Konsole mit Itemprotokoll und Chat.

## Starten

Benötigt Git, PowerShell und Python 3.11–3.13.

```powershell
.\setup.ps1
.\start.ps1
```

Öffne [localhost:8080](http://127.0.0.1:8080). Das erste registrierte Konto einer neuen Installation wird Admin. Andere Spieler registrieren sich mit eigenem Benutzernamen und Passwort; Einladungscodes sind nicht erforderlich.

Der Start ist im privaten Netzwerk unter `http://<Host-IP>:8080` erreichbar. `-LocalOnly` beschränkt ihn auf deinen Rechner. Für Zugriffe außerhalb localhost HTTPS einrichten; siehe [Betrieb](docs/OPERATIONS.md).

## Zusammen spielen

1. Benötigte Spiele in der Bibliothek hinzufügen.
2. Lobby erstellen oder beitreten, danach Spiel und Einstellungen auswählen und übernehmen.
3. Alle melden sich bereit; der Host generiert den Seed.
4. Die ZIP manuell bei archipelago.gg hosten und Raumlink oder Adresse/Port hinterlegen.
5. Den eigenen Spielclient verbinden. Im Hub begleitet euch die Konsole mit Item-Sendungen und Chat.

**Was bringt mich weiter?** untersucht einzelne fehlende Progression-Itemarten mit den originalen APWorld-Regeln, sortiert nach zusätzlichen Checks, dann Regionen und Itemname. Die konkrete Itemsuche und die ausdrücklich gestartete Spielzielanalyse bleiben getrennt. Spoiler müssen bewusst freigegeben werden; Race-Regeln gelten auch in der API.

Die Website ersetzt keinen Spielclient und prüft keine lokale Spielinstallation. Alte Seeds ohne Rekonstruktionsdaten behalten die verifizierte Itemsuche. Nicht überprüfbare Zahlen werden nicht erfunden.

## Dokumentation

- [Funktionen und Grenzen](docs/FEATURES.md)
- [Architektur und Zuständigkeiten](docs/ARCHITECTURE.md)
- [Entwicklung, Tests und Git-Regeln](docs/DEVELOPMENT.md)
- [Installation, Backups und Fehlerbehebung](docs/OPERATIONS.md)
- [Offene Aufgaben in GitHub Issues](https://github.com/Madness61/ArchipeMANU/issues)

`main` enthält den integrierten Entwicklungsstand. Historische Entwicklungsberichte stehen im [Archiv](docs/archive/README.md). Bestehende Daten im `data/`-Ordner vor Updates vollständig sichern und erhalten.
