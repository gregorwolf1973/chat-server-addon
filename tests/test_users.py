"""Benutzerverwaltung: Anlegen, Passwoerter, Sperren, Rechte, Loeschen."""
import os
import sys

import requests

from helpers import (BASE, Ergebnis, als_admin, anmelden, eigene_id,
                     senden, verbindungen_schliessen)


def patch(sitzung, uid, **felder):
    return sitzung.patch(f"{BASE}/api/users/{uid}", json=felder)


def main():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)

    e.abschnitt("Liste und Anlegen")
    r = admin.get(f"{BASE}/api/users")
    e.pruefe(r.status_code == 200, f"GET /api/users = {r.status_code}")
    e.pruefe("homeassistant" not in [u["username"] for u in r.json()],
             "das Bot-Konto taucht nicht in der Verwaltung auf")

    r = admin.post(f"{BASE}/api/users", json={"username": "Testine",
                                              "display_name": "Testine T",
                                              "password": "start123"})
    e.pruefe(r.status_code == 200, f"Konto anlegen = {r.status_code}")
    uid = r.json().get("id")
    e.pruefe(r.json().get("username") == "testine",
             "der Benutzername wird klein gespeichert")
    e.pruefe(admin.post(f"{BASE}/api/users",
                        json={"username": "kurz", "password": "abc"}).status_code == 400,
             "ein zu kurzes Passwort wird abgelehnt")
    e.pruefe(admin.post(f"{BASE}/api/users",
                        json={"username": "homeassistant",
                              "password": "start123"}).status_code == 400,
             "Systemnamen sind vergeben")

    e.abschnitt("Anmelden")
    _, code = anmelden("TESTINE", "start123")
    e.pruefe(code == 302, "die Schreibweise des Benutzernamens ist egal")

    e.abschnitt("Passwort zuruecksetzen")
    gast, _ = anmelden("testine", "start123")
    e.pruefe(gast.get(f"{BASE}/api/state").status_code == 200,
             "die Sitzung gilt vor dem Zuruecksetzen")
    r = admin.post(f"{BASE}/api/users/{uid}/password", json={"password": "neu12345"})
    e.pruefe(r.status_code == 200, f"Zuruecksetzen = {r.status_code}")
    e.pruefe(gast.get(f"{BASE}/api/state").status_code == 401,
             "die alte Sitzung ist sofort ungueltig")
    e.pruefe(anmelden("testine", "start123")[1] == 200,
             "das alte Passwort oeffnet nichts mehr")
    e.pruefe(anmelden("testine", "neu12345")[1] == 302,
             "das neue Passwort funktioniert")
    e.pruefe(admin.post(f"{BASE}/api/users/{uid}/password",
                        json={"password": "kurz"}).status_code == 400,
             "auch beim Zuruecksetzen gilt die Mindestlaenge")
    e.pruefe(admin.get(f"{BASE}/api/state").status_code == 200,
             "die eigene Sitzung ueberlebt fremde Zuruecksetzungen")

    e.abschnitt("Sperren und entsperren")
    gast, _ = anmelden("testine", "neu12345")
    r = patch(admin, uid, active=False)
    e.pruefe(r.status_code == 200 and r.json()["active"] is False,
             f"Sperren = {r.status_code}")
    e.pruefe(gast.get(f"{BASE}/api/state").status_code == 401,
             "die laufende Sitzung endet sofort")
    e.pruefe(anmelden("testine", "neu12345")[1] == 200,
             "ein gesperrtes Konto kommt nicht mehr hinein")
    e.pruefe(any(u["id"] == uid and not u["active"]
                 for u in admin.get(f"{BASE}/api/state").json()["users"]),
             "die Sperre ist in der Oberflaeche sichtbar")
    e.pruefe(patch(admin, uid, active=True).status_code == 200, "Entsperren")
    e.pruefe(anmelden("testine", "neu12345")[1] == 302,
             "danach geht die Anmeldung wieder")

    e.abschnitt("Rechte")
    e.pruefe(patch(admin, uid, is_admin=True).json()["is_admin"],
             "zum Administrator machen")
    gast, _ = anmelden("testine", "neu12345")
    e.pruefe(gast.get(f"{BASE}/api/users").status_code == 200,
             "der neue Administrator darf die Verwaltung sehen")
    e.pruefe(not patch(admin, uid, is_admin=False).json()["is_admin"],
             "Administratorrecht entziehen")
    e.pruefe(gast.get(f"{BASE}/api/users").status_code == 403,
             "danach ist die Verwaltung wieder zu")
    e.pruefe(gast.delete(f"{BASE}/api/users/{uid}").status_code == 403,
             "und Loeschen erst recht")

    e.abschnitt("Niemand sperrt sich selbst aus")
    e.pruefe(patch(admin, admin_id, active=False).status_code == 400,
             "das eigene Konto sperren")
    e.pruefe(patch(admin, admin_id, is_admin=False).status_code == 400,
             "die eigenen Rechte abgeben")
    e.pruefe(admin.delete(f"{BASE}/api/users/{admin_id}").status_code == 400,
             "das eigene Konto loeschen")
    e.pruefe(patch(admin, 99999, active=False).status_code == 404,
             "ein unbekanntes Konto ergibt 404")

    e.abschnitt("Loeschen erhaelt den Verlauf")
    raum = gast.post(f"{BASE}/api/rooms",
                     json={"is_group": False, "members": [admin_id]}).json()["id"]
    senden(gast, raum, "Bleibt das stehen?")
    e.pruefe(any(m["body"] == "Bleibt das stehen?"
                 for m in admin.get(f"{BASE}/api/rooms/{raum}/messages").json()),
             "die Nachricht ist da")
    e.pruefe(admin.delete(f"{BASE}/api/users/{uid}").status_code == 200,
             "Konto loeschen")
    treffer = [m for m in admin.get(f"{BASE}/api/rooms/{raum}/messages").json()
               if m["body"] == "Bleibt das stehen?"]
    e.pruefe(len(treffer) == 1, "die Nachricht steht weiterhin im Verlauf")
    e.pruefe(treffer and treffer[0]["author"] == "Geloeschtes Konto",
             f"als Absender steht dort {treffer[0]['author']!r}" if treffer
             else "kein Absender zu pruefen")
    e.pruefe(anmelden("testine", "neu12345")[1] == 200,
             "das geloeschte Konto kommt nicht mehr hinein")
    namen = [u["username"] for u in admin.get(f"{BASE}/api/users").json()]
    e.pruefe("testine" not in namen and "geloeschtes-konto" not in namen,
             f"die Liste ist aufgeraeumt: {namen}")

    verbindungen_schliessen()
    e.abschnitt("Name der Oberflaeche")
    # Ein gewoehnliches Konto, um die Rechte zu pruefen
    admin.post(f"{BASE}/api/users", json={"username": "leser",
                                          "display_name": "Leser",
                                          "password": "start123"})
    anna, _ = anmelden("leser", "start123")
    r = admin.get(f"{BASE}/api/anzeigename")
    e.pruefe(r.status_code == 200, f"laesst sich lesen = {r.status_code}")
    e.pruefe(r.json()["name"] == "Chat",
             f"voreingestellt = {r.json()['name']}")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["anzeigename"] == "Chat",
             "und steht im Startzustand")
    r = admin.post(f"{BASE}/api/anzeigename", json={"name": "Nachbarschaft"})
    e.pruefe(r.status_code == 200 and r.json()["name"] == "Nachbarschaft",
             f"der Administrator kann ihn aendern = {r.status_code}")
    e.pruefe(anna.get(f"{BASE}/api/state").json()["anzeigename"] == "Nachbarschaft",
             "Anna sieht denselben Namen - er gilt fuer alle")
    e.pruefe(anna.post(f"{BASE}/api/anzeigename",
                       json={"name": "Annas Bude"}).status_code == 403,
             "aendern darf ihn nur, wer Administrator ist")
    e.pruefe(anna.get(f"{BASE}/api/anzeigename").status_code == 200,
             "lesen darf ihn jeder")
    e.pruefe(admin.post(f"{BASE}/api/anzeigename",
                        json={"name": "x" * 41}).status_code == 400,
             "zu lang wird abgewiesen")
    r = admin.post(f"{BASE}/api/anzeigename", json={"name": "   "})
    e.pruefe(r.json()["name"] == "Chat",
             "leer heisst zurueck zur Voreinstellung")
    e.pruefe(requests.post(f"{BASE}/api/anzeigename", json={},
                           allow_redirects=False).status_code in (302, 401),
             "ohne Anmeldung geht gar nichts")

    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    # Der Socket.IO-Client haelt Hintergrundthreads am Leben, die den Prozess
    # sonst nach dem letzten Test nicht enden lassen.
    os._exit(ergebnis)
