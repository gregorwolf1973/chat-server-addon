"""Codenames - Teams, Lageplan, Hinweise, Zuege und das Ende.

Geprueft wird vor allem, was der Server niemandem verraten darf: die Farben
verdeckter Karten bekommen nur die Chefs.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys

import requests

from helpers import BASE, Ergebnis, als_admin, anmelden, eigene_id

HINWEIS = "Qwertzuiop"  # steht garantiert nicht auf dem Feld


def spiel(sitzung, spiel_id):
    return sitzung.get(f"{BASE}/api/spiele/{spiel_id}").json()


def lauf():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    namen = ("anna", "bodo", "carla", "dora")
    for name in namen:
        admin.post(f"{BASE}/api/users", json={
            "username": name, "display_name": name.capitalize(),
            "password": "test1234"})
    ids = {u["username"]: u["id"]
           for u in admin.get(f"{BASE}/api/state").json()["users"]}
    sitz = {"admin": admin}
    for name in namen:
        sitz[name] = anmelden(name, "test1234")[0]
    von_id = {admin_id: "admin", **{ids[n]: n for n in namen}}

    e.abschnitt("Der Wortvorrat")
    worte = admin.get(f"{BASE}/api/codenames-worte").json()["worte"]
    e.pruefe(len(worte) >= 400, f"reichlich Woerter = {len(worte)}")
    e.pruefe(all(" " not in w["wort"] for w in worte), "alles einzelne Woerter")

    e.abschnitt("Einladen braucht vier Leute")
    r = admin.post(f"{BASE}/api/spiele", json={
        "art": "codenames", "gaeste": [ids["anna"], ids["bodo"]]})
    e.pruefe(r.status_code == 400, f"zu dritt geht es nicht = {r.status_code}")
    r = admin.post(f"{BASE}/api/spiele", json={
        "art": "codenames", "gaeste": [ids[n] for n in namen]})
    e.pruefe(r.status_code == 200, f"zu fuenft schon = {r.status_code}")
    spiel_id = r.json()["id"]
    e.pruefe(r.json()["art"] == "codenames", "als Codenames angelegt")

    for n in ("anna", "bodo"):
        sitz[n].post(f"{BASE}/api/spiele/{spiel_id}/antwort", json={"antwort": "ja"})
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/start")
    e.pruefe(r.status_code == 400, "mit drei Zusagen lassen sich keine Teams bilden")
    sitz["carla"].post(f"{BASE}/api/spiele/{spiel_id}/antwort", json={"antwort": "ja"})

    e.abschnitt("Teams aufstellen")
    e.pruefe(sitz["anna"].post(f"{BASE}/api/spiele/{spiel_id}/start").status_code == 403,
             "das darf nur der Gastgeber")
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/start")
    e.pruefe(r.status_code == 200 and r.json()["status"] == "teams",
             f"die Teams stehen = {r.json().get('status')}")
    sp = r.json()
    teams = {t: [p for p in sp["spieler"] if p["team"] == t] for t in ("rot", "blau")}
    e.pruefe(len(teams["rot"]) == 2 and len(teams["blau"]) == 2,
             "zwei gegen zwei")
    e.pruefe(all(sum(p["chef"] for p in teams[t]) == 1 for t in teams),
             "jedes Team hat genau einen Chef")

    e.abschnitt("Wer jetzt noch zusagt, kommt gleich dazu")
    sitz["dora"].post(f"{BASE}/api/spiele/{spiel_id}/antwort", json={"antwort": "ja"})
    sp = spiel(admin, spiel_id)
    dabei = [p for p in sp["spieler"] if p["dabei"]]
    e.pruefe(len(dabei) == 5, f"Dora ist in einem Team = {len(dabei)} dabei")

    e.abschnitt("Umstellen vor dem Start")
    rot = [p for p in sp["spieler"] if p["team"] == "rot"]
    ohne_chef = next(p for p in rot if not p["chef"])
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/teams",
                   json={"aktion": "chef", "user_id": ohne_chef["id"]})
    rot = [p for p in r.json()["spieler"] if p["team"] == "rot"]
    e.pruefe([p["id"] for p in rot if p["chef"]] == [ohne_chef["id"]],
             "ein anderer wird Chef - und nur er")
    chef_rot = ohne_chef["id"]
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/teams",
                   json={"aktion": "tauschen", "user_id": chef_rot})
    sp = r.json()
    getauscht = next(p for p in sp["spieler"] if p["id"] == chef_rot)
    e.pruefe(getauscht["team"] == "blau" and not getauscht["chef"],
             "der Chef wechselt ins andere Team und ist dort Ermittler")
    e.pruefe(sum(p["chef"] for p in sp["spieler"] if p["team"] == "rot") == 1,
             "Rot bekommt einen neuen Chef")
    admin.post(f"{BASE}/api/spiele/{spiel_id}/teams", json={"aktion": "losen"})
    e.pruefe(sitz["anna"].post(f"{BASE}/api/spiele/{spiel_id}/teams",
                               json={"aktion": "losen"}).status_code == 403,
             "Mitspieler duerfen nicht umstellen")

    e.abschnitt("Zu kleines Team wird abgewiesen")
    sp = spiel(admin, spiel_id)
    klein = sorted(("rot", "blau"),
                   key=lambda t: sum(1 for p in sp["spieler"] if p["team"] == t))[0]
    for p in [p for p in sp["spieler"] if p["team"] == klein][:1]:
        admin.post(f"{BASE}/api/spiele/{spiel_id}/teams",
                   json={"aktion": "tauschen", "user_id": p["id"]})
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/los")
    e.pruefe(r.status_code == 400, f"ein Team mit einer Person startet nicht = {r.status_code}")
    admin.post(f"{BASE}/api/spiele/{spiel_id}/teams", json={"aktion": "losen"})

    e.abschnitt("Das Feld")
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/los")
    e.pruefe(r.status_code == 200, f"los geht's = {r.status_code}")
    sichten = {n: spiel(s, spiel_id) for n, s in sitz.items()}
    sp = sichten["admin"]
    e.pruefe(sp["status"] == "laeuft" and len(sp["karten"]) == 25, "25 Karten liegen")
    start = sp["am_zug"]
    e.pruefe(sp["offen"][start] == 9 and sp["offen"][
        "blau" if start == "rot" else "rot"] == 8,
        f"das Startteam hat neun Karten = {sp['offen']}")

    rollen = {}
    for p in sp["spieler"]:
        rollen[von_id[p["id"]]] = (p["team"], p["chef"])
    chef = {t: next(n for n, (tt, c) in rollen.items() if tt == t and c)
            for t in ("rot", "blau")}
    ermittler = {t: [n for n, (tt, c) in rollen.items() if tt == t and not c]
                 for t in ("rot", "blau")}

    plan = sichten[chef[start]]["karten"]
    e.pruefe(all(k["farbe"] for k in plan), "der Chef sieht alle Farben")
    farben = sorted(k["farbe"] for k in plan)
    e.pruefe(farben.count("neutral") == 7 and farben.count("attentaeter") == 1,
             "sieben neutrale, ein Attentaeter")
    blind = sichten[ermittler[start][0]]["karten"]
    e.pruefe(all(k["farbe"] is None for k in blind),
             "Ermittler sehen keine Farbe verdeckter Karten")

    e.abschnitt("Der Hinweis")
    gegner = "blau" if start == "rot" else "rot"
    s_chef, s_erm = sitz[chef[start]], sitz[ermittler[start][0]]
    e.pruefe(sitz[chef[gegner]].post(f"{BASE}/api/spiele/{spiel_id}/hinweis",
                                     json={"wort": HINWEIS, "zahl": 2}).status_code == 403,
             "der andere Chef ist nicht dran")
    e.pruefe(s_erm.post(f"{BASE}/api/spiele/{spiel_id}/hinweis",
                        json={"wort": HINWEIS, "zahl": 2}).status_code == 403,
             "ein Ermittler gibt keinen Hinweis")
    e.pruefe(s_erm.post(f"{BASE}/api/spiele/{spiel_id}/karte",
                        json={"pos": 0}).status_code == 400,
             "ohne Hinweis wird nichts aufgedeckt")
    e.pruefe(s_chef.post(f"{BASE}/api/spiele/{spiel_id}/hinweis",
                         json={"wort": plan[0]["wort"].upper(), "zahl": 1}).status_code == 400,
             "ein Wort vom Feld ist verboten, auch grossgeschrieben")
    e.pruefe(s_chef.post(f"{BASE}/api/spiele/{spiel_id}/hinweis",
                         json={"wort": "zwei Worte", "zahl": 1}).status_code == 400,
             "nur ein Wort")
    e.pruefe(s_chef.post(f"{BASE}/api/spiele/{spiel_id}/hinweis",
                         json={"wort": HINWEIS, "zahl": 12}).status_code == 400,
             "hoechstens neun")
    r = s_chef.post(f"{BASE}/api/spiele/{spiel_id}/hinweis",
                    json={"wort": HINWEIS, "zahl": 2})
    e.pruefe(r.status_code == 200 and r.json()["rest_versuche"] == 3,
             "zwei Karten gemeint - drei Versuche")

    e.abschnitt("Aufdecken")
    eigene = [k["pos"] for k in plan if k["farbe"] == start]
    neutral = [k["pos"] for k in plan if k["farbe"] == "neutral"]
    attentaeter = next(k["pos"] for k in plan if k["farbe"] == "attentaeter")
    e.pruefe(s_chef.post(f"{BASE}/api/spiele/{spiel_id}/karte",
                         json={"pos": eigene[0]}).status_code == 403,
             "der Chef deckt nichts auf")
    e.pruefe(sitz[ermittler[gegner][0]].post(f"{BASE}/api/spiele/{spiel_id}/karte",
                                             json={"pos": eigene[0]}).status_code == 403,
             "das andere Team ist nicht dran")
    e.pruefe(s_erm.post(f"{BASE}/api/spiele/{spiel_id}/passen").status_code == 400,
             "passen erst nach einer Karte")
    r = s_erm.post(f"{BASE}/api/spiele/{spiel_id}/karte", json={"pos": eigene[0]})
    sp = r.json()
    e.pruefe(sp["aufgedeckt"]["farbe"] == start, "ein Treffer")
    e.pruefe(sp["rest_versuche"] == 2 and sp["am_zug"] == start,
             "das Team bleibt dran, ein Versuch weniger")
    e.pruefe(sp["offen"][start] == 8, "eine Karte weniger zu finden")
    sichtbar = next(k for k in spiel(sitz[ermittler[gegner][0]], spiel_id)["karten"]
                    if k["pos"] == eigene[0])
    e.pruefe(sichtbar["farbe"] == start, "aufgedeckt sehen alle die Farbe")
    e.pruefe(s_erm.post(f"{BASE}/api/spiele/{spiel_id}/karte",
                        json={"pos": eigene[0]}).status_code == 400,
             "zweimal dieselbe Karte geht nicht")

    r = s_erm.post(f"{BASE}/api/spiele/{spiel_id}/karte", json={"pos": neutral[0]})
    sp = r.json()
    e.pruefe(sp["am_zug"] == gegner and sp["hinweis"] is None,
             "daneben - das andere Team ist dran")

    e.abschnitt("Passen")
    s_chef2, s_erm2 = sitz[chef[gegner]], sitz[ermittler[gegner][0]]
    plan2 = spiel(s_chef2, spiel_id)["karten"]
    eigene2 = [k["pos"] for k in plan2 if k["farbe"] == gegner and not k["aufgedeckt"]]
    s_chef2.post(f"{BASE}/api/spiele/{spiel_id}/hinweis", json={"wort": HINWEIS, "zahl": 3})
    s_erm2.post(f"{BASE}/api/spiele/{spiel_id}/karte", json={"pos": eigene2[0]})
    r = s_erm2.post(f"{BASE}/api/spiele/{spiel_id}/passen")
    e.pruefe(r.status_code == 200 and r.json()["am_zug"] == start,
             "nach einem Treffer darf das Team aufhoeren")
    verlauf = r.json()["hinweise"]
    e.pruefe(len(verlauf) == 2 and verlauf[0]["team"] == start,
             "die Hinweise stehen im Verlauf")

    e.abschnitt("Alle eigenen Karten gefunden")
    s_chef.post(f"{BASE}/api/spiele/{spiel_id}/hinweis", json={"wort": HINWEIS, "zahl": 9})
    for pos in eigene[1:]:
        sp = s_erm.post(f"{BASE}/api/spiele/{spiel_id}/karte", json={"pos": pos}).json()
    e.pruefe(sp["status"] == "vorbei" and sp["gewinner"] == start
             and sp["ergebnis"] == "alle", f"{start} gewinnt = {sp.get('gewinner')}")
    e.pruefe(all(k["farbe"] for k in spiel(s_erm2, spiel_id)["karten"]),
             "nach dem Ende sehen alle den ganzen Plan")

    e.abschnitt("Naechste Runde: Teams bleiben, der Chef wechselt")
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/start")
    sp = r.json()
    e.pruefe(sp["status"] == "teams" and sp["runde"] == 2, "Runde zwei wird aufgestellt")
    neu = {von_id[p["id"]]: (p["team"], p["chef"]) for p in sp["spieler"] if p["dabei"]}
    e.pruefe(all(neu[n][0] == rollen[n][0] for n in rollen), "alle bleiben im Team")
    e.pruefe(all(not neu[chef[t]][1] for t in chef), "die alten Chefs sind es nicht mehr")

    e.abschnitt("Der Attentaeter")
    admin.post(f"{BASE}/api/spiele/{spiel_id}/los")
    sp = spiel(admin, spiel_id)
    start = sp["am_zug"]
    gegner = "blau" if start == "rot" else "rot"
    leute = {von_id[p["id"]]: p for p in sp["spieler"] if p["dabei"]}
    c = next(n for n, p in leute.items() if p["team"] == start and p["chef"])
    m = next(n for n, p in leute.items() if p["team"] == start and not p["chef"])
    plan = spiel(sitz[c], spiel_id)["karten"]
    sitz[c].post(f"{BASE}/api/spiele/{spiel_id}/hinweis", json={"wort": HINWEIS, "zahl": 1})
    schwarz = next(k["pos"] for k in plan if k["farbe"] == "attentaeter")
    sp = sitz[m].post(f"{BASE}/api/spiele/{spiel_id}/karte", json={"pos": schwarz}).json()
    e.pruefe(sp["status"] == "vorbei" and sp["gewinner"] == gegner
             and sp["ergebnis"] == "attentaeter",
             f"wer den Attentaeter erwischt, verliert sofort = {sp.get('gewinner')}")

    e.abschnitt("Impostor-Aktionen gelten hier nicht")
    e.pruefe(admin.post(f"{BASE}/api/spiele/{spiel_id}/raten",
                        json={"wort": "x"}).status_code == 400, "kein Raten")
    e.pruefe(admin.post(f"{BASE}/api/spiele/{spiel_id}/bereit").status_code in (400, 403),
             "kein Bereit")

    e.abschnitt("Wortliste")
    erstes = worte[0]
    r = sitz["anna"].post(f"{BASE}/api/codenames-worte/{erstes['id']}/sperren",
                          json={"gesperrt": True})
    e.pruefe(r.status_code == 200, "jeder darf sperren")
    danach = sitz["bodo"].get(f"{BASE}/api/codenames-worte").json()["worte"]
    e.pruefe(next(w for w in danach if w["id"] == erstes["id"])["gesperrt"],
             "und es gilt fuer alle")
    e.pruefe(sitz["anna"].post(f"{BASE}/api/codenames-worte",
                               json={"wort": "Flaschengeist"}).status_code == 200,
             "ein eigenes Wort kommt dazu")
    e.pruefe(sitz["anna"].post(f"{BASE}/api/codenames-worte",
                               json={"wort": "FLASCHENGEIST"}).status_code == 400,
             "doppelt auch nicht in anderer Schreibweise")
    e.pruefe(sitz["anna"].post(f"{BASE}/api/codenames-worte",
                               json={"wort": "zwei Worte"}).status_code == 400,
             "nur einzelne Woerter")

    e.abschnitt("Beenden raeumt alles weg")
    e.pruefe(admin.delete(f"{BASE}/api/spiele/{spiel_id}").status_code == 200,
             "der Gastgeber beendet")
    e.pruefe(sitz["anna"].get(f"{BASE}/api/spiele").json()["spiele"] == [],
             "bei allen ist es weg")
    e.pruefe(admin.get(f"{BASE}/api/spiele/{spiel_id}").status_code == 403,
             "und nicht mehr abrufbar")

    e.abschnitt("Ohne Anmeldung geht nichts")
    fremde = requests.Session()
    for pfad, methode in (("/api/codenames-worte", fremde.get),
                          (f"/api/spiele/{spiel_id}/karte", fremde.post),
                          (f"/api/spiele/{spiel_id}/hinweis", fremde.post)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401), f"{pfad} weist Fremde ab = {r.status_code}")

    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
