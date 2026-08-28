"""Geburtstage und die Einwilligung bei der Registrierung.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import datetime
import os
import sys

import requests

from helpers import BASE, Ergebnis, als_admin, anmelden, eigene_id


def antrag(felder):
    s = requests.Session()
    return s.post(f"{BASE}/register", data=felder, allow_redirects=False)


def lauf():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    heute = datetime.date.today()

    e.abschnitt("Die Einwilligung ist Pflicht")
    grund = {"username": "ohnehaken", "display_name": "Ohne Haken",
             "password": "start123", "email": "a@b.de",
             "note": "Ich moechte mitlesen."}
    r = antrag(grund)
    e.pruefe(r.status_code == 200 and "Einverst" in r.text,
             f"ohne Haken kein Konto = {r.status_code}")
    e.pruefe(not any(u["username"] == "ohnehaken"
                     for u in admin.get(f"{BASE}/api/users").json()),
             "und das Konto entsteht auch nicht")

    e.abschnitt("Mit Haken und Geburtstag")
    r = antrag(dict(grund, username="anna", display_name="Anna",
                    zustimmung="on", geburtstag="1990-05-17"))
    e.pruefe(r.status_code in (200, 302), f"der Antrag geht durch = {r.status_code}")
    anna = next((u for u in admin.get(f"{BASE}/api/users").json()
                 if u["username"] == "anna"), None)
    e.pruefe(anna is not None, "das Konto ist da")
    e.pruefe(anna and anna.get("pending"), "und wartet auf Freigabe")

    e.abschnitt("Unbrauchbare Geburtstage")
    for wert, was in (("1990-13-45", "ein unmoegliches Datum"),
                      ((heute + datetime.timedelta(days=1)).isoformat(),
                       "ein Datum von morgen"),
                      ("1700-01-01", "ein Datum von vor 300 Jahren")):
        r = antrag(dict(grund, username=f"x{abs(hash(wert)) % 9999}",
                        zustimmung="on", geburtstag=wert))
        e.pruefe("Geburtsdatum" in r.text, f"{was} wird abgewiesen")

    r = antrag(dict(grund, username="ohnetag", display_name="Ohne Tag",
                    zustimmung="on", geburtstag=""))
    e.pruefe(r.status_code in (200, 302) and "Geburtsdatum" not in r.text,
             "ohne Angabe geht es trotzdem - sie ist freiwillig")

    e.abschnitt("Die Liste der Geburtstage")
    admin.post(f"{BASE}/api/users/{anna['id']}/approve")
    e.pruefe(len(admin.get(f"{BASE}/api/geburtstage").json()) == 0,
             "ohne gemeinsame Unterhaltung sieht der Admin Annas nicht")

    raum = admin.post(f"{BASE}/api/rooms", json={
        "is_group": False, "members": [anna["id"]]}).json()["id"]
    liste = admin.get(f"{BASE}/api/geburtstage").json()
    e.pruefe(len(liste) == 1, f"mit gemeinsamer Unterhaltung schon = {len(liste)}")
    g = liste[0]
    e.pruefe(g["name"] == "Anna", "mit ihrem Namen")
    e.pruefe(g["datum"] == "1990-05-17", "und dem Datum")
    naechster = datetime.date.fromisoformat(g["naechster"])
    e.pruefe(naechster >= heute, f"der naechste liegt nicht in der Vergangenheit"
                                 f" = {g['naechster']}")
    e.pruefe(naechster.month == 5 and naechster.day == 17, "und trifft den Tag")
    e.pruefe(g["wird"] == naechster.year - 1990,
             f"das Alter stimmt = wird {g['wird']}")

    e.abschnitt("Den eigenen Geburtstag setzen")
    r = admin.post(f"{BASE}/api/me/geburtstag", json={"geburtstag": "1972-02-29"})
    e.pruefe(r.status_code == 200, f"der 29. Februar wird angenommen = {r.status_code}")
    meiner = next((x for x in admin.get(f"{BASE}/api/geburtstage").json()
                   if x["ich"]), None)
    e.pruefe(meiner is not None, "und steht in der Liste")
    if meiner:
        d = datetime.date.fromisoformat(meiner["naechster"])
        schaltjahr = (d.year % 4 == 0 and d.year % 100 != 0) or d.year % 400 == 0
        e.pruefe((d.month == 2 and d.day == 29) if schaltjahr
                 else (d.month == 3 and d.day == 1),
                 f"in Jahren ohne Schalttag am 1. Maerz = {meiner['naechster']}")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["geburtstag"] == "1972-02-29",
             "der Startzustand nennt ihn")

    e.pruefe(admin.post(f"{BASE}/api/me/geburtstag",
                        json={"geburtstag": "morgen"}).status_code == 400,
             "Unfug wird abgewiesen")
    r = admin.post(f"{BASE}/api/me/geburtstag", json={"geburtstag": ""})
    e.pruefe(r.status_code == 200 and r.json()["geburtstag"] is None,
             "und loeschen geht auch")
    e.pruefe(not any(x["ich"] for x in admin.get(f"{BASE}/api/geburtstage").json()),
             "danach steht er nicht mehr in der Liste")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    for pfad, methode in (("/api/geburtstage", requests.get),
                          ("/api/me/geburtstag", requests.post)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad} weist Fremde ab = {r.status_code}")

    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
