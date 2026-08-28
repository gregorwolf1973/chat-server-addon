"""Freundschaften - gegenseitig, und was sie sichtbar machen.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys

from helpers import BASE, Ergebnis, als_admin, anmelden, eigene_id


def lauf():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)

    for name in ("anna", "bodo", "carla"):
        admin.post(f"{BASE}/api/users", json={
            "username": name, "display_name": name.capitalize(),
            "password": "test1234"})
    ids = {u["username"]: u["id"]
           for u in admin.get(f"{BASE}/api/state").json()["users"]}
    anna, code = anmelden("anna", "test1234")
    assert code == 302
    bodo, code = anmelden("bodo", "test1234")
    assert code == 302
    carla, code = anmelden("carla", "test1234")
    assert code == 302

    e.abschnitt("Am Anfang kennt niemand jemanden")
    d = admin.get(f"{BASE}/api/freunde").json()
    e.pruefe(d["freunde"] == [], "keine Freunde")
    e.pruefe(len(d["andere"]) == 3, f"aber drei andere Konten = {len(d['andere'])}")
    e.pruefe(not any(u["username"] == "admin" for u in d["andere"]),
             "man selbst steht nicht in der Liste")

    e.abschnitt("Anfragen und annehmen")
    r = admin.post(f"{BASE}/api/freunde/{ids['anna']}")
    e.pruefe(r.status_code == 200 and r.json()["stand"] == "gesendet",
             f"die Anfrage geht raus = {r.json()}")
    e.pruefe(admin.get(f"{BASE}/api/freunde").json()["freunde"] == [],
             "eine Anfrage allein macht noch keine Freundschaft")
    d = anna.get(f"{BASE}/api/freunde").json()
    e.pruefe([u["username"] for u in d["eingehend"]] == ["admin"],
             f"bei Anna wartet sie = {[u['username'] for u in d['eingehend']]}")
    e.pruefe(anna.get(f"{BASE}/api/state").json()["freund_anfragen"] == 1,
             "und der Startzustand nennt sie")

    r = admin.post(f"{BASE}/api/freunde/{ids['anna']}")
    e.pruefe(r.json()["stand"] == "gesendet",
             "noch einmal anfragen aendert nichts")

    r = anna.post(f"{BASE}/api/freunde/{admin_id}")
    e.pruefe(r.json()["stand"] == "freund",
             f"Annas Zusage macht die Freundschaft = {r.json()}")
    e.pruefe([u["username"] for u in
              admin.get(f"{BASE}/api/freunde").json()["freunde"]] == ["anna"],
             "sie steht bei beiden")
    e.pruefe(anna.get(f"{BASE}/api/state").json()["freunde"] == [admin_id],
             "auch im Startzustand")
    e.pruefe(anna.get(f"{BASE}/api/state").json()["freund_anfragen"] == 0,
             "und es wartet nichts mehr")

    e.abschnitt("Unfug")
    e.pruefe(admin.post(f"{BASE}/api/freunde/{admin_id}").status_code == 400,
             "mit sich selbst geht es nicht")
    e.pruefe(admin.post(f"{BASE}/api/freunde/9999").status_code == 404,
             "ein unbekanntes Konto auch nicht")
    bot = admin.get(f"{BASE}/api/users").json()
    e.pruefe(not any(u["username"] == "homeassistant" for u in bot)
             or admin.post(f"{BASE}/api/freunde/"
                           f"{[u for u in bot if u['username']=='homeassistant'][0]['id']}"
                           ).status_code == 404,
             "und mit dem Bot-Konto erst recht nicht")

    e.abschnitt("Der Kreis waechst mit den Freunden")
    # Admin und Bodo teilen keine Unterhaltung. Ohne Freundschaft sieht Bodo
    # die Stimmung des Admins nicht.
    admin.post(f"{BASE}/api/stimmung", json={"text": "Lust auf Kino"})
    e.pruefe(len(bodo.get(f"{BASE}/api/stimmung").json()) == 0,
             "ein Fremder sieht die Stimmung nicht")
    e.pruefe(len(anna.get(f"{BASE}/api/stimmung").json()) == 1,
             "die Freundin schon - ganz ohne gemeinsame Unterhaltung")

    admin.post(f"{BASE}/api/freunde/{ids['bodo']}")
    bodo.post(f"{BASE}/api/freunde/{admin_id}")
    e.pruefe(len(bodo.get(f"{BASE}/api/stimmung").json()) == 1,
             "nach der Freundschaft sieht Bodo sie")
    r = bodo.post(f"{BASE}/api/stimmung/"
                  f"{bodo.get(f'{BASE}/api/stimmung').json()[0]['id']}/mit")
    e.pruefe(r.status_code == 200, f"und kann mitmachen = {r.status_code}")

    e.abschnitt("Eine gemeinsame Unterhaltung genuegt weiterhin")
    raum = admin.post(f"{BASE}/api/rooms", json={
        "name": "Runde", "is_group": True, "members": [ids["carla"]]}).json()["id"]
    e.pruefe(len(carla.get(f"{BASE}/api/stimmung").json()) == 1,
             "Carla sieht sie ohne Freundschaft, weil sie mit im Raum sitzt")
    e.pruefe(carla.get(f"{BASE}/api/state").json()["freunde"] == [],
             "und ist trotzdem nicht befreundet")

    e.abschnitt("Loesen")
    r = bodo.delete(f"{BASE}/api/freunde/{admin_id}")
    e.pruefe(r.status_code == 200, f"Bodo beendet die Freundschaft = {r.status_code}")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["freunde"] == [ids["anna"]],
             "beim Admin ist er fort")
    e.pruefe(len(bodo.get(f"{BASE}/api/stimmung").json()) == 0,
             "und er sieht die Stimmung nicht mehr")

    e.abschnitt("Ablehnen und zuruecknehmen")
    admin.post(f"{BASE}/api/freunde/{ids['bodo']}")
    e.pruefe(len(bodo.get(f"{BASE}/api/freunde").json()["eingehend"]) == 1,
             "eine neue Anfrage wartet")
    bodo.delete(f"{BASE}/api/freunde/{admin_id}")
    e.pruefe(len(bodo.get(f"{BASE}/api/freunde").json()["eingehend"]) == 0,
             "Ablehnen raeumt sie weg")
    e.pruefe(len(admin.get(f"{BASE}/api/freunde").json()["ausgehend"]) == 0,
             "auch beim Absender")
    admin.post(f"{BASE}/api/freunde/{ids['bodo']}")
    admin.delete(f"{BASE}/api/freunde/{ids['bodo']}")
    e.pruefe(len(bodo.get(f"{BASE}/api/freunde").json()["eingehend"]) == 0,
             "und Zuruecknehmen ebenso")

    e.abschnitt("Ein geloeschtes Konto nimmt seine Freundschaften mit")
    admin.post(f"{BASE}/api/freunde/{ids['carla']}")
    carla.post(f"{BASE}/api/freunde/{admin_id}")
    e.pruefe(ids["carla"] in admin.get(f"{BASE}/api/state").json()["freunde"],
             "Carla ist befreundet")
    admin.delete(f"{BASE}/api/users/{ids['carla']}")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["freunde"] == [ids["anna"]],
             "nach dem Loeschen bleibt nur Anna")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    import requests
    e.pruefe(requests.get(f"{BASE}/api/freunde",
                          allow_redirects=False).status_code in (302, 401),
             "die Liste bleibt zu")
    e.pruefe(requests.post(f"{BASE}/api/freunde/1",
                           allow_redirects=False).status_code in (302, 401),
             "und anfragen kann nur, wer angemeldet ist")

    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
