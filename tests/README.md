# Tests

Die Testreihen sprechen einen laufenden Server über HTTP und Socket.IO an,
so wie der Browser es tut. Kein Mocking: was hier grün ist, funktioniert auch
im Add-on.

## Vorbereiten

```bash
python -m venv .venv
.venv/bin/pip install -r chat_server/requirements.txt -r tests/requirements.txt
```

Unter Windows liegen die Programme in `.venv/Scripts/` statt `.venv/bin/`.

## Ausführen

Jede Reihe braucht einen **frisch gestarteten Server auf einem leeren
Datenverzeichnis**. Also pro Reihe einmal:

```bash
DATA_DIR=$(mktemp -d) ADMIN_USER=admin ADMIN_PASSWORD=test1234 \
  .venv/bin/python chat_server/app/server.py &
sleep 3
PYTHONPATH=tests .venv/bin/python tests/test_security.py
kill %1
```

Danach dasselbe für `tests/test_users.py` und `tests/test_media.py`.
`test_media.py` prüft zusätzlich die Blobs auf der Platte und braucht
dafür dasselbe `DATA_DIR` wie der Server.

**Warum kein Skript, das beides hintereinander erledigt?** Weil der eingebaute
Werkzeug-Server das nicht mitmacht. Die Reihen beenden sich hart – sonst
halten die Hintergrundthreads des Socket.IO-Clients sie am Leben – und dabei
bleiben offene Long-Polling-Anfragen am Server hängen, die die nächste Reihe
blockieren. Dasselbe Verhalten steckt hinter dem
`AssertionError: write() before start_response`, den der Server beim
WebSocket-Aufbau ins Protokoll schreibt. Solange der Server so läuft, ist die
Isolation je Reihe der ehrlichere Weg.

Der frische Datenbestand ist ebenfalls nötig: Die Tests prüfen unter anderem,
dass ein Raum *keine* Datei enthält – gegen eine gewachsene Datenbank schlägt
das durch Altbestände fehl.

## Was geprüft wird

`test_security.py` (15 Prüfungen)

* Der MIME-Typ hochgeladener Dateien kommt vom Client und darf nicht geglaubt
  werden – `text/html` wird zu einem Download statt zu einer Seite.
* `nosniff` und eine enge CSP auf der Datei-Route.
* Fremde Datei-IDs lassen sich nicht an eigene Nachrichten hängen.
* Die Pfade im PWA-Manifest lösen auf existierende Adressen auf.

`test_media.py` (19 Prüfungen)

* Sichtbar sind nur Medien aus Unterhaltungen, in denen man Mitglied ist.
* Der Filter je Unterhaltung.
* Eigene Dateien löschen, fremde nur als Administrator.
* Gelöschte Dateien verschwinden auch von der Platte, und eine gelöschte
  Nachricht nimmt ihren Anhang mit.

`test_users.py` (35 Prüfungen)

* Konten anlegen, Anmeldung unabhängig von der Schreibweise.
* Passwort zurücksetzen, inklusive Verfall laufender Sitzungen.
* Sperren und entsperren, Rechte vergeben und entziehen.
* Die Regeln gegen das Aussperren: eigenes Konto, letzter Administrator.
* Löschen erhält den Verlauf unter „Gelöschtes Konto“.
