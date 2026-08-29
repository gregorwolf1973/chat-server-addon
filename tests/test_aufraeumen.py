"""Automatisches Loeschen alter Nachrichten und Anhaenge.

Diese Reihe braucht einen Server, der mit RETENTION_DAYS=1 gestartet wurde -
sonst ist keine Frist gesetzt und es gibt nichts zu pruefen. Ausserdem greift
sie zum Altern der Nachrichten direkt in die Datenbank; ueber die
Schnittstelle laesst sich kein Datum von gestern erzeugen.

    DATA_DIR=... RETENTION_DAYS=1 python server.py
    PYTHONPATH=tests python tests/test_aufraeumen.py
"""
import io
import os
import sqlite3
import sys
import time

import requests

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, senden_mit_antwort, verbindungen_schliessen)


def datenbank():
    ordner = os.environ.get("DATA_DIR")
    if not ordner:
        return None
    pfad = os.path.join(ordner, "chat.db")
    return pfad if os.path.exists(pfad) else None


def altern(msg_ids, tage):
    """Nachrichten kuenstlich altern lassen."""
    pfad = datenbank()
    if not pfad:
        return False
    conn = sqlite3.connect(pfad, timeout=10)
    frueher = int(time.time()) - tage * 86400
    conn.executemany("UPDATE messages SET created_at=? WHERE id=?",
                     [(frueher, i) for i in msg_ids])
    conn.commit()
    conn.close()
    return True


def lauf():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    admin.post(f"{BASE}/api/users", json={"username": "anna",
                                          "display_name": "Anna",
                                          "password": "test1234"})
    anna, code = anmelden("anna", "test1234")
    assert code == 302
    anna_id = eigene_id(anna)
    raum = admin.post(f"{BASE}/api/rooms", json={
        "name": "Runde", "is_group": True, "members": [anna_id]}).json()["id"]

    e.abschnitt("Die eingestellte Frist")
    r = admin.get(f"{BASE}/api/aufbewahrung")
    e.pruefe(r.status_code == 200, f"sie laesst sich lesen = {r.status_code}")
    tage = r.json()["tage"]
    e.pruefe(tage == 1,
             f"der Server laeuft mit einem Tag = {tage}"
             + ("" if tage == 1 else "  (RETENTION_DAYS=1 setzen!)"))
    if tage != 1:
        return e.bilanz()

    e.abschnitt("Altes verschwindet, Neues bleibt")
    datei = hochladen(admin, "alt.png", PNG, "image/png").json()
    senden_mit_antwort(admin, raum, "uralt", datei=datei["id"])
    senden_mit_antwort(admin, raum, "auch alt")
    senden_mit_antwort(admin, raum, "ganz frisch")
    msgs = admin.get(f"{BASE}/api/rooms/{raum}/messages").json()
    alte = [m["id"] for m in msgs if m["body"] in ("uralt", "auch alt")
            or (m.get("file") and m["file"]["id"] == datei["id"])]
    e.pruefe(len(alte) >= 2, f"zwei Nachrichten zum Altern = {len(alte)}")
    e.pruefe(altern(alte, 3), "sie werden auf drei Tage zurueckdatiert")

    r = admin.get(f"{BASE}/api/aufbewahrung")
    e.pruefe(r.json()["faellig"] == len(alte),
             f"der Server sieht sie als faellig = {r.json()['faellig']}")

    r = admin.post(f"{BASE}/api/aufbewahrung/jetzt")
    e.pruefe(r.status_code == 200, f"aufraeumen laesst sich ausloesen = {r.status_code}")
    e.pruefe(r.json()["nachrichten"] == len(alte),
             f"und entfernt genau sie = {r.json()}")
    e.pruefe(r.json()["dateien"] == 1,
             f"samt dem Anhang = {r.json()['dateien']} Datei(en)")

    uebrig = [m["body"] for m in
              admin.get(f"{BASE}/api/rooms/{raum}/messages").json()]
    e.pruefe(uebrig == ["ganz frisch"], f"die junge bleibt = {uebrig}")
    e.pruefe(admin.get(f"{BASE}/files/{datei['id']}").status_code == 404,
             "der Anhang ist fort")
    e.pruefe(admin.get(f"{BASE}/api/aufbewahrung").json()["faellig"] == 0,
             "danach ist nichts mehr faellig")

    e.abschnitt("Ein noch benutzter Anhang bleibt")
    zwei = hochladen(admin, "geteilt.png", PNG, "image/png").json()
    senden_mit_antwort(admin, raum, "erste", datei=zwei["id"])
    msgs = admin.get(f"{BASE}/api/rooms/{raum}/messages").json()
    erste = [m for m in msgs if m["body"] == "erste"][0]
    # Dieselbe Datei ein zweites Mal - ueber das Weiterleiten
    eigener = admin.post(f"{BASE}/api/rooms", json={
        "is_group": False, "members": [anna_id]}).json()["id"]
    admin.post(f"{BASE}/api/messages/{erste['id']}/weiterleiten",
               json={"room_id": eigener})
    altern([erste["id"]], 3)
    r = admin.post(f"{BASE}/api/aufbewahrung/jetzt")
    e.pruefe(r.json()["nachrichten"] == 1, "die alte Nachricht geht weg")
    e.pruefe(r.json()["dateien"] == 0,
             f"die Datei nicht - sie haengt noch woanders = {r.json()}")
    e.pruefe(admin.get(f"{BASE}/files/{zwei['id']}").status_code == 200,
             "und ist weiterhin abrufbar")

    e.abschnitt("Nur der Administrator raeumt auf")
    e.pruefe(anna.post(f"{BASE}/api/aufbewahrung/jetzt").status_code == 403,
             "Anna darf das nicht")
    e.pruefe(anna.get(f"{BASE}/api/aufbewahrung").status_code == 200,
             "die Frist sehen darf sie aber")
    e.pruefe(requests.get(f"{BASE}/api/aufbewahrung",
                          allow_redirects=False).status_code in (302, 401),
             "ohne Anmeldung nicht")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
