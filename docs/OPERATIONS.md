# Installation und Betrieb

## Start und Konfiguration

Windows mit Git, PowerShell und Python 3.11–3.13:

```powershell
.\setup.ps1
.\start.ps1
# Nur auf diesem Rechner erreichbar:
.\start.ps1 -LocalOnly
# Vorhandene vertrauenswürdige APWorlds importieren:
.\setup.ps1 -ImportFrom "C:\ProgramData\Archipelago\custom_worlds"
```

Setup installiert standardmäßig Archipelago 0.6.8 unter `%USERPROFILE%\.ap-yaml-hub`; `-ApVersion` bzw. `-ApHome` ändern dies. Das Setup kann wiederholt werden, verändert dabei aber die AP-Laufzeit; laufende Seeds/Generierungen vorher berücksichtigen. Start bindet standardmäßig `0.0.0.0:8080`; `-Public` bleibt kompatibel, `-Port` wählt einen anderen Port. Linux: vorhandene `setup.sh`/`start.sh` verwenden.

| Variable | Wirkung |
| --- | --- |
| `HUB_DATA` | Separater Datenordner; Standard `data/` im Checkout |
| `AP_HOME`, `AP_SOURCE`, `AP_PYTHON` | AP-Installation, Quellen und geeignete Python-Umgebung |
| `HUB_COOKIE_SECURE=1` | Secure-Cookie für HTTPS; ein vorgeschalteter Server muss TLS bereitstellen |
| `HUB_GENERATE_TIMEOUT` | Generatorlimit in Sekunden, Standard 900 |
| `HUB_EXTRACT_TIMEOUT` | Extraktionslimit in Sekunden, Standard 600 |
| `HUB_TRUSTED_APWORLDS=0` | Benutzerdefinierten APWorld-Code sperren; beim Windows-Start `-NoCustomWorlds` benutzen |

Der private Nutzerkreis darf eigene APWorlds automatisch aktivieren. Diese Archive enthalten ausführbaren Python-Code mit Hostrechten. Es gibt keine Sandbox. Das Netzwerk-Setup selbst liefert kein HTTPS. Außerhalb localhost Zugangsdaten über HTTPS transportieren. `HUB_PASSWORD`/`HUB_INVITE_CODE` werden für die Anmeldung nicht mehr verwendet.

## Konten und Wiederherstellung

Neue Benutzer wählen Benutzernamen und eigenes Passwort (1–1024 Zeichen). Nur das erste Konto einer vollständig leeren Benutzerliste erhält Adminrechte. Bei Updates bleiben IDs, Profile, Vorlagen, Mitgliedschaften und bestehende Administratoren erhalten. Wiederholbare additive Migrationen laufen beim Start; vorhandene Altkonten werden nicht durch offene Registrierung übernommen.

Ein bestehendes Konto ohne Passwort lokal einrichten:

```powershell
& "$env:USERPROFILE\.ap-yaml-hub\venv\Scripts\python.exe" -m hub.auth setup-account Manu
```

Den einmaligen persönlichen Code auf `/account/setup` verwenden und eigenes Passwort vergeben. Codes sind 24 Stunden gültig. Der Admin kann weitere Kontocodes ausgeben; für Passwortverlust lokal `python -m hub.auth reset-account BENUTZER`. Vorhandene Benutzer dürfen nicht über `bootstrap-admin` ersetzt werden; dieser ist nur bei leerer Benutzerliste erlaubt.

Passwörter liegen als gesalzene scrypt-Hashes vor. Sitzungen und Einrichtungscodes sind serverseitig nur als Hash gespeichert. Login erneuert Sitzung/CSRF, Logout widerruft die Sitzung; Passwortreset widerruft alle Sitzungen des Kontos. Rollen werden erneut aus SQLite gelesen. Cookies: HttpOnly/SameSite=Lax, Secure konfigurierbar, Sitzungsdauer acht Stunden. Schreibanfragen benötigen CSRF. Login-Limits: zehn Versuche pro Name und 30 pro IP in 15 Minuten; Registrierung/Codeeingabe zehn pro IP. HTTP 429 enthält Retry-After. Ein unbekanntes Konto kann nicht per Registrierung übernommen werden.

## Daten sichern und aktualisieren

`data/` enthält SQLite, den geheimen Cookie-Schlüssel, APWorld-Archive und alle Seed-/YAML-/Ausgabedateien. Nie löschen, durch Testdaten ersetzen oder selektiv auf einen veralteten Stand zurücksetzen.

1. Laufende Generatoren abschließen lassen und Hub geordnet stoppen.
2. Den **vollständigen** Datenordner in einen neuen Backupordner kopieren; bei laufender SQLite nur die SQLite-Backup-API statt einer einzelnen DB-Dateikopie verwenden.
3. `main` aktualisieren, Abhängigkeiten bei Bedarf installieren, Hub starten.
4. Anmeldung, Runde, vorhandene Downloads und APWorld-Versionen prüfen. Vor einer Wiederherstellung den aktuellen Stand zusätzlich sichern und Originale/Archive konsistent zusammen restaurieren.

Dieses Refactoring benötigt keine zusätzliche Migration und verändert keine bestehenden Seed-Einstellungen. Code im Arbeitsverzeichnis eines laufenden Servers nur bei kontrolliertem Update ersetzen: alte Python-Prozesse laden Templates und Module sonst möglicherweise aus verschiedenen Ständen. Das Mergen eines PR ist noch kein Neustart eines laufenden Hub-Prozesses.

## Fehlerbehebung

- **AP nicht eingerichtet:** Setup/`AP_SOURCE`/`AP_PYTHON` prüfen; Installationsfehler im Serverlog lesen.
- **APWorld nicht geladen:** Versions-/Importmeldung in der Bibliothek bzw. Administration ansehen. Aktiviert ist nicht gleich erfolgreich importiert. Abhängigkeiten/Versionen müssen zur AP-Laufzeit passen.
- **ROM fehlt:** benötigte eigene Originaldatei gemäß Spielanleitung in der AP-Konfiguration hinterlegen. Der Hub lädt keine ROMs herunter.
- **Generierung fehlt:** alle beigetretenen Teilnehmer müssen ein gültiges Spiel samt Einstellungen besitzen und bereit sein. Versions-/Vorlagenwechsel erfordern erneute Bestätigung.
- **Textverbindung unterbrochen:** tatsächlichen Raum/Port, WS/WSS und Raumpasswort prüfen; Diagnose trennt WebHost-API und Socket. Nur API-bestätigte Portwechsel desselben Raums werden automatisch übernommen. `/hint` wird vom Server autorisiert und ggf. berechnet.
- **Nach Hub-Neustart:** persönliche Textverbindung erneut starten; bei passwortgeschützter Aufzeichnung Passwort erneut eingeben. Historie bleibt erhalten. Der Hub startet oder stoppt den externen AP-Spielserver nicht.
- **Progression nicht verfügbar:** passende unveränderte APWorld-/AP-Version, Original-YAMLs, Rekonstruktionsnachweis und frisches vollständiges Inventar erforderlich. Alte Seeds und Item-Link-Gruppen liefern keine dynamischen Behauptungen; die verifizierte Itemsuche bleibt nutzbar.

[API/Befehle](reference/API.md), [Progression-Limits](reference/PROGRESSION.md), [Tests](DEVELOPMENT.md).
