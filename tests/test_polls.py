"""Gruppenabstimmungen: anlegen, abstimmen, auswerten."""
import os
import sys

from helpers import (BASE, Ergebnis, als_admin, anmelden, eigene_id,
                     verbindungen_schliessen)


def main():
    e = Ergebnis()
    admin = als_admin()
    admin_id = eigene_id(admin)
    for n in ("eva", "finn"):
        admin.post(f"{BASE}/api/users", json={"username": n, "display_name": n.capitalize(),
                                              "password": "start123"})
    eva, _ = anmelden("eva", "start123")
    finn, _ = anmelden("finn", "start123")
    eva_id, finn_id = eigene_id(eva), eigene_id(finn)
    gruppe = admin.post(f"{BASE}/api/rooms", json={
        "name": "Ausflug", "is_group": True,
        "members": [eva_id, finn_id]}).json()["id"]
    fremd = admin.post(f"{BASE}/api/rooms", json={
        "name": "Ohne Eva", "is_group": True, "members": []}).json()["id"]

    e.abschnitt("Anlegen")
    r = admin.post(f"{BASE}/api/rooms/{gruppe}/poll",
                   json={"frage": "Wann treffen wir uns?",
                         "optionen": ["Samstag", "Sonntag", "Gar nicht"]})
    e.pruefe(r.status_code == 200, f"Abstimmung anlegen = {r.status_code}")
    poll_id = r.json()["poll_id"]
    e.pruefe(admin.post(f"{BASE}/api/rooms/{gruppe}/poll",
                        json={"frage": "", "optionen": ["a", "b"]}).status_code == 400,
             "ohne Frage geht es nicht")
    e.pruefe(admin.post(f"{BASE}/api/rooms/{gruppe}/poll",
                        json={"frage": "?", "optionen": ["nur eine"]}).status_code == 400,
             "eine einzige Antwort ist zu wenig")
    e.pruefe(eva.post(f"{BASE}/api/rooms/{fremd}/poll",
                      json={"frage": "?", "optionen": ["a", "b"]}).status_code == 403,
             "in fremden Unterhaltungen geht es gar nicht")

    e.abschnitt("Die Abstimmung steht im Verlauf")
    nachrichten = eva.get(f"{BASE}/api/rooms/{gruppe}/messages").json()
    letzte = nachrichten[-1]
    e.pruefe(letzte["poll"] and letzte["poll"]["frage"] == "Wann treffen wir uns?",
             "als eigene Nachricht mit Frage")
    e.pruefe(len(letzte["poll"]["optionen"]) == 3, "mit allen drei Antworten")
    e.pruefe(letzte["poll"]["teilnehmer"] == 0, "noch hat niemand gestimmt")
    optionen = {o["text"]: o["id"] for o in letzte["poll"]["optionen"]}

    e.abschnitt("Abstimmen")
    r = eva.post(f"{BASE}/api/polls/{poll_id}/vote",
                 json={"option_id": optionen["Samstag"]})
    daten = r.json()
    e.pruefe(r.status_code == 200, f"Stimme abgeben = {r.status_code}")
    samstag = next(o for o in daten["optionen"] if o["text"] == "Samstag")
    e.pruefe(samstag["stimmen"] == 1 and samstag["meine"],
             "die eigene Stimme ist gezaehlt und markiert")
    e.pruefe(daten["teilnehmer"] == 1, "ein Teilnehmer")
    e.pruefe([w["name"] for w in samstag["wer"]] == ["Eva"],
             f"und namentlich sichtbar: {[w['name'] for w in samstag['wer']]}")

    r = finn.post(f"{BASE}/api/polls/{poll_id}/vote",
                  json={"option_id": optionen["Samstag"]})
    samstag = next(o for o in r.json()["optionen"] if o["text"] == "Samstag")
    e.pruefe(samstag["stimmen"] == 2, "Finn stimmt derselben Antwort zu")
    e.pruefe(not next(o for o in eva.get(f"{BASE}/api/polls/{poll_id}").json()["optionen"]
                      if o["text"] == "Sonntag")["meine"],
             "Evas Sicht markiert nur ihre eigene Wahl")

    e.abschnitt("Einfachwahl ersetzt, nochmal tippen nimmt zurueck")
    r = eva.post(f"{BASE}/api/polls/{poll_id}/vote",
                 json={"option_id": optionen["Sonntag"]})
    daten = r.json()
    e.pruefe(next(o for o in daten["optionen"] if o["text"] == "Samstag")["stimmen"] == 1,
             "die alte Stimme ist weg")
    e.pruefe(next(o for o in daten["optionen"] if o["text"] == "Sonntag")["meine"],
             "die neue steht")
    r = eva.post(f"{BASE}/api/polls/{poll_id}/vote",
                 json={"option_id": optionen["Sonntag"]})
    daten = r.json()
    e.pruefe(not next(o for o in daten["optionen"] if o["text"] == "Sonntag")["meine"],
             "nochmal tippen nimmt die Stimme zurueck")
    e.pruefe(daten["teilnehmer"] == 1, "danach zaehlt nur noch Finn")

    e.abschnitt("Mehrfachwahl")
    r = admin.post(f"{BASE}/api/rooms/{gruppe}/poll",
                   json={"frage": "Was bringen wir mit?", "mehrfach": True,
                         "optionen": ["Salat", "Kuchen", "Getraenke"]})
    poll2 = r.json()["poll_id"]
    opt2 = {o["text"]: o["id"] for o in eva.get(f"{BASE}/api/polls/{poll2}").json()["optionen"]}
    eva.post(f"{BASE}/api/polls/{poll2}/vote", json={"option_id": opt2["Salat"]})
    daten = eva.post(f"{BASE}/api/polls/{poll2}/vote",
                     json={"option_id": opt2["Kuchen"]}).json()
    gewaehlt = [o["text"] for o in daten["optionen"] if o["meine"]]
    e.pruefe(sorted(gewaehlt) == ["Kuchen", "Salat"],
             f"beide Antworten bleiben stehen: {gewaehlt}")
    e.pruefe(daten["teilnehmer"] == 1,
             "eine Person zaehlt trotz zweier Stimmen einmal")

    e.abschnitt("Schutz")
    e.pruefe(eva.post(f"{BASE}/api/polls/{poll_id}/vote",
                      json={"option_id": opt2["Salat"]}).status_code == 400,
             "eine Antwort aus einer anderen Frage wird abgewiesen")
    e.pruefe(eva.post(f"{BASE}/api/polls/{poll_id}/vote",
                      json={"option_id": "abc"}).status_code == 400,
             "Unsinn statt einer Kennung ebenfalls")
    aussen, _ = anmelden("admin", "test1234")
    admin.post(f"{BASE}/api/rooms/{gruppe}/leave")
    e.pruefe(aussen.get(f"{BASE}/api/polls/{poll_id}").status_code == 403,
             "wer die Unterhaltung verlassen hat, sieht die Abstimmung nicht mehr")

    void = admin_id
    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    os._exit(ergebnis)
