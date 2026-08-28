"""Medienverwaltung: Sichtbarkeit, Loeschrechte und das Aufraeumen der Platte."""
import os
import sys

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, senden, verbindungen_schliessen)

UPLOADS = os.path.join(os.environ.get("DATA_DIR", ""), "uploads")


def dateien_auf_platte():
    """Anzahl der Blobs - nur pruefbar, wenn DATA_DIR bekannt ist."""
    if not os.path.isdir(UPLOADS):
        return None
    return len(os.listdir(UPLOADS))


def teile(sitzung, raum, name, mime="image/png", inhalt=PNG):
    datei = hochladen(sitzung, name, inhalt, mime).json()
    senden(sitzung, raum, "", datei=datei["id"])
    return datei


def main():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    for name in ("anna", "bert"):
        admin.post(f"{BASE}/api/users", json={"username": name,
                                              "display_name": name.capitalize(),
                                              "password": "start123"})
    anna, _ = anmelden("anna", "start123")
    anna_id = eigene_id(anna)
    bert, _ = anmelden("bert", "start123")

    raum_anna = anna.post(f"{BASE}/api/rooms",
                          json={"is_group": False, "members": [admin_id]}).json()["id"]
    raum_bert = bert.post(f"{BASE}/api/rooms",
                          json={"is_group": False, "members": [admin_id]}).json()["id"]

    e.abschnitt("Sichtbar ist nur, was einen ohnehin angeht")
    bild_anna = teile(anna, raum_anna, "anna.png")
    bild_bert = teile(bert, raum_bert, "bert.png")
    pdf_anna = teile(anna, raum_anna, "notiz.pdf", "application/pdf", b"%PDF-1.4 test")

    annas = anna.get(f"{BASE}/api/media").json()
    ids = [m["id"] for m in annas]
    e.pruefe(bild_anna["id"] in ids, "Anna sieht ihr eigenes Bild")
    e.pruefe(pdf_anna["id"] in ids, "Anna sieht ihre eigene Datei")
    e.pruefe(bild_bert["id"] not in ids,
             "Anna sieht nichts aus Berts Unterhaltung")
    alle = [m["id"] for m in admin.get(f"{BASE}/api/media").json()]
    e.pruefe(bild_anna["id"] in alle and bild_bert["id"] in alle,
             "der Administrator ist in beiden Raeumen und sieht beides")

    e.abschnitt("Filter nach Unterhaltung")
    gefiltert = admin.get(f"{BASE}/api/media?room={raum_bert}").json()
    e.pruefe([m["id"] for m in gefiltert] == [bild_bert["id"]],
             "der Filter liefert genau die Medien dieses Raums")

    e.abschnitt("Loeschrechte")
    eintrag = next(m for m in annas if m["id"] == bild_anna["id"])
    e.pruefe(eintrag["can_delete"], "eigene Dateien darf man loeschen")
    e.pruefe(not any(m["can_delete"] is False for m in annas),
             "in Annas Ansicht ist alles ihr eigenes")
    e.pruefe(anna.delete(f"{BASE}/api/media/{bild_bert['id']}").status_code == 404,
             "eine unsichtbare fremde Datei bleibt unerreichbar")

    vorher = dateien_auf_platte()
    r = anna.delete(f"{BASE}/api/media/{bild_anna['id']}")
    e.pruefe(r.status_code == 200, f"eigene Datei loeschen = {r.status_code}")
    e.pruefe(anna.get(f"{BASE}/files/{bild_anna['id']}").status_code == 404,
             "danach ist sie nicht mehr abrufbar")
    e.pruefe(bild_anna["id"] not in [m["id"] for m in anna.get(f"{BASE}/api/media").json()],
             "und aus der Uebersicht verschwunden")
    nachher = dateien_auf_platte()
    if vorher is None:
        print("  (Blobs nicht pruefbar - DATA_DIR nicht gesetzt)")
    else:
        e.pruefe(nachher == vorher - 1,
                 f"die Bytes sind von der Platte weg ({vorher} -> {nachher})")

    verlauf = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()
    e.pruefe(any(m["deleted"] for m in verlauf),
             "im Verlauf steht der Hinweis auf die geloeschte Nachricht")

    e.abschnitt("Der Administrator darf auch fremde")
    r = admin.delete(f"{BASE}/api/media/{bild_bert['id']}")
    e.pruefe(r.status_code == 200, f"fremde Datei loeschen = {r.status_code}")
    e.pruefe(bild_bert["id"] not in [m["id"] for m in bert.get(f"{BASE}/api/media").json()],
             "sie ist auch fuer Bert verschwunden")

    e.abschnitt("Eine geloeschte Nachricht nimmt ihre Datei mit")
    bild2 = teile(anna, raum_anna, "nochmal.png")
    treffer = [m for m in anna.get(f"{BASE}/api/media").json() if m["id"] == bild2["id"]]
    e.pruefe(len(treffer) == 1, "die neue Datei ist da")
    vorher = dateien_auf_platte()
    r = anna.delete(f"{BASE}/api/messages/{treffer[0]['message_id']}")
    e.pruefe(r.status_code == 200, f"Nachricht loeschen = {r.status_code}")
    e.pruefe(anna.get(f"{BASE}/files/{bild2['id']}").status_code == 404,
             "die Datei ist damit ebenfalls fort")
    if vorher is not None:
        nachher = dateien_auf_platte()
        e.pruefe(nachher == vorher - 1,
                 f"auch hier sind die Bytes weg ({vorher} -> {nachher})")

    e.abschnitt("Video und Ton laufen im Browser")
    clip = hochladen(anna, "clip.mp4", bytes([0, 0, 0, 24]) + b"ftypmp42" * 40,
                     "video/mp4").json()
    e.pruefe(clip["mime"] == "video/mp4", f"Video behaelt seinen Typ: {clip['mime']}")
    lied = hochladen(anna, "lied.mp3", b"ID3" + bytes([3, 0, 0, 0]) * 80,
                     "audio/mpeg").json()
    e.pruefe(lied["mime"] == "audio/mpeg", f"Ton behaelt seinen Typ: {lied['mime']}")
    d = anna.get(f"{BASE}/files/{clip['id']}")
    e.pruefe("attachment" not in d.headers.get("Content-Disposition", ""),
             "Video wird zum Abspielen ausgeliefert, nicht als Download")
    e.pruefe("media-src 'self'" in d.headers.get("Content-Security-Policy", ""),
             "die CSP erlaubt das Abspielen")
    boese = hochladen(anna, "trick.html", b"<script>1</script>", "text/html").json()
    e.pruefe(boese["mime"] == "application/octet-stream",
             "HTML bleibt trotzdem draussen")

    e.abschnitt("Farbe je Unterhaltung - nur fuer einen selbst")
    r = anna.post(f"{BASE}/api/rooms/{raum_anna}/color", json={"color": "#3b4a6b"})
    e.pruefe(r.status_code == 200, f"Farbe setzen = {r.status_code}")
    meiner = next(x for x in anna.get(f"{BASE}/api/state").json()["rooms"]
                  if x["id"] == raum_anna)
    e.pruefe(meiner["color"] == "#3b4a6b", "sie steht in Annas Zustand")
    seiner = next((x for x in admin.get(f"{BASE}/api/state").json()["rooms"]
                   if x["id"] == raum_anna), None)
    e.pruefe(seiner is not None and seiner["color"] is None,
             "der Administrator sieht davon nichts")
    e.pruefe(anna.post(f"{BASE}/api/rooms/{raum_anna}/color",
                       json={"color": "#ff0000"}).status_code == 400,
             "eine nicht vorgesehene Farbe wird abgewiesen")
    e.pruefe(anna.post(f"{BASE}/api/rooms/{raum_bert}/color",
                       json={"color": "#3b4a6b"}).status_code == 403,
             "in fremden Unterhaltungen geht es nicht")
    r = anna.post(f"{BASE}/api/rooms/{raum_anna}/color", json={"color": ""})
    e.pruefe(r.status_code == 200 and r.json()["color"] is None,
             "zuruecksetzen auf Standard")

    e.abschnitt("Unterhaltung bei sich loeschen")
    eigener = anna.post(f"{BASE}/api/rooms",
                        json={"is_group": True, "name": "Nur kurz",
                              "members": [admin_id]}).json()["id"]
    senden(anna, eigener, "steht hier drin")
    r = anna.post(f"{BASE}/api/rooms/{eigener}/leave")
    e.pruefe(r.status_code == 200, f"verlassen = {r.status_code}")
    e.pruefe(not any(x["id"] == eigener
                     for x in anna.get(f"{BASE}/api/state").json()["rooms"]),
             "aus Annas Liste verschwunden")
    e.pruefe(any(x["id"] == eigener
                 for x in admin.get(f"{BASE}/api/state").json()["rooms"]),
             "der Administrator behaelt sie")
    e.pruefe(any(m["body"] == "steht hier drin"
                 for m in admin.get(f"{BASE}/api/rooms/{eigener}/messages").json()),
             "und sieht den Verlauf weiterhin")
    e.pruefe(anna.get(f"{BASE}/api/rooms/{eigener}/messages").status_code == 403,
             "Anna kommt nicht mehr an den Verlauf")

    e.abschnitt("Unterhaltung fuer alle loeschen")
    gemeinsam = admin.post(f"{BASE}/api/rooms",
                           json={"is_group": True, "name": "Weg damit",
                                 "members": [anna_id]}).json()["id"]
    bild = hochladen(anna, "anhang.png", PNG, "image/png").json()
    senden(anna, gemeinsam, "", datei=bild["id"])
    vorher = dateien_auf_platte()
    e.pruefe(anna.delete(f"{BASE}/api/rooms/{gemeinsam}").status_code == 403,
             "ein gewoehnliches Konto darf das nicht")
    e.pruefe(admin.delete(f"{BASE}/api/rooms/{gemeinsam}").status_code == 200,
             "der Administrator schon")
    e.pruefe(not any(x["id"] == gemeinsam
                     for x in anna.get(f"{BASE}/api/state").json()["rooms"]),
             "sie ist bei allen fort")
    e.pruefe(anna.get(f"{BASE}/files/{bild['id']}").status_code == 404,
             "der Anhang ist nicht mehr abrufbar")
    if vorher is not None:
        e.pruefe(dateien_auf_platte() == vorher - 1,
                 "und die Bytes sind von der Platte weg")
    e.pruefe(admin.delete(f"{BASE}/api/rooms/{gemeinsam}").status_code == 404,
             "ein zweites Loeschen meldet sauber 404")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    # Der Socket.IO-Client haelt Hintergrundthreads am Leben, die den Prozess
    # sonst nach dem letzten Test nicht enden lassen.
    os._exit(ergebnis)
