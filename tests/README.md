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

Danach dasselbe für `tests/test_users.py`, `tests/test_media.py`,
`tests/test_register.py`, `tests/test_avatars.py`, `tests/test_notify.py`,
`tests/test_login.py`, `tests/test_polls.py` und `tests/test_termine.py`.
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

`test_polls.py` (22 Prüfungen)

* Abstimmung anlegen, mit den Fehlerfällen und fremden Unterhaltungen.
* Abstimmen, zurücknehmen, Einfach- und Mehrfachwahl.
* Wer gestimmt hat, ist sichtbar; Antworten fremder Fragen werden abgewiesen.

`test_termine.py` (76 Prüfungen)

* Termin anlegen, mit Fehlerfällen; unbekannte Merkmale fallen weg.
* Zusagen, ändern, zurücknehmen; Fremde sehen und beantworten nichts.
* Die Terminliste zeigt nur Anstehendes; absagen darf nur der Gastgeber.
* Das Bild einer Einladung sehen Mitglieder, Fremde nicht – und eine fremde
  Datei lässt sich nicht einhängen.
* Live-Standort: starten, Dauer gedeckelt, Ping, beenden; nur Mitglieder
  sehen ihn, und wer die Gruppe verlässt, teilt dort nicht weiter.
* Stimmung: setzen, ersetzen, mitmachen, löschen – sichtbar nur für den
  eigenen Kreis.
* Was die Live-Karte zieht: Termine mit Koordinaten bringen sie mit, solche
  ohne bleiben ohne, abgesagte fallen aus der Liste.
* Leaflet und seine Beigaben liegen im Add-on und bleiben klein.
* Die Straßenkarte lässt sich abschalten; die Einstellung hängt am Konto,
  gilt also auch in einer neuen Sitzung, und betrifft niemanden sonst.

`test_notify.py` (13 Prüfungen)

* Das Token sieht nur ein Administrator.
* Nachrichten an Personen und Gruppen, mit den Fehlerfällen.
* Benachrichtigt wird nur, wer nicht zusieht – ausser bei `always`.

`test_avatars.py` (24 Prüfungen)

* Bild setzen, abrufen, ersetzen und entfernen, jeweils mit Blick auf die
  Dateien auf der Platte.
* Nur Bilder werden angenommen.
* Gruppenbilder sehen und setzen nur Mitglieder; Direktchats haben keins.

`test_register.py` (24 Prüfungen)

* Die Registrierungsseite ist ohne Anmeldung erreichbar, die Pflichtangaben
  greifen.
* Vor der Freigabe kommt niemand hinein und taucht in keiner Liste auf.
* Freigeben und Ablehnen, dazu die Bremse gegen Massenanträge.

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
