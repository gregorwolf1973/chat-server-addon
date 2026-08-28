"""Empfehlungen - wer sie schreiben, sehen und aendern darf.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys

from helpers import BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id, hochladen


def lauf():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)

    for name in ("anna", "bodo"):
        admin.post(f"{BASE}/api/users", json={
            "username": name, "display_name": name.capitalize(),
            "password": "test1234"})
    ids = {u["username"]: u["id"]
           for u in admin.get(f"{BASE}/api/state").json()["users"]}
    anna, code = anmelden("anna", "test1234")
    assert code == 302
    bodo, code = anmelden("bodo", "test1234")
    assert code == 302

    e.abschnitt("Eine Empfehlung schreiben")
    r = admin.post(f"{BASE}/api/tipps", json={
        "art": "restaurant", "titel": "Ristorante Bella", "sterne": 4,
        "ort_text": "Hauptstrasse 4", "lat": 49.01, "lon": 8.40,
        "text": "Die Pizza ist gut, laut ist es trotzdem."})
    e.pruefe(r.status_code == 200, f"sie wird angenommen = {r.status_code}")
    tipp = r.json()
    e.pruefe(tipp["titel"] == "Ristorante Bella", "mit dem richtigen Namen")
    e.pruefe(tipp["sterne"] == 4, f"und den Sternen = {tipp['sterne']}")
    e.pruefe(tipp["ort"] and abs(tipp["ort"]["lat"] - 49.01) < 0.001,
             "der Ort ist gespeichert")
    e.pruefe(tipp["meiner"] is True, "sie gehoert mir")

    e.pruefe(admin.post(f"{BASE}/api/tipps",
                        json={"titel": "", "sterne": 3}).status_code == 400,
             "ohne Namen geht es nicht")
    e.pruefe(admin.post(f"{BASE}/api/tipps",
                        json={"titel": "Ohne Note"}).status_code == 400,
             "ohne Sterne auch nicht")
    r = admin.post(f"{BASE}/api/tipps",
                   json={"art": "quatsch", "titel": "Krumm", "sterne": 99})
    e.pruefe(r.json()["art"] == "sonstiges",
             f"eine unbekannte Art wird zu sonstiges = {r.json()['art']}")
    e.pruefe(r.json()["sterne"] == 5,
             f"und zu viele Sterne werden gedeckelt = {r.json()['sterne']}")
    admin.delete(f"{BASE}/api/tipps/{r.json()['id']}")

    e.abschnitt("Sichtbar ist sie nur im eigenen Kreis")
    e.pruefe(len(admin.get(f"{BASE}/api/tipps").json()["tipps"]) == 1,
             "der Verfasser sieht sie")
    e.pruefe(len(anna.get(f"{BASE}/api/tipps").json()["tipps"]) == 0,
             "eine Fremde nicht")

    admin.post(f"{BASE}/api/freunde/{ids['anna']}")
    anna.post(f"{BASE}/api/freunde/{admin_id}")
    e.pruefe(len(anna.get(f"{BASE}/api/tipps").json()["tipps"]) == 1,
             "nach der Freundschaft schon")
    e.pruefe(len(bodo.get(f"{BASE}/api/tipps").json()["tipps"]) == 0,
             "Bodo weiterhin nicht")
    admin.post(f"{BASE}/api/rooms", json={
        "name": "Runde", "is_group": True, "members": [ids["bodo"]]})
    e.pruefe(len(bodo.get(f"{BASE}/api/tipps").json()["tipps"]) == 1,
             "eine gemeinsame Unterhaltung genuegt aber auch")

    e.abschnitt("Merken")
    tipp_id = tipp["id"]
    r = anna.post(f"{BASE}/api/tipps/{tipp_id}/merken")
    e.pruefe(r.status_code == 200 and r.json()["ich_merke"] is True,
             f"Anna merkt sie sich = {r.status_code}")
    e.pruefe(len(admin.get(f"{BASE}/api/tipps").json()["tipps"][0]["gemerkt"]) == 1,
             "das sieht auch der Verfasser")
    r = anna.post(f"{BASE}/api/tipps/{tipp_id}/merken")
    e.pruefe(r.json()["ich_merke"] is False, "noch einmal nimmt es zurueck")

    e.abschnitt("Aendern darf nur der Verfasser")
    e.pruefe(anna.patch(f"{BASE}/api/tipps/{tipp_id}",
                        json={"titel": "Meins"}).status_code == 403,
             "Anna kommt nicht durch")
    e.pruefe(bodo.delete(f"{BASE}/api/tipps/{tipp_id}").status_code == 403,
             "und loeschen kann sie auch niemand sonst")
    r = admin.patch(f"{BASE}/api/tipps/{tipp_id}",
                    json={"sterne": 2, "text": "Doch zu laut."})
    e.pruefe(r.status_code == 200 and r.json()["sterne"] == 2,
             f"der Verfasser schon = {r.status_code}")
    e.pruefe(r.json()["titel"] == "Ristorante Bella",
             "nicht mitgeschickte Felder bleiben stehen")
    e.pruefe(r.json()["ort"] is not None, "auch der Ort")
    r = admin.patch(f"{BASE}/api/tipps/{tipp_id}", json={"lat": None, "lon": None})
    e.pruefe(r.json()["ort"] is None, "und laesst sich gezielt entfernen")
    e.pruefe(admin.patch(f"{BASE}/api/tipps/{tipp_id}",
                         json={"titel": "  "}).status_code == 400,
             "ein leerer Name wird abgewiesen")

    e.abschnitt("Das Bild einer Empfehlung")
    datei = hochladen(admin, "essen.png", PNG, "image/png").json()["id"]
    admin.patch(f"{BASE}/api/tipps/{tipp_id}", json={"file_id": datei})
    e.pruefe(admin.get(f"{BASE}/api/tipps").json()["tipps"][0]["file_id"] == datei,
             "es haengt am Tipp")
    e.pruefe(anna.get(f"{BASE}/files/{datei}").status_code == 200,
             "die Freundin darf es sehen")
    fremd = hochladen(anna, "fremd.png", PNG, "image/png").json()["id"]
    admin.patch(f"{BASE}/api/tipps/{tipp_id}", json={"file_id": fremd})
    e.pruefe(admin.get(f"{BASE}/api/tipps").json()["tipps"][0]["file_id"] is None,
             "eine fremde Datei laesst sich nicht einhaengen")
    e.pruefe(admin.get(f"{BASE}/files/{datei}").status_code == 404,
             "das abgeloeste Bild wird aufgeraeumt")

    e.abschnitt("Loeschen")
    admin.post(f"{BASE}/api/tipps", json={"art": "kino", "titel": "Weg damit",
                                          "sterne": 3})
    weg = admin.get(f"{BASE}/api/tipps").json()["tipps"][0]["id"]
    e.pruefe(admin.delete(f"{BASE}/api/tipps/{weg}").status_code == 200,
             "der eigene Tipp geht weg")
    e.pruefe(len(admin.get(f"{BASE}/api/tipps").json()["tipps"]) == 1,
             "und ist fort")

    e.abschnitt("Ein geloeschtes Konto nimmt seine Tipps mit")
    anna.post(f"{BASE}/api/tipps", json={"art": "bar", "titel": "Annas Kneipe",
                                         "sterne": 5})
    e.pruefe(any(t["titel"] == "Annas Kneipe"
                 for t in admin.get(f"{BASE}/api/tipps").json()["tipps"]),
             "Annas Tipp ist da")
    admin.delete(f"{BASE}/api/users/{ids['anna']}")
    e.pruefe(not any(t["titel"] == "Annas Kneipe"
                     for t in admin.get(f"{BASE}/api/tipps").json()["tipps"]),
             "nach dem Loeschen ihres Kontos nicht mehr")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    import requests
    for pfad, methode in (("/api/tipps", requests.get),
                          ("/api/tipps", requests.post),
                          (f"/api/tipps/{tipp_id}/merken", requests.post)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad} weist Fremde ab = {r.status_code}")

    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
