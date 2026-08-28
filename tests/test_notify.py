"""Die Schnittstelle fuer Home Assistant und das Token dazu."""
import os
import sys

import requests

from helpers import (BASE, Ergebnis, als_admin, anmelden, eigene_id,
                     verbindungen_schliessen, verbindung)


def melde(token, **felder):
    return requests.post(f"{BASE}/api/notify",
                         headers={"Authorization": f"Bearer {token}"},
                         json=felder)


def main():
    e = Ergebnis()
    admin = als_admin()
    admin.post(f"{BASE}/api/users", json={"username": "rosa",
                                          "display_name": "Rosa Rot",
                                          "password": "start123"})
    rosa, _ = anmelden("rosa", "start123")
    rosa_id = eigene_id(rosa)

    e.abschnitt("Das Token bekommt nur ein Verwalter")
    r = admin.get(f"{BASE}/api/token")
    e.pruefe(r.status_code == 200 and r.json().get("token"),
             f"Administrator sieht es = {r.status_code}")
    token = r.json()["token"]
    e.pruefe(rosa.get(f"{BASE}/api/token").status_code == 403,
             "ein gewoehnliches Konto nicht")
    e.pruefe(requests.get(f"{BASE}/api/token").status_code == 401,
             "ohne Anmeldung erst recht nicht")

    e.abschnitt("Nachricht aus Home Assistant")
    e.pruefe(melde("falsch", room="Rosa Rot", message="hallo").status_code == 401,
             "ein falsches Token wird abgewiesen")
    e.pruefe(melde(token, room="Rosa Rot").status_code == 400,
             "ohne Text geht es nicht")
    e.pruefe(melde(token, room="Gibtsnicht", message="hallo").status_code == 404,
             "ein unbekannter Empfaenger wird gemeldet")

    r = melde(token, room="rosa", message="Die Waschmaschine ist fertig")
    e.pruefe(r.status_code == 200, f"an eine Person = {r.status_code}")
    raum = r.json()["room_id"]
    nachrichten = rosa.get(f"{BASE}/api/rooms/{raum}/messages").json()
    e.pruefe(any(m["body"] == "Die Waschmaschine ist fertig" for m in nachrichten),
             "die Nachricht steht im Chat")
    e.pruefe(nachrichten[-1]["author"] == "Home Assistant",
             f"Absender ist das Konto: {nachrichten[-1]['author']}")

    gruppe = admin.post(f"{BASE}/api/rooms", json={
        "name": "Haus", "is_group": True, "members": [rosa_id]}).json()["id"]
    r = melde(token, room="Haus", message="Fenster offen")
    e.pruefe(r.status_code == 200 and r.json()["room_id"] == gruppe,
             "an eine Gruppe")

    e.abschnitt("Push nur an Abwesende - ausser man verlangt es")
    # In der Gruppe sind Rosa und der Administrator. Beide verbinden sich,
    # gelten also als anwesend.
    verbindung(rosa)
    verbindung(admin)
    r = melde(token, room="Haus", message="Normalfall")
    e.pruefe(r.json().get("pushed") == 0,
             f"wer zusieht, bekommt keine Benachrichtigung: {r.json().get('pushed')}")
    r = melde(token, room="Haus", message="Rauchmelder!", always=True)
    e.pruefe(r.json().get("pushed") == 2,
             f"mit always geht sie an beide: {r.json().get('pushed')}")
    r = melde(token, room="Haus", message="auch als Text", always="true")
    e.pruefe(r.json().get("pushed") == 2,
             "auch wenn die Vorlage 'true' als Text schickt")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    os._exit(ergebnis)
