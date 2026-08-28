"""Termine, Live-Standort und Stimmung.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR - siehe
tests/README.md.
"""
import os
import sys
import time

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, verbindungen_schliessen)


def konto_anlegen(admin, name, passwort="test1234"):
    r = admin.post(f"{BASE}/api/users", json={
        "username": name, "display_name": name.capitalize(),
        "password": passwort})
    return r.json().get("id") if r.status_code < 300 else None


def lauf():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)

    anna_id = konto_anlegen(admin, "anna")
    bodo_id = konto_anlegen(admin, "bodo")
    anna, code = anmelden("anna", "test1234")
    assert code == 302, "Anna kam nicht hinein"
    bodo, code = anmelden("bodo", "test1234")
    assert code == 302, "Bodo kam nicht hinein"

    # Gruppe mit Admin und Anna. Bodo bleibt draussen - er ist die Kontrolle.
    raum = admin.post(f"{BASE}/api/rooms", json={
        "name": "Grillrunde", "is_group": True,
        "members": [anna_id]}).json()["id"]

    # ------------------------------------------------------------------
    e.abschnitt("Einen Termin anlegen")
    r = admin.post(f"{BASE}/api/rooms/{raum}/event", json={
        "titel": "Grillen im Garten",
        "beschreibung": "Bringt Salat mit.",
        "ort_text": "Bei Gregor",
        "beginnt_at": int(time.time()) + 86400,
        "kategorien": ["essen", "musik", "quatsch"],
        "lat": 49.01, "lon": 8.40})
    e.pruefe(r.status_code == 200, f"der Termin wird angelegt = {r.status_code}")
    event_id = r.json().get("event_id")
    e.pruefe(bool(event_id), "und traegt eine Kennung")

    ev = admin.get(f"{BASE}/api/events/{event_id}").json()
    e.pruefe(ev["titel"] == "Grillen im Garten", "der Titel steht drin")
    e.pruefe(ev["kategorien"] == ["essen", "musik"],
             f"nur bekannte Merkmale bleiben = {ev['kategorien']}")
    e.pruefe(ev["ort"] and abs(ev["ort"]["lat"] - 49.01) < 0.001,
             "der Ort ist gespeichert")
    e.pruefe(ev["meine"] == "ja", "wer einlaedt, ist automatisch dabei")
    e.pruefe(len(ev["wer"]["ja"]) == 1, "und steht als einzige Zusage da")

    r = admin.post(f"{BASE}/api/rooms/{raum}/event", json={"titel": "  "})
    e.pruefe(r.status_code == 400, f"ohne Titel geht es nicht = {r.status_code}")

    e.abschnitt("Der Termin erscheint im Verlauf")
    msgs = admin.get(f"{BASE}/api/rooms/{raum}/messages").json()
    treffer = [m for m in msgs if m.get("event")]
    e.pruefe(len(treffer) == 1, f"genau eine Nachricht traegt ihn = {len(treffer)}")
    e.pruefe(treffer and treffer[0]["event"]["titel"] == "Grillen im Garten",
             "mit dem richtigen Titel")

    # ------------------------------------------------------------------
    e.abschnitt("Zu- und absagen")
    r = anna.post(f"{BASE}/api/events/{event_id}/antwort", json={"antwort": "ja"})
    e.pruefe(r.status_code == 200, f"Anna sagt zu = {r.status_code}")
    e.pruefe(len(r.json()["wer"]["ja"]) == 2, "jetzt sind es zwei Zusagen")

    r = anna.post(f"{BASE}/api/events/{event_id}/antwort",
                  json={"antwort": "vielleicht"})
    daten = r.json()
    e.pruefe(daten["meine"] == "vielleicht", "sie kann ihre Antwort aendern")
    e.pruefe(len(daten["wer"]["ja"]) == 1,
             f"und zaehlt nicht mehr als Zusage = {len(daten['wer']['ja'])}")

    r = anna.post(f"{BASE}/api/events/{event_id}/antwort", json={"antwort": ""})
    e.pruefe(r.json()["meine"] == "", "die Antwort laesst sich zuruecknehmen")

    r = anna.post(f"{BASE}/api/events/{event_id}/antwort",
                  json={"antwort": "villeicht"})
    e.pruefe(r.status_code == 400, f"Unfug wird abgewiesen = {r.status_code}")

    e.abschnitt("Fremde bleiben draussen")
    e.pruefe(bodo.get(f"{BASE}/api/events/{event_id}").status_code == 403,
             "Bodo sieht den Termin nicht")
    e.pruefe(bodo.post(f"{BASE}/api/events/{event_id}/antwort",
                       json={"antwort": "ja"}).status_code == 403,
             "und kann auch nicht zusagen")
    e.pruefe(len(bodo.get(f"{BASE}/api/events").json()) == 0,
             "seine Terminliste bleibt leer")

    e.abschnitt("Die Terminliste")
    liste = anna.get(f"{BASE}/api/events").json()
    e.pruefe(len(liste) == 1, f"Anna sieht den Termin = {len(liste)}")

    # Ein Termin von vorgestern gehoert nicht mehr hinein
    admin.post(f"{BASE}/api/rooms/{raum}/event", json={
        "titel": "War mal", "beginnt_at": int(time.time()) - 3 * 86400})
    titel = [x["titel"] for x in anna.get(f"{BASE}/api/events").json()]
    e.pruefe("War mal" not in titel, f"Vergangenes faellt heraus = {titel}")

    e.abschnitt("Absagen darf nur, wer eingeladen hat")
    e.pruefe(anna.delete(f"{BASE}/api/events/{event_id}").status_code == 403,
             "Anna kann den Termin nicht absagen")
    e.pruefe(admin.delete(f"{BASE}/api/events/{event_id}").status_code == 200,
             "der Gastgeber schon")
    ev = admin.get(f"{BASE}/api/events/{event_id}").json()
    e.pruefe(ev["abgesagt"] is True, "er ist als abgesagt vermerkt")
    e.pruefe(anna.post(f"{BASE}/api/events/{event_id}/antwort",
                       json={"antwort": "ja"}).status_code == 400,
             "und nimmt keine Zusagen mehr an")

    e.abschnitt("Das Bild einer Einladung")
    datei = hochladen(admin, "einladung.png", PNG, "image/png").json()["id"]
    r = admin.post(f"{BASE}/api/rooms/{raum}/event",
                   json={"titel": "Mit Bild", "file_id": datei})
    mit_bild = r.json()["event_id"]
    e.pruefe(admin.get(f"{BASE}/api/events/{mit_bild}").json()["file_id"] == datei,
             "es haengt am Termin")
    e.pruefe(anna.get(f"{BASE}/files/{datei}").status_code == 200,
             "Anna darf es sehen, obwohl keine Nachricht daran haengt")
    e.pruefe(bodo.get(f"{BASE}/files/{datei}").status_code == 403,
             "Bodo nicht")

    fremd = hochladen(bodo, "fremd.png", PNG, "image/png").json()["id"]
    r = admin.post(f"{BASE}/api/rooms/{raum}/event",
                   json={"titel": "Geklaut", "file_id": fremd})
    e.pruefe(admin.get(f"{BASE}/api/events/{r.json()['event_id']}")
             .json()["file_id"] is None,
             "eine fremde Datei laesst sich nicht einhaengen")

    # ------------------------------------------------------------------
    e.abschnitt("Live-Standort")
    r = admin.post(f"{BASE}/api/live", json={
        "room_id": raum, "lat": 49.0, "lon": 8.4, "minuten": 30})
    e.pruefe(r.status_code == 200, f"die Freigabe startet = {r.status_code}")
    e.pruefe(r.json()["bis_at"] > int(time.time()) + 1700, "und laeuft 30 Minuten")

    sicht = anna.get(f"{BASE}/api/live").json()
    e.pruefe(len(sicht) == 1, f"Anna sieht sie = {len(sicht)}")
    e.pruefe(sicht and sicht[0]["user_id"] == admin_id, "und weiss, von wem")
    e.pruefe(sicht and sicht[0]["ich"] is False, "als fremde Freigabe")
    e.pruefe(len(bodo.get(f"{BASE}/api/live").json()) == 0,
             "Bodo sieht nichts - er ist nicht in der Gruppe")

    r = admin.post(f"{BASE}/api/live", json={
        "room_id": raum, "lat": 200, "lon": 8.4, "minuten": 30})
    e.pruefe(r.status_code == 400, f"unsinnige Koordinaten prallen ab = {r.status_code}")

    r = bodo.post(f"{BASE}/api/live", json={
        "room_id": raum, "lat": 49.0, "lon": 8.4})
    e.pruefe(r.status_code == 403,
             f"in fremden Unterhaltungen darf man nicht teilen = {r.status_code}")

    r = admin.post(f"{BASE}/api/live", json={
        "room_id": raum, "lat": 49.0, "lon": 8.4, "minuten": 99999})
    e.pruefe(r.json()["bis_at"] - int(time.time()) <= 8 * 3600 + 5,
             "die Dauer ist bei acht Stunden gedeckelt")

    admin.post(f"{BASE}/api/live/ping", json={"lat": 50.5, "lon": 9.5})
    sicht = anna.get(f"{BASE}/api/live").json()
    e.pruefe(sicht and abs(sicht[0]["lat"] - 50.5) < 0.001,
             "der Ping schiebt die Position nach")

    r = bodo.post(f"{BASE}/api/live/ping", json={"lat": 50.5, "lon": 9.5})
    e.pruefe(r.json()["aktiv"] == 0,
             "ohne eigene Freigabe bewirkt der Ping nichts")

    e.pruefe(admin.get(f"{BASE}/api/state").json()["live"],
             "der Startzustand bringt die Freigaben gleich mit")

    r = admin.delete(f"{BASE}/api/live", json={})
    e.pruefe(r.status_code == 200, f"die Freigabe endet = {r.status_code}")
    e.pruefe(len(anna.get(f"{BASE}/api/live").json()) == 0,
             "und ist sofort verschwunden")

    e.abschnitt("Wer die Gruppe verlaesst, teilt dort nicht weiter")
    anna.post(f"{BASE}/api/live", json={"room_id": raum, "lat": 49.0, "lon": 8.4})
    e.pruefe(len(admin.get(f"{BASE}/api/live").json()) == 1, "Anna teilt")
    anna.post(f"{BASE}/api/rooms/{raum}/leave")
    e.pruefe(len(admin.get(f"{BASE}/api/live").json()) == 0,
             "nach dem Verlassen ist die Freigabe weg")

    # ------------------------------------------------------------------
    e.abschnitt("Stimmung")
    # Anna ist raus aus der Gruppe, also legen wir einen Direktchat an -
    # damit teilen Admin und Anna wieder eine Unterhaltung.
    admin.post(f"{BASE}/api/rooms", json={"is_group": False, "members": [anna_id]})

    r = admin.post(f"{BASE}/api/stimmung", json={
        "emoji": "🎬", "text": "Heute Abend Kino", "stunden": 3})
    e.pruefe(r.status_code == 200, f"die Meldung wird gesetzt = {r.status_code}")
    stimmung_id = r.json()["id"]
    e.pruefe(r.json()["text"] == "Heute Abend Kino", "mit dem richtigen Text")

    e.pruefe(admin.post(f"{BASE}/api/stimmung",
                        json={"text": "  "}).status_code == 400,
             "ohne Text geht es nicht")

    sicht = anna.get(f"{BASE}/api/stimmung").json()
    e.pruefe(len(sicht) == 1, f"Anna sieht sie = {len(sicht)}")
    e.pruefe(len(bodo.get(f"{BASE}/api/stimmung").json()) == 0,
             "Bodo nicht - er teilt keine Unterhaltung mit dem Admin")

    r = anna.post(f"{BASE}/api/stimmung/{stimmung_id}/mit")
    e.pruefe(r.status_code == 200 and r.json()["ich_mache_mit"] is True,
             "Anna macht mit")
    r = anna.post(f"{BASE}/api/stimmung/{stimmung_id}/mit")
    e.pruefe(r.json()["ich_mache_mit"] is False,
             "noch einmal tippen nimmt es zurueck")
    e.pruefe(bodo.post(f"{BASE}/api/stimmung/{stimmung_id}/mit").status_code == 403,
             "Bodo kann nicht mitmachen")

    admin.post(f"{BASE}/api/stimmung", json={"text": "Doch lieber Kneipe"})
    sicht = anna.get(f"{BASE}/api/stimmung").json()
    e.pruefe(len(sicht) == 1 and sicht[0]["text"] == "Doch lieber Kneipe",
             f"eine neue Meldung ersetzt die alte = {len(sicht)}")

    neue_id = sicht[0]["id"]
    e.pruefe(anna.delete(f"{BASE}/api/stimmung/{neue_id}").status_code == 403,
             "fremde Meldungen darf man nicht loeschen")
    e.pruefe(admin.delete(f"{BASE}/api/stimmung/{neue_id}").status_code == 200,
             "die eigene schon")
    e.pruefe(len(anna.get(f"{BASE}/api/stimmung").json()) == 0,
             "danach ist die Pinnwand leer")

    e.abschnitt("Was die Live-Karte aus der Terminliste zieht")
    # Die Karte zeigt nur Termine mit Koordinaten und nur solche, die noch
    # gelten. Beides entscheidet der Server, nicht die Oberflaeche.
    mit_ort = admin.post(f"{BASE}/api/rooms/{raum}/event", json={
        "titel": "Am See", "lat": 49.03, "lon": 8.36,
        "beginnt_at": int(time.time()) + 86400}).json()["event_id"]
    admin.post(f"{BASE}/api/rooms/{raum}/event", json={
        "titel": "Ohne Ort", "beginnt_at": int(time.time()) + 86400})
    liste = admin.get(f"{BASE}/api/events").json()
    nach_titel = {x["titel"]: x for x in liste}
    e.pruefe(nach_titel["Am See"]["ort"] is not None,
             "ein Termin mit Koordinaten bringt sie mit")
    e.pruefe(nach_titel["Ohne Ort"]["ort"] is None,
             "einer ohne bleibt ohne - er kommt nicht auf die Karte")
    e.pruefe("Mit Bild" in nach_titel, "Termine ohne Zeitpunkt stehen auch drin")

    admin.delete(f"{BASE}/api/events/{mit_ort}")
    titel = [x["titel"] for x in admin.get(f"{BASE}/api/events").json()]
    e.pruefe("Am See" not in titel,
             f"ein abgesagter faellt aus der Liste = {titel}")

    e.abschnitt("Leaflet liegt im Add-on")
    r = admin.get(f"{BASE}/static/leaflet/leaflet.js")
    e.pruefe(r.status_code == 200, f"die Bibliothek wird ausgeliefert = {r.status_code}")
    e.pruefe(b"leafletjs.com" in r.content, "und ist die echte")
    e.pruefe(len(r.content) < 300 * 1024,
             f"und bleibt klein genug fuer den Pi ({len(r.content) // 1024} KB)")
    e.pruefe(admin.get(f"{BASE}/static/leaflet/leaflet.css").status_code == 200,
             "das Stilblatt liegt daneben")
    e.pruefe(admin.get(f"{BASE}/static/leaflet/images/marker-shadow.png")
             .status_code == 200, "die Symbole ebenfalls")

    e.abschnitt("Die Strassenkarte laesst sich abschalten")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["kacheln"] is True,
             "sie ist zu Beginn an")
    r = admin.post(f"{BASE}/api/me/karten", json={"kacheln": False})
    e.pruefe(r.status_code == 200 and r.json()["kacheln"] is False,
             f"sie laesst sich ausschalten = {r.status_code}")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["kacheln"] is False,
             "und bleibt aus")
    # Die Einstellung haengt am Konto, nicht am Geraet - also auch nach einer
    # neuen Anmeldung von anderswo.
    zweites, _ = anmelden("admin", "test1234")
    e.pruefe(zweites.get(f"{BASE}/api/state").json()["me"]["kacheln"] is False,
             "auch in einer neuen Sitzung")
    e.pruefe(anna.get(f"{BASE}/api/state").json()["me"]["kacheln"] is True,
             "bei Anna aendert sich nichts")
    admin.post(f"{BASE}/api/me/karten", json={"kacheln": True})
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["kacheln"] is True,
             "und wieder einschalten geht auch")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    import requests
    r = requests.post(BASE + "/api/me/karten", json={"kacheln": False},
                      allow_redirects=False)
    e.pruefe(r.status_code in (302, 401),
             f"/api/me/karten weist Fremde ab = {r.status_code}")
    for pfad in ("/api/events", "/api/live", "/api/stimmung"):
        r = requests.get(BASE + pfad, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad} weist Fremde ab = {r.status_code}")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    # Socket.IO haelt sonst Threads offen und der Lauf endet nicht
    os._exit(code)
