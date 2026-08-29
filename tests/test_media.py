"""Medienverwaltung: Sichtbarkeit, Loeschrechte und das Aufraeumen der Platte."""
import os
import sys

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, senden, senden_mit_antwort,
                     verbindungen_schliessen)

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
    bert_id = eigene_id(bert)

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

    e.abschnitt("Album-Kennung fuer gebuendelte Bilder")
    for name in ("alb1.png", "alb2.png"):
        d = hochladen(anna, name, PNG, "image/png").json()
        senden_mit_antwort(anna, raum_anna, "", datei=d["id"], album="abc123")
    nachrichten = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()
    mit_album = [m for m in nachrichten if m.get("album") == "abc123"]
    e.pruefe(len(mit_album) == 2,
             f"beide Bilder tragen dieselbe Kennung ({len(mit_album)})")
    e.pruefe(all(m["file"] for m in mit_album),
             "und haengen weiterhin je an einer eigenen Nachricht")

    d = hochladen(anna, "einzeln.png", PNG, "image/png").json()
    senden_mit_antwort(anna, raum_anna, "", datei=d["id"])
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["album"] is None, "ein einzelnes Bild bekommt keine Kennung")

    d = hochladen(anna, "boese.png", PNG, "image/png").json()
    senden_mit_antwort(anna, raum_anna, "", datei=d["id"],
                       album="<script>alert(1)</script>")
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["album"] is None,
             "eine Kennung mit Sonderzeichen wird verworfen")

    e.abschnitt("Standort in einer Nachricht")
    antwort = senden_mit_antwort(anna, raum_anna, "Bin hier",
                                 ort={"lat": 36.5101, "lon": -4.8825})
    e.pruefe(antwort and antwort.get("ok"), "eine Nachricht mit Ort wird angenommen")
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["ort"] and abs(letzte["ort"]["lat"] - 36.5101) < 0.0001,
             f"die Koordinaten kommen zurueck: {letzte['ort']}")
    antwort = senden_mit_antwort(anna, raum_anna, "",
                                 ort={"lat": 200, "lon": 0})
    e.pruefe(antwort and antwort.get("ok") is False,
             "unmoegliche Koordinaten machen die Nachricht leer und damit ungueltig")
    antwort = senden_mit_antwort(anna, raum_anna, "nur Text",
                                 ort={"lat": "hier", "lon": "dort"})
    e.pruefe(antwort and antwort.get("ok"), "unsinnige Werte kippen den Text nicht")
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["ort"] is None, "werden aber verworfen")

    e.abschnitt("Nachrichten weiterleiten")
    quelle = hochladen(anna, "weiter.png", PNG, "image/png").json()
    senden_mit_antwort(anna, raum_anna, "Schau mal", datei=quelle["id"])
    msg = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    eigener = anna.post(f"{BASE}/api/rooms",
                        json={"is_group": False, "members": [bert_id]}).json()["id"]

    r = anna.post(f"{BASE}/api/messages/{msg['id']}/weiterleiten",
                  json={"room_id": eigener})
    e.pruefe(r.status_code == 200, f"die Nachricht geht weiter = {r.status_code}")
    ziel = anna.get(f"{BASE}/api/rooms/{eigener}/messages").json()[-1]
    e.pruefe(ziel["body"] == "Schau mal", "der Text kommt mit")
    e.pruefe(ziel["file"] and ziel["file"]["id"] == quelle["id"],
             "der Anhang auch - und zwar derselbe, nicht eine Kopie")
    e.pruefe(ziel["weitergeleitet"] is True, "sie ist als weitergeleitet vermerkt")
    e.pruefe(bert.get(f"{BASE}/files/{quelle['id']}").status_code == 200,
             "Bert sieht das Bild jetzt, weil es in seiner Unterhaltung haengt")

    e.pruefe(anna.post(f"{BASE}/api/messages/{msg['id']}/weiterleiten",
                       json={"room_id": raum_anna}).status_code == 400,
             "in dieselbe Unterhaltung geht es nicht")
    e.pruefe(anna.post(f"{BASE}/api/messages/{msg['id']}/weiterleiten",
                       json={"room_id": raum_bert}).status_code == 403,
             "in eine fremde auch nicht")
    e.pruefe(bert.post(f"{BASE}/api/messages/{msg['id']}/weiterleiten",
                       json={"room_id": raum_bert}).status_code == 403,
             "und eine fremde Nachricht kann man nicht weiterleiten")
    e.pruefe(anna.post(f"{BASE}/api/messages/999999/weiterleiten",
                       json={"room_id": eigener}).status_code == 403,
             "eine unbekannte ebenso wenig")

    e.abschnitt("Hintergrundmuster einer Unterhaltung")
    def muster(sitzung, raum, wert):
        return sitzung.post(f"{BASE}/api/rooms/{raum}/hintergrund",
                            json={"muster": wert})
    r = muster(anna, raum_anna, "karo")
    e.pruefe(r.status_code == 200 and r.json()["hintergrund"] == "karo",
             f"Anna waehlt ein Muster = {r.status_code}")
    dieser = [x for x in anna.get(f"{BASE}/api/state").json()["rooms"]
              if x["id"] == raum_anna][0]
    e.pruefe(dieser["hintergrund"] == "karo", "der Startzustand nennt es")
    e.pruefe("color" not in dieser, "eine Farbe gibt es nicht mehr")

    # Es gehoert der Person, nicht der Unterhaltung
    anderer = [x for x in admin.get(f"{BASE}/api/state").json()["rooms"]
               if x["id"] == raum_anna][0]
    e.pruefe(anderer["hintergrund"] is None,
             "das andere Mitglied sieht seins, nicht ihres")
    muster(admin, raum_anna, "punkte")
    e.pruefe([x for x in admin.get(f"{BASE}/api/state").json()["rooms"]
              if x["id"] == raum_anna][0]["hintergrund"] == "punkte",
             "er waehlt sein eigenes")
    e.pruefe([x for x in anna.get(f"{BASE}/api/state").json()["rooms"]
              if x["id"] == raum_anna][0]["hintergrund"] == "karo",
             "Annas bleibt davon unberuehrt")

    e.pruefe(muster(anna, raum_anna, "regenbogen").status_code == 400,
             "ein erfundenes Muster wird abgewiesen")
    e.pruefe(muster(anna, raum_bert, "karo").status_code == 403,
             "in einer fremden Unterhaltung geht es nicht")
    r = muster(anna, raum_anna, "")
    e.pruefe(r.status_code == 200 and r.json()["hintergrund"] is None,
             "und es laesst sich wieder abwaehlen")

    # Es gibt keine Bilddatei mehr - das Muster wird gezeichnet
    e.pruefe(anna.get(f"{BASE}/hintergrund/{raum_anna}").status_code == 404,
             "die alte Bildadresse gibt es nicht mehr")

    e.abschnitt("Sprachnachrichten")
    ton = hochladen(anna, "sprachnachricht.webm", b"kein echter Ton, reicht hier",
                    "audio/webm").json()
    e.pruefe(ton.get("mime") == "audio/webm",
             f"eine Aufnahme wird angenommen = {ton.get('mime')}")
    antwort = senden_mit_antwort(anna, raum_anna, "", datei=ton["id"],
                                 sprachdauer=14)
    e.pruefe(antwort and antwort.get("ok"), "sie laesst sich senden")
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["sprachdauer"] == 14,
             f"die Laenge kommt zurueck = {letzte['sprachdauer']}")

    # Die Laenge steht nur fuer eine Aufnahme - ohne Datei ergaebe sie keinen
    # Sinn, und eine Stunde ist die Obergrenze.
    ton2 = hochladen(anna, "lang.webm", b"x", "audio/webm").json()
    senden_mit_antwort(anna, raum_anna, "", datei=ton2["id"], sprachdauer=99999)
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["sprachdauer"] == 3600,
             f"unsinnig lange Angaben werden gedeckelt = {letzte['sprachdauer']}")
    senden_mit_antwort(anna, raum_anna, "nur Text", sprachdauer=9)
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["sprachdauer"] is None,
             "ohne Aufnahme wird die Laenge verworfen")
    ton3 = hochladen(anna, "krumm.webm", b"y", "audio/webm").json()
    senden_mit_antwort(anna, raum_anna, "", datei=ton3["id"], sprachdauer="viel")
    letzte = anna.get(f"{BASE}/api/rooms/{raum_anna}/messages").json()[-1]
    e.pruefe(letzte["sprachdauer"] is None, "und Unfug ebenso")

    e.abschnitt("Mehrere Medien auf einmal loeschen")
    eigene = []
    for n in ("s1.png", "s2.png", "s3.png"):
        d = hochladen(anna, n, PNG, "image/png").json()
        senden(anna, raum_anna, "", datei=d["id"])
        eigene.append(d["id"])
    fremd = hochladen(bert, "berts.png", PNG, "image/png").json()
    senden(bert, raum_bert, "", datei=fremd["id"])
    vorher = dateien_auf_platte()

    r = anna.post(f"{BASE}/api/media/delete", json={"ids": []})
    e.pruefe(r.status_code == 400, "eine leere Auswahl wird abgewiesen")

    r = anna.post(f"{BASE}/api/media/delete", json={"ids": eigene[:2]})
    e.pruefe(r.status_code == 200 and r.json()["geloescht"] == 2,
             f"zwei eigene auf einmal: {r.json()}")
    e.pruefe(anna.get(f"{BASE}/files/{eigene[0]}").status_code == 404,
             "die erste ist fort")
    if vorher is not None:
        e.pruefe(dateien_auf_platte() == vorher - 2,
                 "beide Dateien sind von der Platte weg")

    r = anna.post(f"{BASE}/api/media/delete",
                  json={"ids": [eigene[2], fremd["id"], 999999]})
    daten = r.json()
    e.pruefe(daten["geloescht"] == 1 and daten["abgelehnt"] == 2,
             f"Fremdes und Unbekanntes werden uebersprungen: {daten}")
    e.pruefe(bert.get(f"{BASE}/files/{fremd['id']}").status_code == 200,
             "Berts Datei ist unversehrt")

    r = admin.post(f"{BASE}/api/media/delete", json={"ids": [fremd["id"]]})
    e.pruefe(r.json()["geloescht"] == 1,
             "der Administrator darf auch fremde in einem Rutsch")

    e.abschnitt("Verlaesst der Letzte, verschwindet alles")
    zuzweit = admin.post(f"{BASE}/api/rooms",
                         json={"is_group": True, "name": "Zu zweit",
                               "members": [anna_id]}).json()["id"]
    anhang = hochladen(anna, "gemeinsam.png", PNG, "image/png").json()
    senden(anna, zuzweit, "", datei=anhang["id"])
    vorher = dateien_auf_platte()

    e.pruefe(anna.post(f"{BASE}/api/rooms/{zuzweit}/leave").status_code == 200,
             "Anna geht als Erste")
    e.pruefe(admin.get(f"{BASE}/files/{anhang['id']}").status_code == 200,
             "solange der Administrator bleibt, ist der Anhang noch da")
    if vorher is not None:
        e.pruefe(dateien_auf_platte() == vorher,
                 "und die Datei liegt weiterhin auf der Platte")

    e.pruefe(admin.post(f"{BASE}/api/rooms/{zuzweit}/leave").json().get("geloescht"),
             "geht auch der Letzte, meldet der Server die Aufloesung")
    e.pruefe(admin.get(f"{BASE}/files/{anhang['id']}").status_code == 404,
             "der Anhang ist damit fort")
    if vorher is not None:
        e.pruefe(dateien_auf_platte() == vorher - 1,
                 f"auch von der Platte ({vorher} -> {dateien_auf_platte()})")
    e.pruefe(not any(x["id"] == zuzweit
                     for x in admin.get(f"{BASE}/api/state").json()["rooms"]),
             "und die Unterhaltung ist bei niemandem mehr sichtbar")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    # Der Socket.IO-Client haelt Hintergrundthreads am Leben, die den Prozess
    # sonst nach dem letzten Test nicht enden lassen.
    os._exit(ergebnis)
