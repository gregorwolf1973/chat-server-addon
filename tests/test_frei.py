"""Termine ohne Unterhaltung - ausgewaehlte Freunde oder ein Umkreis.
Dazu die abschaltbaren Geburtstagserinnerungen.

Braucht einen frisch gestarteten Server auf einem leeren DATA_DIR.
"""
import os
import sys

import requests

from helpers import (BASE, Ergebnis, als_admin, anmelden, eigene_id,
                     verbindungen_schliessen)

# Karlsruhe, Ettlingen (rund 8 km), Mannheim (rund 53 km)
KARLSRUHE = {"lat": 49.0094, "lon": 8.4044}
ETTLINGEN = {"lat": 48.9400, "lon": 8.4050}
MANNHEIM = {"lat": 49.4875, "lon": 8.4660}


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

    # Anna ist mit Bert und Cara befreundet, der Administrator mit niemandem
    for wer, wer_id in ((bert, bert_id), (cara, cara_id)):
        anna.post(f"{BASE}/api/freunde/{wer_id}")
        wer.post(f"{BASE}/api/freunde/{anna_id}")

    def termine(sitzung, ort=None):
        ziel = f"{BASE}/api/events"
        if ort:
            ziel += f"?lat={ort['lat']}&lon={ort['lon']}"
        return sitzung.get(ziel).json()

    e.abschnitt("Ein Termin fuer ausgewaehlte Freunde")
    r = anna.post(f"{BASE}/api/events", json={
        "titel": "Kino am Freitag", "sicht": "freunde", "gaeste": [bert_id]})
    e.pruefe(r.status_code == 200, f"laesst sich anlegen = {r.status_code}")
    ev_id = r.json()["event_id"]
    e.pruefe([t["titel"] for t in termine(bert)] == ["Kino am Freitag"],
             "Bert ist eingeladen und sieht ihn")
    e.pruefe(termine(cara) == [],
             "Cara nicht - sie wurde nicht ausgewaehlt")
    e.pruefe([t["titel"] for t in termine(anna)] == ["Kino am Freitag"],
             "Anna sieht ihren eigenen")
    e.pruefe(termine(admin) == [],
             "der Administrator auch nicht - er ist kein Freund")

    daten = termine(bert)[0]
    e.pruefe(daten["sicht"] == "freunde", "die Art steht dabei")
    e.pruefe(daten["room_id"] == 0, "und keine Unterhaltung")
    e.pruefe(daten["gaeste"] == [bert_id], f"mit der Gaesteliste = {daten['gaeste']}")

    e.abschnitt("Wer nicht dabei ist, kommt auch nicht heran")
    e.pruefe(cara.get(f"{BASE}/api/events/{ev_id}").status_code == 403,
             "Cara kann ihn nicht einzeln abrufen")
    e.pruefe(cara.post(f"{BASE}/api/events/{ev_id}/antwort",
                       json={"antwort": "ja"}).status_code == 403,
             "und nicht zusagen")
    e.pruefe(bert.post(f"{BASE}/api/events/{ev_id}/antwort",
                       json={"antwort": "ja"}).status_code == 200,
             "Bert schon")

    e.abschnitt("Nur Freunde lassen sich einladen")
    r = anna.post(f"{BASE}/api/events", json={
        "titel": "Mit einem Fremden", "sicht": "freunde", "gaeste": [admin_id]})
    e.pruefe(r.status_code == 400,
             f"der Administrator ist kein Freund von Anna = {r.status_code}")
    e.pruefe(anna.post(f"{BASE}/api/events", json={
        "titel": "Ohne alle", "sicht": "freunde", "gaeste": []}
        ).status_code == 400, "und ganz ohne Auswahl geht es auch nicht")
    e.pruefe(anna.post(f"{BASE}/api/events", json={
        "titel": "Unfug", "sicht": "welt"}).status_code == 400,
        "eine erfundene Art wird abgewiesen")
    e.pruefe(anna.post(f"{BASE}/api/events", json={
        "titel": "", "sicht": "freunde", "gaeste": [bert_id]}
        ).status_code == 400, "ohne Titel ebenso")

    e.abschnitt("Die Gaesteliste aendert nur der Gastgeber")
    e.pruefe(bert.patch(f"{BASE}/api/events/{ev_id}",
                        json={"gaeste": [bert_id, cara_id]}).status_code == 403,
             "Bert darf nicht umbesetzen")
    r = anna.patch(f"{BASE}/api/events/{ev_id}",
                   json={"gaeste": [bert_id, cara_id]})
    e.pruefe(r.status_code == 200, f"Anna schon = {r.status_code}")
    e.pruefe(len(termine(cara)) == 1, "jetzt sieht Cara ihn auch")
    anna.patch(f"{BASE}/api/events/{ev_id}", json={"gaeste": [bert_id]})
    e.pruefe(termine(cara) == [], "und nach dem Ausladen nicht mehr")
    e.pruefe(anna.patch(f"{BASE}/api/events/{ev_id}",
                        json={"gaeste": []}).status_code == 400,
             "ganz leeren geht nicht")

    e.abschnitt("Ein Termin fuer alle im Umkreis")
    e.pruefe(anna.post(f"{BASE}/api/events", json={
        "titel": "Ohne Ort", "sicht": "umkreis", "umkreis_km": 10}
        ).status_code == 400, "ohne Ort wird er abgewiesen")
    r = anna.post(f"{BASE}/api/events", json={
        "titel": "Hoffest", "sicht": "umkreis", "umkreis_km": 10,
        "lat": KARLSRUHE["lat"], "lon": KARLSRUHE["lon"]})
    e.pruefe(r.status_code == 200, f"mit Ort geht er = {r.status_code}")
    hof_id = r.json()["event_id"]

    e.pruefe(termine(cara) == [],
             "ohne Standort sieht Cara ihn nicht - der Server weiss nicht, wo sie ist")
    nah = [t["titel"] for t in termine(cara, ETTLINGEN)]
    e.pruefe(nah == ["Hoffest"], f"aus Ettlingen heraus schon = {nah}")
    fern = [t["titel"] for t in termine(cara, MANNHEIM)]
    e.pruefe(fern == [], f"aus Mannheim nicht mehr = {fern}")
    e.pruefe(len(termine(admin, ETTLINGEN)) == 1,
             "auch wer kein Freund ist, sieht ihn - der Umkreis zaehlt")

    e.abschnitt("Der Umkreis zaehlt auch beim Zugriff")
    e.pruefe(cara.get(f"{BASE}/api/events/{hof_id}").status_code == 403,
             "ohne Standort kein Zugriff")
    e.pruefe(cara.get(f"{BASE}/api/events/{hof_id}"
                      f"?lat={ETTLINGEN['lat']}&lon={ETTLINGEN['lon']}"
                      ).status_code == 200, "aus der Naehe schon")
    e.pruefe(cara.get(f"{BASE}/api/events/{hof_id}"
                      f"?lat={MANNHEIM['lat']}&lon={MANNHEIM['lon']}"
                      ).status_code == 403, "aus der Ferne nicht")

    e.abschnitt("Ein laufender Standort zaehlt genauso")
    raum = anna.post(f"{BASE}/api/rooms", json={
        "name": "Runde", "is_group": True, "members": [cara_id]}).json()["id"]
    cara.post(f"{BASE}/api/live", json={"room_id": raum, "minuten": 30,
                                        "lat": ETTLINGEN["lat"],
                                        "lon": ETTLINGEN["lon"]})
    e.pruefe(len([t for t in termine(cara) if t["titel"] == "Hoffest"]) == 1,
             "wer teilt, sieht die Einladung ohne weiteres Zutun")
    cara.post(f"{BASE}/api/live", json={"room_id": raum, "minuten": 30,
                                        "lat": MANNHEIM["lat"],
                                        "lon": MANNHEIM["lon"]})
    e.pruefe([t for t in termine(cara) if t["titel"] == "Hoffest"] == [],
             "aus Mannheim heraus nicht mehr")
    cara.delete(f"{BASE}/api/live", json={})

    e.abschnitt("Der Umkreis hat eine Obergrenze")
    r = anna.post(f"{BASE}/api/events", json={
        "titel": "Viel zu weit", "sicht": "umkreis", "umkreis_km": 500,
        "lat": KARLSRUHE["lat"], "lon": KARLSRUHE["lon"]})
    weit = anna.get(f"{BASE}/api/events/{r.json()['event_id']}").json()
    e.pruefe(weit["umkreis_km"] == 25,
             f"mehr als 25 km gibt es nicht = {weit['umkreis_km']}")
    e.pruefe(termine(cara, MANNHEIM) == [],
             "und aus 53 km Entfernung bleibt es unsichtbar")

    e.abschnitt("Absagen bleibt beim Gastgeber")
    e.pruefe(bert.delete(f"{BASE}/api/events/{ev_id}").status_code == 403,
             "Bert kann den Termin nicht absagen")
    e.pruefe(anna.delete(f"{BASE}/api/events/{ev_id}").status_code == 200,
             "Anna schon")
    e.pruefe(termine(bert) == [], "danach steht er bei niemandem mehr")

    e.abschnitt("Geburtstagserinnerungen")
    anna.post(f"{BASE}/api/me/geburtstag", json={"geburtstag": "1980-05-17"})
    e.pruefe(bert.get(f"{BASE}/api/state").json()["me"]["geburtstage_an"] is True,
             "voreingestellt sind sie an")
    e.pruefe(len(bert.get(f"{BASE}/api/geburtstage").json()) >= 1,
             "Bert sieht Annas Geburtstag")
    r = bert.post(f"{BASE}/api/me/geburtstage-an", json={"an": False})
    e.pruefe(r.status_code == 200 and r.json()["an"] is False,
             f"sie lassen sich abschalten = {r.status_code}")
    e.pruefe(bert.get(f"{BASE}/api/geburtstage").json() == [],
             "danach ist die Liste leer")
    e.pruefe(bert.get(f"{BASE}/api/state").json()["me"]["geburtstage_an"] is False,
             "und der Startzustand sagt es")
    e.pruefe(len(anna.get(f"{BASE}/api/geburtstage").json()) >= 1,
             "bei Anna aendert das nichts - die Einstellung gehoert der Person")
    bert.post(f"{BASE}/api/me/geburtstage-an", json={"an": True})
    e.pruefe(len(bert.get(f"{BASE}/api/geburtstage").json()) >= 1,
             "und wieder einschalten geht")

    e.abschnitt("Ohne Anmeldung geht gar nichts")
    for pfad, methode in (("/api/events", requests.post),
                          ("/api/me/geburtstage-an", requests.post)):
        r = methode(BASE + pfad, json={}, allow_redirects=False)
        e.pruefe(r.status_code in (302, 401),
                 f"{pfad} weist Fremde ab = {r.status_code}")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    code = lauf()
    sys.stdout.flush()
    os._exit(code)
