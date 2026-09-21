"""Impostor - Einladung, Runde, Raten und das Ende.

Geprueft wird vor allem, was der Server niemandem verraten darf: der Impostor
sieht das Wort nie, und wer Impostor ist, steht erst in der Auswertung drin.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys
import time

import requests

from helpers import BASE, Ergebnis, als_admin, anmelden, eigene_id


def spiel(sitzung, spiel_id):
    return sitzung.get(f"{BASE}/api/spiele/{spiel_id}").json()


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
    anna = anmelden("anna", "test1234")[0]
    bodo = anmelden("bodo", "test1234")[0]
    carla = anmelden("carla", "test1234")[0]

    e.abschnitt("Der Wortvorrat steht bereit")
    worte = admin.get(f"{BASE}/api/spiel-worte").json()
    e.pruefe(len(worte["worte"]) > 100,
             f"es gibt reichlich Woerter = {len(worte['worte'])}")
    e.pruefe(len(worte["kategorien"]) >= 8,
             f"in mehreren Kategorien = {len(worte['kategorien'])}")
    e.pruefe(all(w["tipp"] for w in worte["worte"]),
             "jedes Wort hat einen Tipp fuer den Impostor")

    e.abschnitt("Einladen")
    r = admin.post(f"{BASE}/api/spiele", json={"gaeste": [ids["anna"]]})
    e.pruefe(r.status_code == 400, f"zu zweit geht es nicht = {r.status_code}")

    r = admin.post(f"{BASE}/api/spiele", json={
        "gaeste": [ids["anna"], ids["bodo"], ids["carla"]],
        "kategorien": ["sport", "musik"], "impostoren": 1,
        "dauer_s": 120, "versuche": 2})
    e.pruefe(r.status_code == 200, f"zu viert schon = {r.status_code}")
    sp = r.json()
    spiel_id = sp["id"]
    e.pruefe(sp["status"] == "einladung", f"Status = {sp['status']}")
    e.pruefe(sp["bin_gastgeber"] is True, "der Einladende ist Gastgeber")
    e.pruefe(sp["meine_antwort"] == "ja", "er selbst ist gesetzt")
    e.pruefe(len(sp["spieler"]) == 4, "vier Leute stehen auf der Liste")
    e.pruefe(sp["versuche"] == 2 and sp["dauer_s"] == 120,
             "die Einstellungen sind uebernommen")

    e.pruefe(admin.post(f"{BASE}/api/spiele", json={
        "gaeste": [ids["anna"], ids["bodo"], ids["carla"]]}).status_code == 400,
        "ein zweites Spiel nebenher geht nicht")

    fremde = requests.Session()
    e.pruefe(spiel(anna, spiel_id)["id"] == spiel_id, "Eingeladene sehen das Spiel")

    e.abschnitt("Zusagen und absagen")
    anna.post(f"{BASE}/api/spiele/{spiel_id}/antwort", json={"antwort": "ja"})
    bodo.post(f"{BASE}/api/spiele/{spiel_id}/antwort", json={"antwort": "ja"})
    carla.post(f"{BASE}/api/spiele/{spiel_id}/antwort", json={"antwort": "nein"})
    sp = spiel(admin, spiel_id)
    zusagen = [p for p in sp["spieler"] if p["antwort"] == "ja"]
    e.pruefe(len(zusagen) == 3, f"drei haben zugesagt = {len(zusagen)}")

    e.pruefe(anna.post(f"{BASE}/api/spiele/{spiel_id}/start").status_code == 403,
             "starten darf nur der Gastgeber")

    e.abschnitt("Die Runde beginnt")
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/start")
    e.pruefe(r.status_code == 200, f"der Gastgeber startet = {r.status_code}")
    sp = r.json()
    e.pruefe(sp["status"] == "zeigen", f"jetzt wird gelesen = {sp['status']}")
    e.pruefe(sp["runde"] == 1, "es ist die erste Runde")

    sichten = {"admin": spiel(admin, spiel_id), "anna": spiel(anna, spiel_id),
               "bodo": spiel(bodo, spiel_id), "carla": spiel(carla, spiel_id)}
    dabei = [n for n, s in sichten.items() if s["ich_dabei"]]
    e.pruefe(sorted(dabei) == ["admin", "anna", "bodo"],
             f"nur die Zusagenden sind dabei = {sorted(dabei)}")
    e.pruefe(sichten["carla"]["ich_dabei"] is False,
             "wer abgesagt hat, spielt nicht mit")

    impostoren = [n for n in dabei if sichten[n]["bin_impostor"]]
    e.pruefe(len(impostoren) == 1, f"es gibt genau einen Impostor = {len(impostoren)}")
    imp = impostoren[0]
    unschuldig = [n for n in dabei if n != imp]
    e.pruefe("mein_wort" not in sichten[imp],
             "der Impostor bekommt das Wort nicht zu sehen")
    e.pruefe("wort" not in sichten[imp], "auch nicht ueber die Auswertung")
    e.pruefe(bool(sichten[imp].get("mein_tipp")), "er bekommt einen Tipp")
    woerter = {sichten[n].get("mein_wort") for n in unschuldig}
    e.pruefe(len(woerter) == 1 and all(woerter),
             f"alle anderen haben dasselbe Wort = {woerter}")
    wort = woerter.pop()
    e.pruefe(all(p["impostor"] is None
                 for n in dabei for p in sichten[n]["spieler"]),
             "wer Impostor ist, steht waehrend des Spiels bei niemandem")

    plaetze = {p["name"]: p["platz"] for p in sichten["admin"]["spieler"] if p["dabei"]}
    e.pruefe(sorted(plaetze.values()) == [1, 2, 3],
             f"jeder hat einen Platz = {sorted(plaetze.values())}")
    imp_name = {"admin": "admin", "anna": "Anna", "bodo": "Bodo"}[imp]
    e.pruefe(plaetze[imp_name] >= 2,
             f"der Impostor ist nicht als Erster dran = Platz {plaetze[imp_name]}")

    e.abschnitt("Erst wenn alle bereit sind, laeuft die Uhr")
    e.pruefe(carla.post(f"{BASE}/api/spiele/{spiel_id}/bereit").status_code == 403,
             "wer nicht mitspielt, bestaetigt auch nichts")
    admin.post(f"{BASE}/api/spiele/{spiel_id}/bereit")
    anna.post(f"{BASE}/api/spiele/{spiel_id}/bereit")
    e.pruefe(spiel(admin, spiel_id)["status"] == "zeigen",
             "solange einer fehlt, wartet das Spiel")
    r = bodo.post(f"{BASE}/api/spiele/{spiel_id}/bereit")
    sp = r.json()
    e.pruefe(sp["status"] == "laeuft", f"dann geht es los = {sp['status']}")
    e.pruefe(sp["rest_s"] and sp["rest_s"] > 100,
             f"die Uhr steht auf zwei Minuten = {sp['rest_s']}")

    e.abschnitt("Raten darf nur der Impostor")
    sitzungen = {"admin": admin, "anna": anna, "bodo": bodo, "carla": carla}
    ahnungslos = sitzungen[unschuldig[0]]
    e.pruefe(ahnungslos.post(f"{BASE}/api/spiele/{spiel_id}/raten",
                             json={"wort": wort}).status_code == 403,
             "wer das Wort kennt, darf nicht raten")

    r = sitzungen[imp].post(f"{BASE}/api/spiele/{spiel_id}/raten",
                            json={"wort": "Kaeseigel"})
    e.pruefe(r.status_code == 200 and r.json()["treffer"] is False,
             "ein falscher Versuch wird abgelehnt")
    e.pruefe(r.json()["status"] == "laeuft",
             "beim ersten von zwei Versuchen laeuft es weiter")

    r = sitzungen[imp].post(f"{BASE}/api/spiele/{spiel_id}/raten",
                            json={"wort": wort.upper()})
    e.pruefe(r.json()["treffer"] is True,
             "Grossschreibung ist egal - das Wort zaehlt")
    sp = r.json()
    e.pruefe(sp["status"] == "vorbei" and sp["ergebnis"] == "erraten",
             f"der Impostor gewinnt = {sp['ergebnis']}")
    e.pruefe(sp["wort"] == wort, "jetzt steht das Wort in der Auswertung")
    nach = spiel(ahnungslos, spiel_id)
    verraten = [p["name"] for p in nach["spieler"] if p["impostor"]]
    e.pruefe(verraten == [imp_name],
             f"und alle erfahren, wer es war = {verraten}")

    e.abschnitt("Naechste Runde - wer inzwischen zusagt, ist dabei")
    carla.post(f"{BASE}/api/spiele/{spiel_id}/antwort", json={"antwort": "ja"})
    r = admin.post(f"{BASE}/api/spiele/{spiel_id}/start")
    e.pruefe(r.status_code == 200, f"die naechste Runde startet = {r.status_code}")
    sp = r.json()
    e.pruefe(sp["runde"] == 2, "es ist Runde zwei")
    e.pruefe(spiel(carla, spiel_id)["ich_dabei"] is True,
             "Carla spielt jetzt mit")
    e.pruefe(len([p for p in sp["spieler"] if p["dabei"]]) == 4,
             "die Runde hat vier Leute")

    e.abschnitt("Wenn die Zeit ablaeuft, verliert der Impostor")
    admin.delete(f"{BASE}/api/spiele/{spiel_id}")
    r = admin.post(f"{BASE}/api/spiele", json={
        "gaeste": [ids["anna"], ids["bodo"]], "dauer_s": 30, "versuche": 1})
    kurz_id = r.json()["id"]
    anna.post(f"{BASE}/api/spiele/{kurz_id}/antwort", json={"antwort": "ja"})
    bodo.post(f"{BASE}/api/spiele/{kurz_id}/antwort", json={"antwort": "ja"})
    admin.post(f"{BASE}/api/spiele/{kurz_id}/start")
    for s in (admin, anna, bodo):
        s.post(f"{BASE}/api/spiele/{kurz_id}/bereit")
    # Die kuerzeste erlaubte Spielzeit sind 30 Sekunden - die werden hier
    # wirklich abgewartet. Der Server stellt den Ablauf beim Nachsehen fest,
    # nicht mit einem Wecker; genau das wird damit geprueft.
    e.pruefe(spiel(admin, kurz_id)["status"] == "laeuft", "die Uhr laeuft")
    time.sleep(32)
    sp = spiel(admin, kurz_id)
    e.pruefe(sp["status"] == "vorbei" and sp["ergebnis"] == "zeit_um",
             f"nach dem Alarm ist Schluss = {sp['ergebnis']}")
    e.pruefe(bool(sp.get("wort")), "das Wort wird aufgeloest")

    e.abschnitt("Wortliste pflegen")
    erstes = worte["worte"][0]
    r = anna.post(f"{BASE}/api/spiel-worte/{erstes['id']}/sperren",
                  json={"gesperrt": True})
    e.pruefe(r.status_code == 200, f"jeder darf sperren = {r.status_code}")
    danach = bodo.get(f"{BASE}/api/spiel-worte").json()
    gesperrt = next(w for w in danach["worte"] if w["id"] == erstes["id"])
    e.pruefe(gesperrt["gesperrt"] is True, "und es gilt fuer alle")

    r = anna.post(f"{BASE}/api/spiel-worte",
                  json={"kategorie": "sport", "wort": "Eisstockschiessen",
                        "tipp": "Winter, und es rutscht."})
    e.pruefe(r.status_code == 200, f"ein eigenes Wort kommt dazu = {r.status_code}")
    e.pruefe(anna.post(f"{BASE}/api/spiel-worte",
                       json={"kategorie": "sport", "wort": "Eisstockschiessen",
                             "tipp": "nochmal"}).status_code == 400,
             "zweimal dasselbe nicht")
    e.pruefe(anna.post(f"{BASE}/api/spiel-worte",
                       json={"kategorie": "sport", "wort": "Ohne Tipp",
                             "tipp": ""}).status_code == 400,
             "und ohne Tipp auch nicht")

    e.abschnitt("Beenden raeumt alles weg")
    e.pruefe(anna.delete(f"{BASE}/api/spiele/{kurz_id}").status_code == 403,
             "beenden darf nur der Gastgeber")
    e.pruefe(admin.delete(f"{BASE}/api/spiele/{kurz_id}").status_code == 200,
             "der Gastgeber beendet")
    e.pruefe(admin.get(f"{BASE}/api/spiele").json()["spiele"] == [],
             "danach ist die Liste leer")
    e.pruefe(anna.get(f"{BASE}/api/spiele").json()["spiele"] == [],
             "auch bei den Eingeladenen")

    e.abschnitt("Ohne Anmeldung geht nichts")
    for pfad, methode in (("/api/spiele", fremde.get),
                          ("/api/spiel-worte", fremde.get),
                          ("/api/spiele", fremde.post)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad} weist Fremde ab = {r.status_code}")

    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
