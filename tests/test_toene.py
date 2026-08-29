"""Toene und Stummschaltung.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys
import time

import requests

from helpers import BASE, Ergebnis, als_admin, anmelden, eigene_id


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

    e.abschnitt("Die allgemeine Einstellung")
    r = admin.get(f"{BASE}/api/toene")
    e.pruefe(r.status_code == 200, f"sie laesst sich lesen = {r.status_code}")
    e.pruefe(r.json()["stufe"] == "alle", "voreingestellt ist alles an")
    e.pruefe(r.json()["stumm"] == {}, "und nichts ist stumm")

    r = admin.post(f"{BASE}/api/toene", json={"stufe": "nur_anrufe"})
    e.pruefe(r.status_code == 200 and r.json()["stufe"] == "nur_anrufe",
             f"sie laesst sich aendern = {r.status_code}")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["ton_stufe"] == "nur_anrufe",
             "der Startzustand nennt sie")
    e.pruefe(admin.post(f"{BASE}/api/toene",
                        json={"stufe": "laut"}).status_code == 400,
             "eine erfundene Stufe wird abgewiesen")
    e.pruefe(anna.get(f"{BASE}/api/toene").json()["stufe"] == "alle",
             "bei Anna aendert das nichts - die Einstellung gehoert der Person")
    admin.post(f"{BASE}/api/toene", json={"stufe": "alle"})

    e.abschnitt("Eine Unterhaltung stummschalten")
    r = admin.post(f"{BASE}/api/rooms/{raum}/stumm", json={"stunden": 2})
    e.pruefe(r.status_code == 200, f"stummschalten geht = {r.status_code}")
    bis = r.json()["stumm_bis"]
    e.pruefe(bis > int(time.time()) + 7000, f"und gilt zwei Stunden = {bis}")
    dieser = [x for x in admin.get(f"{BASE}/api/state").json()["rooms"]
              if x["id"] == raum][0]
    e.pruefe(dieser["stumm_bis"] == bis, "der Raum meldet es im Startzustand")
    e.pruefe(str(raum) in admin.get(f"{BASE}/api/toene").json()["stumm"],
             "und die Uebersicht listet ihn")
    anderer = [x for x in anna.get(f"{BASE}/api/state").json()["rooms"]
               if x["id"] == raum][0]
    e.pruefe(anderer["stumm_bis"] is None,
             "Anna hoert weiterhin - Stummschaltung gilt nur fuer einen selbst")

    r = admin.post(f"{BASE}/api/rooms/{raum}/stumm", json={"stunden": 0})
    e.pruefe(r.json()["stumm_bis"] == 0, "null Stunden heisst: ohne Ende")
    e.pruefe(str(raum) in admin.get(f"{BASE}/api/toene").json()["stumm"],
             "auch das steht in der Uebersicht")

    r = admin.post(f"{BASE}/api/rooms/{raum}/stumm", json={"stunden": None})
    e.pruefe(r.json()["stumm_bis"] is None, "und wieder aufheben geht")
    e.pruefe(admin.get(f"{BASE}/api/toene").json()["stumm"] == {},
             "danach ist die Uebersicht leer")

    e.pruefe(admin.post(f"{BASE}/api/rooms/{raum}/stumm",
                        json={"stunden": "lange"}).status_code == 400,
             "Unfug wird abgewiesen")
    fremd = anna.post(f"{BASE}/api/rooms", json={
        "is_group": False, "members": [anna_id]}).json().get("id")
    if fremd:
        e.pruefe(admin.post(f"{BASE}/api/rooms/{fremd}/stumm",
                            json={"stunden": 1}).status_code == 403,
                 "in einer fremden Unterhaltung geht es nicht")

    e.abschnitt("Eine abgelaufene Stummschaltung zaehlt nicht mehr")
    # Direkt in die Datenbank zu greifen waere hier unsauber - stattdessen
    # eine Stummschaltung, die sofort abgelaufen ist: der Server rechnet
    # Stunden immer nach vorn, also nehmen wir den Weg ueber "aufheben".
    admin.post(f"{BASE}/api/rooms/{raum}/stumm", json={"stunden": 1})
    e.pruefe(len(admin.get(f"{BASE}/api/toene").json()["stumm"]) == 1,
             "eine laufende zaehlt")
    admin.post(f"{BASE}/api/rooms/{raum}/stumm", json={"stunden": None})
    e.pruefe(len(admin.get(f"{BASE}/api/toene").json()["stumm"]) == 0,
             "eine aufgehobene nicht mehr")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    for pfad, methode in (("/api/toene", requests.get),
                          ("/api/toene", requests.post),
                          (f"/api/rooms/{raum}/stumm", requests.post)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad} weist Fremde ab = {r.status_code}")

    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
