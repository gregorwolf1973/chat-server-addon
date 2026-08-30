"""Im Verlauf suchen, dorthin springen und die Wahl der Kartenanwendung.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys

import requests

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, senden_mit_antwort, verbindungen_schliessen)


def lauf():
    e = Ergebnis()
    admin = als_admin()
    for name in ("anna", "bert"):
        admin.post(f"{BASE}/api/users", json={"username": name,
                                              "display_name": name.capitalize(),
                                              "password": "test1234"})
    anna, code = anmelden("anna", "test1234")
    assert code == 302
    bert, code = anmelden("bert", "test1234")
    assert code == 302
    anna_id, bert_id = eigene_id(anna), eigene_id(bert)

    runde = admin.post(f"{BASE}/api/rooms", json={
        "name": "Runde", "is_group": True, "members": [anna_id]}).json()["id"]
    # Ein Raum, in dem der Administrator nichts zu suchen hat
    fremd = anna.post(f"{BASE}/api/rooms", json={
        "name": "Ohne dich", "is_group": True, "members": [bert_id]}).json()["id"]

    senden_mit_antwort(admin, runde, "Wir grillen am Hafen")
    senden_mit_antwort(anna, runde, "Grillen klingt gut")
    senden_mit_antwort(admin, runde, "Sonst nichts Besonderes")
    senden_mit_antwort(anna, fremd, "Hier grillen wir heimlich")

    def suche(sitzung, frage, raum=None):
        ziel = f"{BASE}/api/suche?q={frage}"
        if raum:
            ziel += f"&room={raum}"
        return sitzung.get(ziel)

    e.abschnitt("In einer Unterhaltung suchen")
    r = suche(admin, "grillen", runde)
    e.pruefe(r.status_code == 200, f"die Suche antwortet = {r.status_code}")
    treffer = r.json()["treffer"]
    e.pruefe(len(treffer) == 2, f"zwei Treffer in der Runde = {len(treffer)}")
    e.pruefe(all(t["room_id"] == runde for t in treffer),
             "beide aus dieser Unterhaltung")
    e.pruefe(treffer[0]["id"] > treffer[1]["id"], "neueste zuerst")
    e.pruefe({t["author"] for t in treffer} == {"admin", "Anna"},
             f"mit Absender = {[t['author'] for t in treffer]}")

    e.abschnitt("Gross und klein ist egal")
    e.pruefe(len(suche(admin, "GRILLEN", runde).json()["treffer"]) == 2,
             "GRILLEN findet dasselbe")
    e.pruefe(len(suche(admin, "GrIlLeN", runde).json()["treffer"]) == 2,
             "GrIlLeN auch")

    e.abschnitt("In allen Unterhaltungen")
    alle = suche(admin, "grillen").json()["treffer"]
    e.pruefe(len(alle) == 2,
             f"der Administrator sieht nur seine zwei = {len(alle)}")
    e.pruefe(all(t["room_id"] != fremd for t in alle),
             "die fremde Unterhaltung bleibt aussen vor")
    annas = suche(anna, "grillen").json()["treffer"]
    e.pruefe(len(annas) == 3, f"Anna ist in beiden und sieht drei = {len(annas)}")

    e.abschnitt("In einer fremden Unterhaltung geht es nicht")
    e.pruefe(suche(admin, "grillen", fremd).status_code == 403,
             "der Versuch wird abgewiesen")
    e.pruefe(suche(admin, "grillen", 9999).status_code == 403,
             "eine erfundene Unterhaltung ebenso")

    e.abschnitt("Zu kurz ist keine Frage")
    for frage in ("", "a"):
        r = suche(admin, frage)
        e.pruefe(r.status_code == 200 and r.json()["treffer"] == [],
                 f"eine Frage aus {len(frage)} Zeichen liefert nichts"
                 f" = {r.status_code}")

    e.abschnitt("Platzhalter zaehlen nicht")
    senden_mit_antwort(admin, runde, "Rabatt 100% auf alles")
    senden_mit_antwort(admin, runde, "Datei mit_unterstrich.txt")
    e.pruefe(len(suche(admin, "100%25", runde).json()["treffer"]) == 1,
             "nach '100%' wird woertlich gesucht")
    # Ein nacktes % wuerde als "alles" jede Nachricht treffen
    r = suche(admin, "%25%25", runde).json()["treffer"]
    e.pruefe(len(r) == 0, f"'%%' trifft nichts statt alles = {len(r)}")
    e.pruefe(len(suche(admin, "mit_unter", runde).json()["treffer"]) == 1,
             "der Unterstrich ebenfalls woertlich")
    r = suche(admin, "mit%5Funter", runde).json()["treffer"]
    e.pruefe(len(r) == 1, "und als Fluchtzeichen geschrieben genauso")

    e.abschnitt("Dateinamen zaehlen mit")
    datei = hochladen(admin, "Wanderkarte.pdf", PNG, "application/pdf").json()
    senden_mit_antwort(admin, runde, "", datei=datei["id"])
    r = suche(admin, "Wanderkarte", runde).json()["treffer"]
    e.pruefe(len(r) == 1, f"die Datei wird gefunden = {len(r)}")
    e.pruefe(r and r[0]["file"] and r[0]["file"]["name"] == "Wanderkarte.pdf",
             "und bringt ihren Namen mit")

    e.abschnitt("Geloeschtes bleibt verschwunden")
    weg = senden_mit_antwort(admin, runde, "Diesen Satz nehme ich zurueck")
    e.pruefe(len(suche(admin, "zurueck", runde).json()["treffer"]) == 1,
             "vorher ist er da")
    admin.delete(f"{BASE}/api/messages/{weg['id']}")
    e.pruefe(len(suche(admin, "zurueck", runde).json()["treffer"]) == 0,
             "nach dem Loeschen nicht mehr")

    e.abschnitt("Zu einem Treffer springen")
    for i in range(1, 121):
        senden_mit_antwort(admin, runde, f"Zeile {i}")
    ziel = suche(admin, "Zeile 5", runde).json()["treffer"]
    ziel = [t for t in ziel if t["body"] == "Zeile 5"][0]
    r = admin.get(f"{BASE}/api/rooms/{runde}/messages?um={ziel['id']}&limit=60")
    e.pruefe(r.status_code == 200, f"die Umgebung laesst sich holen = {r.status_code}")
    rund = r.json()
    e.pruefe(any(m["id"] == ziel["id"] for m in rund), "der Treffer steckt darin")
    e.pruefe(len(rund) <= 60, f"nicht mehr als verlangt = {len(rund)}")
    e.pruefe([m["id"] for m in rund] == sorted(m["id"] for m in rund),
             "aufsteigend sortiert")
    danach = [m for m in rund if m["id"] > ziel["id"]]
    davor = [m for m in rund if m["id"] < ziel["id"]]
    e.pruefe(len(danach) == 30, f"dreissig danach = {len(danach)}")
    e.pruefe(len(davor) >= 1, f"und was davor da war = {len(davor)}")
    # Mitten im Verlauf muss es auf beiden Seiten gleich viel sein
    mitte = suche(admin, "Zeile 60", runde).json()["treffer"]
    mitte = [t for t in mitte if t["body"] == "Zeile 60"][0]
    rund = admin.get(f"{BASE}/api/rooms/{runde}/messages"
                     f"?um={mitte['id']}&limit=60").json()
    e.pruefe(len([m for m in rund if m["id"] < mitte["id"]]) == 29
             and len([m for m in rund if m["id"] > mitte["id"]]) == 30,
             f"in der Mitte je dreissig = {len(rund)} zusammen")
    e.pruefe(anna.get(f"{BASE}/api/rooms/{fremd}/messages"
                      "?um=1&limit=20").status_code == 200,
             "Anna darf in ihrer Unterhaltung springen")
    e.pruefe(admin.get(f"{BASE}/api/rooms/{fremd}/messages"
                       "?um=1&limit=20").status_code == 403,
             "der Administrator nicht in der fremden")

    e.abschnitt("Aeltere nachladen")
    erste = admin.get(f"{BASE}/api/rooms/{runde}/messages?limit=50").json()
    e.pruefe(len(erste) == 50, f"der erste Schwung = {len(erste)}")
    zweiter = admin.get(f"{BASE}/api/rooms/{runde}/messages"
                        f"?before={erste[0]['id']}&limit=50").json()
    e.pruefe(len(zweiter) == 50, f"der zweite = {len(zweiter)}")
    e.pruefe(max(m["id"] for m in zweiter) < erste[0]["id"],
             "und liegt vollstaendig davor")
    e.pruefe(not ({m["id"] for m in zweiter} & {m["id"] for m in erste}),
             "ohne Ueberschneidung")

    e.abschnitt("Womit ein Ort geoeffnet wird")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["karten_app"] == "geraet",
             "voreingestellt ist die Anwendung des Geraets")
    apps = admin.get(f"{BASE}/api/karten-apps").json()
    e.pruefe(set(apps) == {"geraet", "google", "apple", "osm"},
             f"es gibt vier Moeglichkeiten = {apps}")
    r = admin.post(f"{BASE}/api/me/karten-app", json={"app": "google"})
    e.pruefe(r.status_code == 200 and r.json()["app"] == "google",
             f"eine laesst sich waehlen = {r.status_code}")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["karten_app"] == "google",
             "und steht im Startzustand")
    e.pruefe(anna.get(f"{BASE}/api/state").json()["me"]["karten_app"] == "geraet",
             "bei Anna aendert das nichts")
    e.pruefe(admin.post(f"{BASE}/api/me/karten-app",
                        json={"app": "navi"}).status_code == 400,
             "eine erfundene wird abgewiesen")
    e.pruefe(admin.post(f"{BASE}/api/me/karten-app", json={}).status_code == 400,
             "und gar keine auch")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    for pfad, methode in (("/api/suche?q=grillen", requests.get),
                          ("/api/karten-apps", requests.get),
                          ("/api/me/karten-app", requests.post),
                          (f"/api/rooms/{runde}/messages?um=1", requests.get)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad.split('?')[0]} weist Fremde ab = {r.status_code}")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
