# Persönliche Konten: Analyse und Migrationsplan

Ergänzung vom 10.11.2026: Fehlt eine gültige Anmeldung, führen geschützte
HTML-Seiten zur Anmeldung mit Rückweg zur angeforderten Seite. API-Aufrufe
antworten mit HTTP 401 und JSON (`authentication_required`, `login_url`) statt
einer englischen HTML-Fehlerseite. Rückwege nach POST-Aktionen führen zu einer
lesbaren Rundenseite; Aktionen werden nicht nach der Anmeldung wiederholt.
Die Konsole zeigt einen Hinweis „Erneut anmelden“ und hält ihre automatische
Abfrage an. Unversendeter Chattext wird nicht durch eine automatische Navigation
verworfen. Passwortprüfung, Sitzungsdauer, Rollen, CSRF und Race-Schutz bleiben
unverändert. Ungültige Zugangsdaten zeigen weiterhin das reguläre Loginformular.

Stand: 7. November 2026. Individuelle Konten wurden auf
`feature/individual-user-accounts` eingeführt; die vereinfachte offene
Registrierung liegt auf `feature/simple-registration`.

## Ausgangslage

Die bisherige `/login`-Route authentifizierte nur das gemeinsame Gruppenpasswort
(falls gesetzt). Jeder Teilnehmer konnte einen vorhandenen Benutzernamen wählen
und dessen Identität einschließlich Adminrechten übernehmen. Unbekannte Namen
wurden automatisch registriert; die erste Registrierung erhielt Adminrechte.
Es gab weder Passwort-Hashes noch Login-Limits. Das Cookie enthielt eine signierte
Benutzer-ID, war aber nach Logout serverseitig nicht widerrufbar. CSRF-Tokens
waren bereits vorhanden. Die vorhandenen Rechteprüfungen verwenden `g.user` und
die in SQLite gespeicherten Rollen; diese Struktur bleibt erhalten.

## Rückwärtskompatible Migration

1. Vor dem produktiven Update den Server stoppen und `data` vollständig sichern.
   Den Server erst nach Abschluss laufender Seed-Generierungen stoppen.
2. `users` erhält ausschließlich die zusätzliche Spalte `password_hash` mit
   leerem Standardwert. Benutzer-IDs, Namen, Slotnamen, Profile, Vorlagen,
   Mitgliedschaften und Adminflags werden nicht geändert oder neu angelegt.
3. Neue Tabellen speichern gehashte Sitzungstokens, Einrichtungscodes und
   Login-Zähler. Die Migration ist wiederholbar. Bereits gespeicherte
   Einladungscode-Einstellungen bleiben erhalten, werden aber nicht mehr verwendet.
4. Altkonten ohne Passwort können sich zunächst nicht anmelden. Ein Gruppencode,
   eine bisherige Cookie-Benutzer-ID und die Registrierung dürfen diese Konten
   nicht übernehmen. Alte Cookies bleiben ungültig, ohne `secret.key` zu ersetzen.
5. Der Host stellt lokal einen persönlichen Einrichtungscode für seinen
   bestehenden Admin aus. Der Code gilt 24 Stunden und ist einmal verwendbar.
   Erst der Besitzer legt damit sein eigenes Passwort im Browser fest.
6. Der bestehende Admin kann danach für die weiteren Konten Einrichtungscodes
   ausgeben. Er muss die Empfänger außerhalb der Website als Kontobesitzer
   identifizieren. Neue Spieler registrieren sich direkt mit Benutzername und Passwort.
   Solange bereits Konten existieren, erhalten neue Registrierungen Spielerrechte.
   Nur bei vollständig leerer Benutzerliste wird das erste registrierte Konto Admin.

Die Tests verwenden ausschließlich temporäre Daten. Die additive Migration
erfolgt beim Serverstart oder beim ausdrücklichen Aufruf des lokalen
Kontowerkzeugs. Die vereinfachte Registrierung benötigt keine neue Migration.
Es gibt keinen automatischen Push oder Merge.

## Bestehenden Admin einrichten

Nach Backup und Stopp des alten Servers im Projektordner:

```powershell
& "$env:USERPROFILE\.ap-yaml-hub\venv\Scripts\python.exe" -m hub.auth setup-account Manu
.\start.ps1
```

`Manu` durch den tatsächlichen bisherigen Admin-Benutzernamen ersetzen.
Der erste Befehl migriert nur die Kontotabellen und zeigt einen persönlichen
Einrichtungscode an. Er startet keine APWorlds und unterbricht keine Seed-Jobs.
Im Browser `http://127.0.0.1:8080/account/setup` öffnen, den Code einfügen und
ein eigenes Passwort vergeben. Anschließend normal anmelden.

Bei einer vollständig neuen Installation ohne Benutzer einfach `/register`
öffnen: Das erste registrierte Konto wird automatisch Admin. Die Prüfung und
Kontoanlage erfolgen in einer gemeinsamen SQLite-Schreibtransaktion, sodass
auch bei gleichzeitigen Registrierungen nur ein erstes Konto Admin wird.
Alternativ bleibt die lokale Einrichtung verfügbar:

```powershell
& "$env:USERPROFILE\.ap-yaml-hub\venv\Scripts\python.exe" -m hub.auth bootstrap-admin Manu
```

