"""Profilbilder: setzen, ausliefern, ersetzen, entfernen, Rechte."""
import io as pyio
import os
import sys

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     verbindungen_schliessen)

AVATARE = os.path.join(os.environ.get("DATA_DIR", ""), "avatars")


def blobs():
    if not os.path.isdir(AVATARE):
        return None
    return len(os.listdir(AVATARE))


def setze(sitzung, pfad, inhalt=PNG, mime="image/png", name="bild.png"):
    return sitzung.post(f"{BASE}{pfad}",
                        files={"file": (name, pyio.BytesIO(inhalt), mime)})


def main():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    for name in ("nina", "olaf"):
        admin.post(f"{BASE}/api/users", json={"username": name,
                                              "display_name": name.capitalize(),
                                              "password": "start123"})
    nina, _ = anmelden("nina", "start123")
    olaf, _ = anmelden("olaf", "start123")
    nina_id = eigene_id(nina)

    e.abschnitt("Ohne Bild")
    e.pruefe(nina.get(f"{BASE}/avatars/u/{nina_id}").status_code == 404,
             "wer keins hat, liefert 404 - die Oberflaeche zeigt dann Initialen")
    zustand = nina.get(f"{BASE}/api/state").json()
    e.pruefe(zustand["me"]["avatar"] is None, "im Zustand steht kein Bild")

    e.abschnitt("Eigenes Bild setzen")
    vorher = blobs()
    r = setze(nina, "/api/me/avatar")
    e.pruefe(r.status_code == 200, f"hochladen = {r.status_code}")
    name1 = r.json().get("avatar")
    e.pruefe(bool(name1), "der Server nennt den neuen Namen")
    d = nina.get(f"{BASE}/avatars/u/{nina_id}")
    e.pruefe(d.status_code == 200, "das Bild ist abrufbar")
    e.pruefe("max-age" in d.headers.get("Cache-Control", ""),
             f"und darf zwischengespeichert werden: {d.headers.get('Cache-Control')}")
    e.pruefe(nina.get(f"{BASE}/api/state").json()["me"]["avatar"] == name1,
             "der Zustand kennt das Bild")
    if vorher is not None:
        e.pruefe(blobs() == vorher + 1, "eine Datei mehr auf der Platte")

    e.abschnitt("Andere sehen es auch")
    e.pruefe(olaf.get(f"{BASE}/avatars/u/{nina_id}").status_code == 200,
             "Olaf kann Ninas Bild laden")
    nutzer = olaf.get(f"{BASE}/api/state").json()["users"]
    eintrag = next((u for u in nutzer if u["id"] == nina_id), None)
    e.pruefe(eintrag and eintrag["avatar"] == name1,
             "und findet es in der Nutzerliste")

    e.abschnitt("Ersetzen raeumt das alte auf")
    vorher = blobs()
    name2 = setze(nina, "/api/me/avatar").json()["avatar"]
    e.pruefe(name2 != name1, "der Name wechselt, damit der Cache nicht stoert")
    if vorher is not None:
        e.pruefe(blobs() == vorher, f"die Anzahl bleibt gleich ({vorher})")

    e.abschnitt("Nur Bilder")
    r = setze(nina, "/api/me/avatar", b"<html>nein</html>", "text/html", "x.html")
    e.pruefe(r.status_code == 400, "eine HTML-Datei wird abgewiesen")
    e.pruefe(nina.get(f"{BASE}/api/state").json()["me"]["avatar"] == name2,
             "das bisherige Bild bleibt unangetastet")

    e.abschnitt("Gruppenbild")
    gruppe = admin.post(f"{BASE}/api/rooms", json={
        "name": "Nachbarn", "is_group": True,
        "members": [nina_id]}).json()["id"]
    r = setze(nina, f"/api/rooms/{gruppe}/avatar")
    e.pruefe(r.status_code == 200, f"ein Mitglied darf es setzen = {r.status_code}")
    e.pruefe(nina.get(f"{BASE}/avatars/r/{gruppe}").status_code == 200,
             "das Gruppenbild ist abrufbar")
    e.pruefe(olaf.get(f"{BASE}/avatars/r/{gruppe}").status_code == 403,
             "wer nicht in der Gruppe ist, sieht es nicht")
    e.pruefe(setze(olaf, f"/api/rooms/{gruppe}/avatar").status_code == 403,
             "und darf es erst recht nicht setzen")
    raum = next(r for r in nina.get(f"{BASE}/api/state").json()["rooms"]
                if r["id"] == gruppe)
    e.pruefe(bool(raum["avatar"]), "der Zustand kennt das Gruppenbild")

    e.abschnitt("Direktchats haben kein eigenes Bild")
    direkt = nina.post(f"{BASE}/api/rooms", json={"is_group": False,
                                                  "members": [admin_id]}).json()["id"]
    r = setze(nina, f"/api/rooms/{direkt}/avatar")
    e.pruefe(r.status_code == 400, "dort wird das Setzen abgelehnt")

    e.abschnitt("Entfernen")
    vorher = blobs()
    e.pruefe(nina.delete(f"{BASE}/api/me/avatar").status_code == 200,
             "eigenes Bild entfernen")
    e.pruefe(nina.get(f"{BASE}/avatars/u/{nina_id}").status_code == 404,
             "danach gibt es nichts mehr abzurufen")
    if vorher is not None:
        e.pruefe(blobs() == vorher - 1, "und die Datei ist von der Platte weg")
    e.pruefe(nina.delete(f"{BASE}/api/rooms/{gruppe}/avatar").status_code == 200,
             "Gruppenbild entfernen")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    os._exit(ergebnis)
