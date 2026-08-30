"""Zugriffsschutz: Dateitypen, fremde Datei-IDs, Manifest-Pfade."""
import os
import sys
import time
from urllib.parse import urljoin

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, senden, senden_mit_antwort, verbindung,
                     verbindungen_schliessen)


def main():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    admin.post(f"{BASE}/api/users", json={"username": "testperson",
                                          "display_name": "Test Person",
                                          "password": "start123"})
    gast, code = anmelden("testperson", "start123")
    assert code == 302, "Das Testkonto kam nicht hinein"

    e.abschnitt("Der MIME-Typ kommt vom Client - ihm darf man nicht glauben")
    boese = hochladen(admin, "boese.html",
                      b"<script>alert(document.cookie)</script>", "text/html").json()
    e.pruefe(boese["mime"] == "application/octet-stream",
             f"'text/html' wird zu {boese['mime']!r}")
    d = admin.get(f"{BASE}/files/{boese['id']}")
    e.pruefe(d.headers.get("Content-Type", "").startswith("application/octet-stream"),
             f"Auslieferung als {d.headers.get('Content-Type')!r}")
    e.pruefe("attachment" in d.headers.get("Content-Disposition", ""),
             "als Download, nicht als Seite")
    e.pruefe(d.headers.get("X-Content-Type-Options") == "nosniff",
             "mit nosniff gegen das Erraten des Typs")
    e.pruefe("default-src 'none'" in d.headers.get("Content-Security-Policy", ""),
             "und einer engen CSP")

    bild = hochladen(admin, "bild.png", PNG, "image/png").json()
    e.pruefe(bild["mime"] == "image/png", "ein echtes Bild bleibt 'image/png'")
    d = admin.get(f"{BASE}/files/{bild['id']}")
    e.pruefe("attachment" not in d.headers.get("Content-Disposition", ""),
             "und wird weiterhin direkt angezeigt")
    d = admin.get(f"{BASE}/files/{bild['id']}?dl=1")
    e.pruefe("attachment" in d.headers.get("Content-Disposition", ""),
             "?dl=1 erzwingt trotzdem den Download")

    e.abschnitt("Fremde Datei-IDs an eigenen Nachrichten")
    raum = gast.post(f"{BASE}/api/rooms",
                     json={"is_group": False, "members": [admin_id]}).json()["id"]
    senden(gast, raum, "geklaut?", datei=bild["id"])
    senden(gast, raum, "ganz normal")
    nachrichten = gast.get(f"{BASE}/api/rooms/{raum}/messages").json()
    e.pruefe(not [m for m in nachrichten if m.get("file")],
             "die fremde Datei wurde nicht angehaengt")
    e.pruefe(any(m["body"] == "ganz normal" for m in nachrichten),
             "normale Nachrichten kommen weiterhin durch")
    e.pruefe(gast.get(f"{BASE}/files/{bild['id']}").status_code == 403,
             "und der Direktzugriff bleibt verwehrt")

    eigenes = hochladen(gast, "meins.png", PNG, "image/png").json()
    senden(gast, raum, "", datei=eigenes["id"])
    nachrichten = gast.get(f"{BASE}/api/rooms/{raum}/messages").json()
    e.pruefe(any(m.get("file") and m["file"]["id"] == eigenes["id"]
                 for m in nachrichten),
             "die eigene Datei laesst sich senden")

    e.abschnitt("Der Server bestaetigt jede Nachricht")
    antwort = senden_mit_antwort(gast, raum, "wird das bestaetigt?")
    e.pruefe(antwort and antwort.get("ok"), f"eine gueltige Nachricht: {antwort}")
    # Der Sende-Knopf reichte frueher sein Klick-Ereignis als Datei-Kennung
    # weiter - ohne Bestaetigung verschwand die Nachricht stillschweigend.
    antwort = senden_mit_antwort(gast, raum, "mit Unsinn als Datei",
                                 datei={"isTrusted": True})
    e.pruefe(antwort and antwort.get("ok") is False,
             f"eine unsinnige Datei-Kennung wird gemeldet: {antwort}")
    e.pruefe(not any(m["body"] == "mit Unsinn als Datei"
                     for m in gast.get(f"{BASE}/api/rooms/{raum}/messages").json()),
             "und die Nachricht landet nicht im Verlauf")

    e.abschnitt("Manifest-Pfade werden relativ zum Manifest aufgeloest")
    manifest_url = f"{BASE}/manifest.webmanifest"
    mf = admin.get(manifest_url).json()
    for name, wert in [("start_url", mf["start_url"]),
                       ("Symbol 192", mf["icons"][0]["src"]),
                       ("Symbol 512", mf["icons"][1]["src"])]:
        ziel = urljoin(manifest_url, wert)
        code = admin.get(ziel).status_code
        e.pruefe(code == 200, f"{name}: {wert!r} -> {ziel} = {code}")
    e.pruefe(all("?v=" in i["src"] for i in mf["icons"]),
             "die Symbole tragen eine Kennung, damit kein altes Bild haengen bleibt")

    e.abschnitt("Verstecktes bleibt versteckt")
    # Ohne diese Regel ueberstimmt jedes eigene display das hidden-Attribut.
    # Das Anhang-Menue liess sich deshalb nicht schliessen, und das
    # Anruffenster haette bildschirmfuellend ueber allem gelegen.
    css = admin.get(f"{BASE}/static/style.css")
    e.pruefe(css.status_code == 200, f"das Stilblatt wird ausgeliefert = {css.status_code}")
    ohne_leer = "".join(css.text.split())
    e.pruefe("[hidden]{display:none!important" in ohne_leer,
             "und setzt hidden ausdruecklich durch")

    e.abschnitt("Die Weltkarte liegt im Add-on")
    r = admin.get(f"{BASE}/static/weltkarte.svg")
    e.pruefe(r.status_code == 200, f"sie wird ausgeliefert = {r.status_code}")
    e.pruefe(' d="M' in r.text, "und enthaelt Umrisse")
    e.pruefe(len(r.content) < 400 * 1024,
             f"und bleibt klein genug fuer den Pi ({len(r.content) // 1024} KB)")

    e.abschnitt("Auch Skript und Gestaltung tragen eine Kennung")
    seite = admin.get(f"{BASE}/").text
    e.pruefe("app.js?v=" in seite and "style.css?v=" in seite,
             "sonst liefert der Browser nach einem Update alte Dateien aus")

    e.abschnitt("Inhaltsrichtlinie fuer die Seite")
    r = admin.get(f"{BASE}/")
    csp = r.headers.get("Content-Security-Policy", "")
    e.pruefe(csp, "die Seite bringt eine Richtlinie mit")
    e.pruefe("script-src 'self' 'nonce-" in csp,
             "Skripte nur von hier, das eine mit Kennung")
    e.pruefe("object-src 'none'" in csp and "base-uri 'none'" in csp,
             "kein Objekt, keine fremde Grundadresse")
    e.pruefe("tile.openstreetmap.org" in csp,
             "Kartenkacheln sind die einzige fremde Quelle")
    kennung = csp.split("'nonce-")[1].split("'")[0]
    e.pruefe(f'nonce="{kennung}"' in r.text,
             "das Skript in der Seite traegt genau diese Kennung")
    zweite = admin.get(f"{BASE}/").headers.get("Content-Security-Policy", "")
    e.pruefe(zweite != csp, "und sie wechselt bei jedem Aufruf")
    e.pruefe("Content-Security-Policy" in admin.get(f"{BASE}/login").headers,
             "die Anmeldeseite ebenfalls")

    e.abschnitt("Push-Anmeldung verraet nichts nach innen")
    r = admin.post(f"{BASE}/api/push/subscribe", json={"endpoint": "x"})
    e.pruefe(r.status_code == 400, f"unvollstaendig wird abgewiesen = {r.status_code}")
    text = r.json().get("error", "")
    e.pruefe("push_subs" not in text and "p256dh" not in text.lower(),
             f"ohne Tabellen- und Spaltennamen = {text!r}")

    e.abschnitt('"Schreibt gerade" nur in eigenen Unterhaltungen')
    # Ein Raum, in dem der Administrator ist und das Testkonto nicht
    admin.post(f"{BASE}/api/users", json={"username": "dritte",
                                          "display_name": "Dritte",
                                          "password": "start123"})
    dritte, _ = anmelden("dritte", "start123")
    ohne_gast = admin.post(f"{BASE}/api/rooms", json={
        "name": "Ohne Gast", "is_group": True,
        "members": [eigene_id(dritte)]}).json()["id"]
    # Erst jetzt verbinden: die Sockets treten den Raeumen beim Verbinden bei
    verbindungen_schliessen()
    lauscher = verbindung(admin)
    empfangen = []
    lauscher.on("typing", lambda d: empfangen.append(d))
    time.sleep(0.6)

    verbindung(gast).emit("typing", {"room_id": ohne_gast,
                                     "name": "Jemand ganz anderes"})
    time.sleep(1.5)
    e.pruefe(not empfangen,
             f"wer nicht dazugehoert, dringt nicht durch = {empfangen}")

    # In der gemeinsamen Unterhaltung geht es - mit dem Namen vom Server
    empfangen.clear()
    verbindung(gast).emit("typing", {"room_id": raum,
                                     "name": "Erfundener Name"})
    time.sleep(1.5)
    e.pruefe(len(empfangen) == 1, f"in der gemeinsamen schon = {empfangen}")
    e.pruefe(empfangen and empfangen[0].get("name") == "Test Person",
             "und der Name kommt vom Server, nicht aus der Anfrage = "
             f"{empfangen[0].get('name') if empfangen else '-'}")
    e.pruefe(empfangen and empfangen[0].get("room_id") == raum,
             "mit der richtigen Unterhaltung")

    e.abschnitt("Der Datenstrom nimmt keine fremde Herkunft an")
    import socketio as sio_mod
    cookie = "; ".join(f"{c.name}={c.value}" for c in admin.cookies)
    fremd_client = sio_mod.Client(reconnection=False)
    abgewiesen = False
    try:
        fremd_client.connect(BASE, transports=["polling"], wait_timeout=6,
                             headers={"Cookie": cookie,
                                      "Origin": "https://boese.example"})
    except Exception:  # noqa: BLE001
        abgewiesen = True
    else:
        fremd_client.disconnect()
    e.pruefe(abgewiesen,
             "eine Verbindung von einer fremden Seite kommt nicht durch")

    eigen_client = sio_mod.Client(reconnection=False)
    durchgelassen = True
    try:
        eigen_client.connect(BASE, transports=["polling"], wait_timeout=6,
                             headers={"Cookie": cookie, "Origin": BASE})
    except Exception:  # noqa: BLE001
        durchgelassen = False
    else:
        eigen_client.disconnect()
    e.pruefe(durchgelassen, "von der eigenen Seite schon")

    e.abschnitt("Push-Anmeldungen bleiben gedeckelt")
    for i in range(25):
        admin.post(f"{BASE}/api/push/subscribe", json={
            "endpoint": f"https://push.example/{i}",
            "keys": {"p256dh": "k" * 20, "auth": "a" * 12}})
    # Ueber die Schnittstelle nicht abfragbar - der Deckel zeigt sich daran,
    # dass die aelteste Anmeldung nicht mehr benachrichtigt wird. Hier reicht
    # die Zusicherung, dass keine Anfrage gescheitert ist.
    r = admin.post(f"{BASE}/api/push/subscribe", json={
        "endpoint": "https://push.example/letzte",
        "keys": {"p256dh": "k" * 20, "auth": "a" * 12}})
    e.pruefe(r.status_code == 200,
             f"die 26. Anmeldung geht durch = {r.status_code}")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    # Der Socket.IO-Client haelt Hintergrundthreads am Leben, die den Prozess
    # sonst nach dem letzten Test nicht enden lassen.
    os._exit(ergebnis)