Der Bootstrap ist gesperrt, sobald irgendein Benutzer existiert. Dadurch wird
kein vorhandener Spieler automatisch zum Admin. Für eine spätere lokale
Passwortwiederherstellung gibt es `python -m hub.auth reset-account BENUTZER`.
`setup-account` lehnt Konten mit vorhandenem Passwort ab.

## Neue Spieler registrieren

Neue Spieler öffnen `/register`, wählen Benutzernamen und ein eigenes Passwort
und sind danach direkt angemeldet. Das Formular hat nur diese beiden Felder.
Das Passwort muss nicht leer sein; es gibt keine Mindestlänge oder Zeichenregeln.
Einladungscode und Adminfreigabe sind nicht erforderlich. Alte Umgebungsvariablen
`HUB_INVITE_CODE` und `HUB_PASSWORD` sowie gespeicherte Einladungscode-Hashes
werden ignoriert. Die Verwaltung und das CLI-Kommando für Gruppencodes entfallen.

Persönliche Einrichtungscodes bleiben ausschließlich für bestehende Konten ohne
Passwort und für die Passwortwiederherstellung verfügbar. Ein bereits vergebener
Benutzername kann über die offene Registrierung nicht übernommen werden.

## Sicherheitsverhalten

- Passwörter dürfen beliebig gewählt werden, mit 1 bis 1024 Zeichen und ohne
  erzwungene Sonderzeichenregeln. Die Obergrenze begrenzt die Eingabegröße.
  Gespeichert werden gesalzene scrypt-Hashes über
  [Werkzeug](https://werkzeug.palletsprojects.com/en/stable/utils/#werkzeug.security.generate_password_hash).
  Passwörter erscheinen weder in Datenbank-Klartext noch in Cookies oder
  Kommandozeilenargumenten. Einrichtungscodes und Sitzungstokens liegen in SQLite
  nur als SHA-256-Digests ihrer kryptografisch zufälligen Werte vor.
- Sitzungen laufen nach acht Stunden ab. Login ersetzt Zustand und CSRF-Token.
  Logout widerruft das aktuelle Sitzungstoken; eine Kopie des alten Cookies
  funktioniert danach nicht mehr. Passwortwiederherstellung beendet alle
  Sitzungen des betroffenen Kontos. Rollen werden bei jeder Anfrage neu geladen.
- Cookies verwenden `HttpOnly` und `SameSite=Lax`. Für HTTPS-Betrieb
  `HUB_COOKIE_SECURE=1` setzen. `Secure` ist für das lokale HTTP-Setup abschaltbar;
  außerhalb von localhost Passwörter über HTTPS transportieren. Das Startskript
  aktiviert kein TLS. Siehe auch die
  [Flask-Sicherheitshinweise](https://flask.palletsprojects.com/en/stable/web-security/#set-cookie-options).
- Alle schreibenden Web-Anfragen einschließlich Login, Registrierung, Logout,
  Codeausgabe und Passwortvergabe benötigen ein CSRF-Token. Ungültige
  Unicode-Token führen zu einer Ablehnung statt einem Serverfehler.
- SQLite begrenzt Login-Anfragen in festen 15-Minuten-Fenstern auf 10 pro
  Benutzername und 30 pro IP. Registrierungen und Einrichtungscode-Eingaben sind
  auf jeweils 10 pro IP begrenzt. Auch erfolgreiche Login-Versuche werden gezählt.
  Sperren liefern HTTP 429 und `Retry-After`, bleiben über Neustarts erhalten und
  werden nicht durch neue Cookies umgangen. Gefälschte `X-Forwarded-For`-Header
  werden nicht als Client-IP verwendet. Hinter einem Proxy ist ohne explizite
  vertrauenswürdige Proxykonfiguration dessen IP die gemeinsame Grenze.
- Login-Fehler unterscheiden ungültige Benutzernamen, Altkonten und falsche
  Passwörter nicht. Fehlende Konten durchlaufen ebenfalls die Passwortprüfung.
  Weiterleitungen nach Login dürfen nur lokale Pfade verwenden.
- Einrichtungscodes werden per POST übergeben, nicht in URLs. Codeausgabe und
  persönliche Antworten sind mit `Cache-Control: no-store` und
  `Referrer-Policy: no-referrer` versehen. Rohcodes werden nicht in Flash-Cookies
  abgelegt. Ein neuer Code ersetzt den vorherigen.

Die bisher ausdrücklich gewünschte automatische Ausführung hochgeladener
APWorlds bleibt bestehen. Solcher Code hat weiterhin Serverrechte und könnte
auch auf Kontodaten zugreifen; die neue Anmeldung schafft keine Isolation gegen
ausführbaren Code im selben Prozess-/Dateisystem-Vertrauensbereich.

## Tests

```powershell
.\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v
```

Die Authentifizierungstests verwenden temporäre Datenbanken und prüfen echte
Passwort-Hashes, offene Registrierung mit kurzen Passwörtern, Migration, Einrichtungscodes,
Cookie-Widerruf, Rollen, CSRF, Ablaufzeiten und Login-Limits. Die bisherigen
Feature-Tests provisionieren explizite Testkonten und melden diese über die
neue Passwortprüfung an. Der produktive Server und produktive Konten werden
für diese Prüfung nicht benutzt.
