"""Die Vermittlung von Anrufen.

Bild und Ton laufen direkt zwischen den Geraeten - hier wird geprueft, was der
Server dazu beitraegt: wer mitmachen darf, wer davon erfaehrt und dass die
Aushandlungsdaten nur zwischen Beteiligten fliessen.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys
import time

from helpers import (BASE, Ergebnis, als_admin, anmelden, eigene_id,
                     verbindung, verbindungen_schliessen)


def horcher(sio, namen):
    """Sammelt die genannten Ereignisse in einer Liste."""
    empfangen = []
    for name in namen:
        sio.on(name, lambda daten, n=name: empfangen.append((n, daten)))
    return empfangen


def warte_auf(empfangen, name, sekunden=3.0):
    ende = time.time() + sekunden
    while time.time() < ende:
        for n, daten in empfangen:
            if n == name:
                return daten
        time.sleep(0.05)
    return None


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

    raum = admin.post(f"{BASE}/api/rooms", json={
        "name": "Runde", "is_group": True,
        "members": [ids["anna"], ids["bodo"]]}).json()["id"]

    s_admin = verbindung(admin)
    s_anna = verbindung(anna)
    s_bodo = verbindung(bodo)
    s_carla = verbindung(carla)
    e_admin = horcher(s_admin, ["anruf_stand", "anruf_neuer", "anruf_signal",
                                "anruf_weg", "anruf_abgelehnt"])
    e_anna = horcher(s_anna, ["anruf_stand", "anruf_neuer", "anruf_signal",
                              "anruf_weg", "anruf_abgelehnt"])
    e_carla = horcher(s_carla, ["anruf_stand", "anruf_signal"])
    time.sleep(0.4)

    # ------------------------------------------------------------------
    e.abschnitt("Die Vermittlungsserver")
    r = admin.get(f"{BASE}/api/anruf/server")
    e.pruefe(r.status_code == 200, f"werden ausgeliefert = {r.status_code}")
    daten = r.json()
    e.pruefe(isinstance(daten.get("iceServers"), list),
             "als Liste, so wie der Browser sie erwartet")
    e.pruefe(daten.get("max", 0) >= 2, f"mit einer Obergrenze = {daten.get('max')}")

    import requests
    e.pruefe(requests.get(f"{BASE}/api/anruf/server",
                          allow_redirects=False).status_code in (302, 401),
             "und nicht ohne Anmeldung")

    # ------------------------------------------------------------------
    e.abschnitt("Einen Anruf beginnen")
    antwort = s_admin.call("anruf_beitreten", {"room_id": raum, "art": "audio"},
                           timeout=6)
    e.pruefe(antwort and antwort.get("ok"), f"der Anruf startet = {antwort}")
    e.pruefe(antwort.get("bestehende") == [],
             "als Erster ist noch niemand da")
    stand = warte_auf(e_anna, "anruf_stand")
    e.pruefe(stand and stand["wer"] == [admin_id],
             f"Anna erfaehrt davon = {stand}")
    e.pruefe(stand and stand["art"] == "audio", "und um welche Art es geht")
    e.pruefe(warte_auf(e_carla, "anruf_stand", 0.6) is None,
             "Carla nicht - sie gehoert nicht zur Gruppe")

    r = anna.get(f"{BASE}/api/state").json()
    dieser = [x for x in r["rooms"] if x["id"] == raum][0]
    e.pruefe(dieser["anruf"] and dieser["anruf"]["wer"] == [admin_id],
             "der Startzustand nennt den laufenden Anruf")

    e.abschnitt("Dazukommen")
    e_admin.clear()
    antwort = s_anna.call("anruf_beitreten", {"room_id": raum, "art": "audio"},
                          timeout=6)
    e.pruefe(antwort and antwort.get("ok"), "Anna kommt dazu")
    e.pruefe(antwort.get("bestehende") == [admin_id],
             f"und erfaehrt, wer schon da ist = {antwort.get('bestehende')}")
    neuer = warte_auf(e_admin, "anruf_neuer")
    e.pruefe(neuer and neuer["user_id"] == ids["anna"],
             f"der Anwesende wird auf sie hingewiesen = {neuer}")

    e.abschnitt("Fremde bleiben draussen")
    antwort = s_carla.call("anruf_beitreten", {"room_id": raum}, timeout=6)
    e.pruefe(antwort and antwort.get("ok") is False,
             f"Carla kommt nicht hinein = {antwort}")

    e.abschnitt("Die Aushandlung wird weitergereicht")
    e_anna.clear()
    antwort = s_admin.call("anruf_signal", {
        "room_id": raum, "an": ids["anna"], "art": "angebot",
        "daten": {"sdp": "v=0 …", "type": "offer"}}, timeout=6)
    e.pruefe(antwort and antwort.get("ok"), "das Angebot wird angenommen")
    signal = warte_auf(e_anna, "anruf_signal")
    e.pruefe(signal and signal["von"] == admin_id, f"und kommt an = {signal}")
    e.pruefe(signal and signal["daten"]["type"] == "offer",
             "unveraendert - der Server ist nur Briefkasten")

    antwort = s_carla.call("anruf_signal", {
        "room_id": raum, "an": ids["anna"], "art": "angebot",
        "daten": {"sdp": "boese"}}, timeout=6)
    e.pruefe(antwort and antwort.get("ok") is False,
             f"wer nicht im Anruf sitzt, darf niemandem etwas schicken = {antwort}")
    e.pruefe(warte_auf(e_anna, "anruf_signal", 0.6) is None
             or len([x for x in e_anna if x[0] == "anruf_signal"]) == 1,
             "und es kommt auch nichts an")

    e_anna.clear()
    antwort = s_admin.call("anruf_signal", {
        "room_id": raum, "an": ids["carla"], "art": "angebot",
        "daten": {"sdp": "x"}}, timeout=6)
    e.pruefe(antwort and antwort.get("ok") is False,
             "an jemanden ausserhalb des Anrufs geht ebenfalls nichts")

    e.abschnitt("Ablehnen")
    e_admin.clear()
    s_bodo.call("anruf_ablehnen", {"room_id": raum}, timeout=6)
    abgelehnt = warte_auf(e_admin, "anruf_abgelehnt")
    e.pruefe(abgelehnt and abgelehnt["user_id"] == ids["bodo"],
             f"die anderen erfahren es = {abgelehnt}")

    e.abschnitt("Verlassen")
    e_admin.clear()
    s_anna.call("anruf_verlassen", {"room_id": raum}, timeout=6)
    weg = warte_auf(e_admin, "anruf_weg")
    e.pruefe(weg and weg["user_id"] == ids["anna"], f"Anna geht = {weg}")
    stand = warte_auf(e_admin, "anruf_stand")
    e.pruefe(stand and stand["wer"] == [admin_id],
             f"der Anruf laeuft mit dem Rest weiter = {stand}")

    e_anna.clear()
    s_admin.call("anruf_verlassen", {"room_id": raum}, timeout=6)
    stand = warte_auf(e_anna, "anruf_stand")
    e.pruefe(stand is not None and not stand.get("wer"),
             f"geht der Letzte, ist der Anruf vorbei = {stand}")
    dieser = [x for x in anna.get(f"{BASE}/api/state").json()["rooms"]
              if x["id"] == raum][0]
    e.pruefe(dieser["anruf"] is None, "und steht auch im Startzustand nicht mehr")

    e.abschnitt("Ein Videoanruf faerbt den ganzen Anruf")
    s_admin.call("anruf_beitreten", {"room_id": raum, "art": "audio"}, timeout=6)
    e_anna.clear()
    antwort = s_anna.call("anruf_beitreten", {"room_id": raum, "art": "video"},
                          timeout=6)
    e.pruefe(antwort and antwort.get("art") == "video",
             f"schaltet jemand die Kamera zu, gilt das fuer alle = {antwort}")

    e.abschnitt("Wer die Verbindung verliert, faellt heraus")
    e_admin.clear()
    s_anna.disconnect()
    weg = warte_auf(e_admin, "anruf_weg", 5.0)
    e.pruefe(weg and weg["user_id"] == ids["anna"],
             f"Annas Kachel bleibt nicht stehen = {weg}")

    s_admin.call("anruf_verlassen", {"room_id": raum}, timeout=6)

    e.abschnitt("Wer neu in die Gruppe kommt")
    # Ohne diese Meldung fehlt der Neue in der Mitgliederliste der anderen -
    # in einem laufenden Anruf stuende dann eine Kachel ohne Namen da.
    e_admin.clear()
    s_admin.on("room_changed", lambda d: e_admin.append(("room_changed", d)))
    r = admin.post(f"{BASE}/api/rooms/{raum}/members",
                   json={"user_id": ids["carla"]})
    e.pruefe(r.status_code == 200, f"Carla wird aufgenommen = {r.status_code}")
    geaendert = warte_auf(e_admin, "room_changed")
    e.pruefe(geaendert and geaendert["id"] == raum,
             f"die schon Anwesenden erfahren davon = {geaendert}")
    namen = [m["display_name"] for m in
             [x for x in admin.get(f"{BASE}/api/state").json()["rooms"]
              if x["id"] == raum][0]["members"]]
    e.pruefe("Carla" in namen, f"und finden sie in der Mitgliederliste = {namen}")

    e.abschnitt("Unfug")
    e.pruefe(s_admin.call("anruf_beitreten", {"room_id": "keiner"},
                          timeout=6).get("ok") is False,
             "ein unbrauchbarer Raum wird abgewiesen")
    e.pruefe(s_admin.call("anruf_beitreten", {"room_id": 9999},
                          timeout=6).get("ok") is False,
             "ein fremder ebenfalls")
    e.pruefe(s_admin.call("anruf_signal", {"room_id": raum, "an": "wer"},
                          timeout=6).get("ok") is False,
             "und ein Signal ohne Empfaenger auch")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
