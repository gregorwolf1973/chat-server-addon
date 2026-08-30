"""Galerie: freigeben, Herzen, Kommentare - und wer was davon sieht.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys

import requests

from helpers import (BASE, PNG, Ergebnis, als_admin, anmelden, eigene_id,
                     hochladen, senden_mit_antwort, verbindungen_schliessen)


def befreunden(a, b, b_id, a_id):
    """Beide fragen einander - das gilt als bestaetigte Freundschaft."""
    a.post(f"{BASE}/api/freunde/{b_id}")
    b.post(f"{BASE}/api/freunde/{a_id}")


def lauf():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    for name in ("anna", "bert", "cara"):
        admin.post(f"{BASE}/api/users", json={"username": name,
                                              "display_name": name.capitalize(),
                                              "password": "test1234"})
    anna, _ = anmelden("anna", "test1234")
    bert, _ = anmelden("bert", "test1234")
    cara, _ = anmelden("cara", "test1234")
    anna_id, bert_id, cara_id = (eigene_id(anna), eigene_id(bert),
                                 eigene_id(cara))

    # Anna und Bert sind Freunde, Cara steht draussen
    befreunden(anna, bert, bert_id, anna_id)
    raum = anna.post(f"{BASE}/api/rooms", json={
        "name": "Runde", "is_group": True, "members": [bert_id]}).json()["id"]

    bild = hochladen(anna, "urlaub.png", PNG, "image/png").json()
    zweites = hochladen(anna, "berg.png", PNG, "image/png").json()
    senden_mit_antwort(anna, raum, "", datei=bild["id"])
    senden_mit_antwort(anna, raum, "", datei=zweites["id"])
    fremd = hochladen(bert, "bert.png", PNG, "image/png").json()

    e.abschnitt("Freigeben")
    r = anna.post(f"{BASE}/api/galerie", json={"file_id": bild["id"],
                                               "art": "freunde",
                                               "titel": "Am Meer"})
    e.pruefe(r.status_code == 200, f"ein eigenes Bild geht = {r.status_code}")
    eintrag = r.json()
    e.pruefe(eintrag["art"] == "freunde" and eintrag["titel"] == "Am Meer",
             f"mit Art und Unterschrift = {eintrag['art']}/{eintrag['titel']}")
    e.pruefe(eintrag["herzen"] == 0 and eintrag["worte"] == 0,
             "frisch und ohne Herzen")

    e.pruefe(bert.post(f"{BASE}/api/galerie",
                       json={"file_id": bild["id"], "art": "alle"}
                       ).status_code == 403,
             "ein fremdes Bild kann Bert nicht freigeben")
    e.pruefe(anna.post(f"{BASE}/api/galerie",
                       json={"file_id": bild["id"], "art": "welt"}
                       ).status_code == 400,
             "eine erfundene Art wird abgewiesen")
    e.pruefe(anna.post(f"{BASE}/api/galerie", json={"art": "alle"}
                       ).status_code == 400,
             "ohne Datei geht es nicht")
    pdf = hochladen(anna, "brief.pdf", PNG, "application/pdf").json()
    e.pruefe(anna.post(f"{BASE}/api/galerie",
                       json={"file_id": pdf["id"], "art": "alle"}
                       ).status_code == 400,
             "und ein PDF ist kein Bild")

    e.abschnitt("Wer sieht was")
    e.pruefe(len(anna.get(f"{BASE}/api/galerie/{anna_id}").json()["eintraege"]) == 1,
             "Anna sieht ihr eigenes")
    e.pruefe(anna.get(f"{BASE}/api/galerie/{anna_id}").json()["meine"] is True,
             "und weiss, dass es ihre ist")
    e.pruefe(len(bert.get(f"{BASE}/api/galerie/{anna_id}").json()["eintraege"]) == 1,
             "der Freund Bert auch")
    e.pruefe(len(cara.get(f"{BASE}/api/galerie/{anna_id}").json()["eintraege"]) == 0,
             "Cara nicht - sie ist keine Freundin")

    anna.post(f"{BASE}/api/galerie", json={"file_id": zweites["id"],
                                           "art": "alle"})
    e.pruefe(len(cara.get(f"{BASE}/api/galerie/{anna_id}").json()["eintraege"]) == 1,
             "was fuer alle frei ist, sieht auch Cara")
    e.pruefe(anna.get(f"{BASE}/api/galerie/9999").status_code == 404,
             "eine erfundene Person gibt es nicht")

    e.abschnitt("Die Datei selbst wird abrufbar")
    e.pruefe(cara.get(f"{BASE}/files/{zweites['id']}").status_code == 200,
             "Cara darf das freigegebene Bild laden")
    e.pruefe(cara.get(f"{BASE}/files/{bild['id']}").status_code == 403,
             "das nur fuer Freunde freigegebene nicht")
    e.pruefe(bert.get(f"{BASE}/files/{bild['id']}").status_code == 200,
             "Bert schon")

    e.abschnitt("Herzen zaehlt jeder")
    g_freunde = [x for x in bert.get(f"{BASE}/api/galerie/{anna_id}").json()
                 ["eintraege"] if x["file_id"] == bild["id"]][0]
    r = bert.post(f"{BASE}/api/galerie/{g_freunde['id']}/herz")
    e.pruefe(r.status_code == 200 and r.json()["herzen"] == 1,
             f"Bert setzt eines = {r.status_code}")
    e.pruefe(r.json()["mein_herz"] is True, "und sieht es als seines")
    sicht = [x for x in anna.get(f"{BASE}/api/galerie/{anna_id}").json()
             ["eintraege"] if x["id"] == g_freunde["id"]][0]
    e.pruefe(sicht["herzen"] == 1, "Anna sieht die Zahl")
    e.pruefe(sicht["mein_herz"] is False, "aber nicht als ihres")
    r = bert.post(f"{BASE}/api/galerie/{g_freunde['id']}/herz")
    e.pruefe(r.json()["herzen"] == 0, "ein zweiter Tipp nimmt es zurueck")
    bert.post(f"{BASE}/api/galerie/{g_freunde['id']}/herz")
    e.pruefe(cara.post(f"{BASE}/api/galerie/{g_freunde['id']}/herz"
                       ).status_code == 403,
             "Cara kommt an dieses Bild nicht heran")

    e.abschnitt("Kommentare bleiben zwischen zweien")
    g_alle = [x for x in cara.get(f"{BASE}/api/galerie/{anna_id}").json()
              ["eintraege"] if x["file_id"] == zweites["id"]][0]
    e.pruefe(bert.post(f"{BASE}/api/galerie/{g_alle['id']}/worte",
                       json={"text": "Schoener Berg"}).status_code == 200,
             "Bert schreibt etwas")
    e.pruefe(cara.post(f"{BASE}/api/galerie/{g_alle['id']}/worte",
                       json={"text": "Da war ich auch"}).status_code == 200,
             "Cara auch")
    e.pruefe(bert.post(f"{BASE}/api/galerie/{g_alle['id']}/worte",
                       json={"text": "   "}).status_code == 400,
             "leerer Text wird abgewiesen")

    berts = bert.get(f"{BASE}/api/galerie/{g_alle['id']}/worte").json()
    e.pruefe(len(berts["worte"]) == 1,
             f"Bert sieht nur seinen eigenen Faden = {len(berts['worte'])}")
    e.pruefe(berts["worte"][0]["text"] == "Schoener Berg", "naemlich seinen")
    caras = cara.get(f"{BASE}/api/galerie/{g_alle['id']}/worte").json()
    e.pruefe([w["text"] for w in caras["worte"]] == ["Da war ich auch"],
             "Cara ebenso nur ihren")
    e.pruefe(bert.get(f"{BASE}/api/galerie/{g_alle['id']}/worte"
                      f"?mit={cara_id}").json()["mit_id"] == bert_id,
             "Bert kann sich nicht in Caras Faden schummeln")

    uebersicht = anna.get(f"{BASE}/api/galerie/{g_alle['id']}/worte").json()
    e.pruefe(len(uebersicht["faeden"]) == 2,
             f"Anna sieht zwei Gespraeche = {len(uebersicht['faeden'])}")
    e.pruefe({f["mit_id"] for f in uebersicht["faeden"]} == {bert_id, cara_id},
             "mit Bert und mit Cara")
    einer = anna.get(f"{BASE}/api/galerie/{g_alle['id']}/worte"
                     f"?mit={bert_id}").json()
    e.pruefe([w["text"] for w in einer["worte"]] == ["Schoener Berg"],
             "und kann einen davon lesen")

    e.abschnitt("Antworten und Loeschen")
    r = anna.post(f"{BASE}/api/galerie/{g_alle['id']}/worte",
                  json={"text": "Danke!", "mit_id": bert_id})
    e.pruefe(r.status_code == 200, f"Anna antwortet Bert = {r.status_code}")
    e.pruefe(len(bert.get(f"{BASE}/api/galerie/{g_alle['id']}/worte"
                          ).json()["worte"]) == 2,
             "Bert sieht die Antwort")
    e.pruefe(len(cara.get(f"{BASE}/api/galerie/{g_alle['id']}/worte"
                          ).json()["worte"]) == 1,
             "Cara nicht - sie steht nicht in diesem Faden")
    e.pruefe(anna.post(f"{BASE}/api/galerie/{g_alle['id']}/worte",
                       json={"text": "Hallo?", "mit_id": 9999}
                       ).status_code == 400,
             "in einen erfundenen Faden geht es nicht")
    e.pruefe(anna.post(f"{BASE}/api/galerie/{g_alle['id']}/worte",
                       json={"text": "an mich"}).status_code == 400,
             "und ohne Gegenueber auch nicht")

    meins = bert.get(f"{BASE}/api/galerie/{g_alle['id']}/worte").json()["worte"]
    meins = [w for w in meins if w["meins"]][0]
    e.pruefe(cara.delete(f"{BASE}/api/galerie/worte/{meins['id']}"
                         ).status_code == 403,
             "Cara kann Berts Kommentar nicht loeschen")
    e.pruefe(anna.delete(f"{BASE}/api/galerie/worte/{meins['id']}"
                         ).status_code == 403,
             "Anna ebenso wenig - es ist nicht ihr Text")
    e.pruefe(bert.delete(f"{BASE}/api/galerie/worte/{meins['id']}"
                         ).status_code == 200,
             "Bert selbst schon")

    e.abschnitt("Die Zahl der Kommentare verraet nichts")
    caras_sicht = [x for x in cara.get(f"{BASE}/api/galerie/{anna_id}").json()
                   ["eintraege"] if x["id"] == g_alle["id"]][0]
    e.pruefe(caras_sicht["worte"] == 1,
             f"Cara zaehlt nur ihren eigenen = {caras_sicht['worte']}")
    annas_sicht = [x for x in anna.get(f"{BASE}/api/galerie/{anna_id}").json()
                   ["eintraege"] if x["id"] == g_alle["id"]][0]
    e.pruefe(annas_sicht["worte"] == 2,
             f"Anna sieht alle = {annas_sicht['worte']}")

    e.abschnitt("Freigabe aendern und zuruecknehmen")
    r = anna.post(f"{BASE}/api/galerie", json={"file_id": bild["id"],
                                               "art": "alle"})
    e.pruefe(r.json()["id"] == g_freunde["id"],
             "dieselbe Datei bleibt derselbe Eintrag")
    e.pruefe(len(cara.get(f"{BASE}/api/galerie/{anna_id}").json()
                 ["eintraege"]) == 2,
             "jetzt sieht Cara beide")
    e.pruefe(r.json()["herzen"] == 1, "das Herz bleibt dabei erhalten")
    e.pruefe(bert.delete(f"{BASE}/api/galerie/{g_freunde['id']}"
                         ).status_code == 403,
             "Bert kann die Freigabe nicht zuruecknehmen")
    e.pruefe(anna.delete(f"{BASE}/api/galerie/{g_freunde['id']}"
                         ).status_code == 200,
             "Anna schon")
    e.pruefe(len(cara.get(f"{BASE}/api/galerie/{anna_id}").json()
                 ["eintraege"]) == 1,
             "danach steht es nicht mehr da")
    e.pruefe(anna.get(f"{BASE}/files/{bild['id']}").status_code == 200,
             "die Datei selbst bleibt")

    e.abschnitt("Die Medienliste kennt den Stand")
    meine = anna.get(f"{BASE}/api/media").json()
    berg = [m for m in meine if m["id"] == zweites["id"]][0]
    e.pruefe(berg["galerie"] == "alle", f"das freigegebene = {berg['galerie']}")
    e.pruefe(berg["galerie_id"] == g_alle["id"], "mit seiner Kennung")
    urlaub = [m for m in meine if m["id"] == bild["id"]][0]
    e.pruefe(urlaub["galerie"] is None, "das zurueckgenommene nicht mehr")
    beim_anderen = [m for m in bert.get(f"{BASE}/api/media").json()
                    if m["id"] == zweites["id"]]
    e.pruefe(beim_anderen and beim_anderen[0]["galerie"] is None,
             "und bei Bert steht nichts - es ist nicht seine Freigabe")

    e.abschnitt("Mit der Datei geht auch der Eintrag")
    anna.post(f"{BASE}/api/galerie", json={"file_id": fremd["id"],
                                           "art": "alle"})
    anna.post(f"{BASE}/api/media/delete", json={"ids": [zweites["id"]]})
    e.pruefe(len(anna.get(f"{BASE}/api/galerie/{anna_id}").json()
                 ["eintraege"]) == 0,
             "die geloeschte Datei ist aus der Galerie verschwunden")
    e.pruefe(anna.get(f"{BASE}/api/galerie/{g_alle['id']}/worte"
                      ).status_code == 403,
             "und ihre Kommentare sind mit weg")

    e.abschnitt("Ein Bild direkt in die Galerie legen")
    # Ohne Umweg ueber eine Unterhaltung: hochladen und gleich freigeben
    direkt = hochladen(anna, "direkt.png", PNG, "image/png").json()
    r = anna.post(f"{BASE}/api/galerie", json={"file_id": direkt["id"],
                                               "art": "alle",
                                               "titel": "Ohne Chat"})
    e.pruefe(r.status_code == 200, f"das geht = {r.status_code}")
    direkt_g = r.json()["id"]
    e.pruefe(len(cara.get(f"{BASE}/api/galerie/{anna_id}").json()
                 ["eintraege"]) == 1, "Cara sieht es")
    e.pruefe(cara.get(f"{BASE}/files/{direkt['id']}").status_code == 200,
             "und kann es laden, obwohl es in keiner Unterhaltung steht")

    e.abschnitt("Die Freigabe haelt die Datei fest")
    haltbar = hochladen(anna, "haltbar.png", PNG, "image/png").json()
    msg = senden_mit_antwort(anna, raum, "", datei=haltbar["id"])
    anna.post(f"{BASE}/api/galerie", json={"file_id": haltbar["id"],
                                           "art": "alle"})
    e.pruefe(anna.delete(f"{BASE}/api/messages/{msg['id']}").status_code == 200,
             "die Nachricht laesst sich loeschen")
    e.pruefe(anna.get(f"{BASE}/files/{haltbar['id']}").status_code == 200,
             "die Datei bleibt - die Freigabe haelt sie")
    e.pruefe(len([x for x in anna.get(f"{BASE}/api/galerie/{anna_id}").json()
                  ["eintraege"] if x["file_id"] == haltbar["id"]]) == 1,
             "und sie steht weiter in der Galerie")

    e.abschnitt("Zuruecknehmen raeumt ein einsames Bild weg")
    e.pruefe(anna.delete(f"{BASE}/api/galerie/{direkt_g}").status_code == 200,
             "die Freigabe laesst sich zuruecknehmen")
    e.pruefe(anna.get(f"{BASE}/files/{direkt['id']}").status_code == 404,
             "das direkt hochgeladene Bild ist fort - nichts hielt es mehr")
    uebrig = [x for x in anna.get(f"{BASE}/api/galerie/{anna_id}").json()
              ["eintraege"] if x["file_id"] == haltbar["id"]][0]
    anna.delete(f"{BASE}/api/galerie/{uebrig['id']}")
    e.pruefe(anna.get(f"{BASE}/files/{haltbar['id']}").status_code == 404,
             "das aus der Unterhaltung ebenfalls - dort war die Nachricht ja weg")

    e.abschnitt("Aus der Galerie heraus loeschen")
    weg = hochladen(anna, "weg.png", PNG, "image/png").json()
    anna.post(f"{BASE}/api/galerie", json={"file_id": weg["id"], "art": "alle"})
    eintrag = [x for x in anna.get(f"{BASE}/api/galerie/{anna_id}").json()
               ["eintraege"] if x["file_id"] == weg["id"]][0]
    bert.post(f"{BASE}/api/galerie/{eintrag['id']}/herz")
    bert.post(f"{BASE}/api/galerie/{eintrag['id']}/worte", json={"text": "schoen"})
    e.pruefe(bert.post(f"{BASE}/api/media/delete",
                       json={"ids": [weg["id"]]}).json()["geloescht"] == 0,
             "Bert kann Annas Bild nicht loeschen")
    r = anna.post(f"{BASE}/api/media/delete", json={"ids": [weg["id"]]})
    e.pruefe(r.json()["geloescht"] == 1, f"Anna schon = {r.json()}")
    e.pruefe(not [x for x in anna.get(f"{BASE}/api/galerie/{anna_id}").json()
                  ["eintraege"] if x["file_id"] == weg["id"]],
             "danach ist es aus der Galerie fort")
    e.pruefe(anna.get(f"{BASE}/files/{weg['id']}").status_code == 404,
             "und die Datei vom Server")
    e.pruefe(anna.get(f"{BASE}/api/galerie/{eintrag['id']}/worte"
                      ).status_code == 403,
             "Herzen und Kommentare gehen mit")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    for pfad, methode in ((f"/api/galerie/{anna_id}", requests.get),
                          ("/api/galerie", requests.post),
                          (f"/api/galerie/{g_alle['id']}/herz", requests.post),
                          (f"/api/galerie/{g_alle['id']}/worte", requests.get)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad} weist Fremde ab = {r.status_code}")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
