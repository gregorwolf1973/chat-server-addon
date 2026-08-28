"""Zugriffsschutz: Dateitypen, fremde Datei-IDs, Manifest-Pfade."""
import os
import sys
from urllib.parse import urljoin

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, senden, senden_mit_antwort,
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

    e.abschnitt("Auch Skript und Gestaltung tragen eine Kennung")
    seite = admin.get(f"{BASE}/").text
    e.pruefe("app.js?v=" in seite and "style.css?v=" in seite,
             "sonst liefert der Browser nach einem Update alte Dateien aus")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    # Der Socket.IO-Client haelt Hintergrundthreads am Leben, die den Prozess
    # sonst nach dem letzten Test nicht enden lassen.
    os._exit(ergebnis)
