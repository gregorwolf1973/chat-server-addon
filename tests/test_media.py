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

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    # Der Socket.IO-Client haelt Hintergrundthreads am Leben, die den Prozess
    # sonst nach dem letzten Test nicht enden lassen.
    os._exit(ergebnis)
