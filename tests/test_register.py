"""Selbstregistrierung: Antrag, Freigabe, Ablehnung und die Spam-Bremse."""
import os
import sys

import requests

from helpers import BASE, Ergebnis, als_admin, anmelden, verbindungen_schliessen


def antrag(username="neuling", display="Neuer Nachbar", passwort="start123",
           email="neu@example.org", phone="", note="Wohne nebenan",
           sitzung=None, zustimmung="on", geburtstag=""):
    s = sitzung or requests.Session()
    daten = {"username": username, "display_name": display,
             "password": passwort, "email": email, "phone": phone,
             "note": note, "geburtstag": geburtstag}
    # Ohne den Haken legt der Server kein Konto an - die Reihen hier
    # setzen ihn also, ausser sie pruefen genau das Gegenteil.
    if zustimmung:
        daten["zustimmung"] = zustimmung
    return s.post(f"{BASE}/register", data=daten, allow_redirects=False)


def main():
    e = Ergebnis()
    admin = als_admin()

    e.abschnitt("Die Seite ist offen erreichbar")
    r = requests.get(f"{BASE}/register")
    e.pruefe(r.status_code == 200 and "Zugang beantragen" in r.text,
             f"GET /register ohne Anmeldung = {r.status_code}")
    r = requests.get(f"{BASE}/login")
    e.pruefe("Zugang beantragen" in r.text,
             "die Anmeldeseite verweist auf die Registrierung")

    e.abschnitt("Pflichtangaben")
    e.pruefe("mindestens 6 Zeichen" in antrag(passwort="abc").text,
             "zu kurzes Passwort wird abgewiesen")
    e.pruefe("erreichen" in antrag(username="ohnekontakt", email="", phone="").text,
             "ohne E-Mail und Telefon geht es nicht")
    e.pruefe("weshalb" in antrag(username="ohnegrund", note="").text.lower(),
             "ohne Begruendung geht es nicht")
    e.pruefe("vergeben" in antrag(username="homeassistant").text,
             "Systemnamen sind gesperrt")

    e.abschnitt("Antrag stellen")
    r = antrag()
    e.pruefe("unterwegs" in r.text, "der Antrag wird angenommen")
    e.pruefe("gibt es schon" in antrag(username="neuling", email="x@y.de").text,
             "derselbe Benutzername ein zweites Mal wird abgewiesen")

    e.abschnitt("Vor der Freigabe kommt niemand hinein")
    s, code = anmelden("neuling", "start123")
    e.pruefe(code == 200, "die Anmeldung schlaegt fehl")
    e.pruefe("freigegeben" in s.post(f"{BASE}/login",
                                     data={"username": "neuling",
                                           "password": "start123"}).text,
             "und nennt den Grund")
    sichtbar = [u["username"] for u in admin.get(f"{BASE}/api/state").json()["users"]]
    e.pruefe("neuling" not in sichtbar,
             "der Antragsteller taucht nicht in der Nutzerliste auf")

    e.abschnitt("Der Administrator sieht den Antrag")
    liste = admin.get(f"{BASE}/api/users").json()
    eintrag = next((u for u in liste if u["username"] == "neuling"), None)
    e.pruefe(eintrag is not None, "der Antrag steht in der Verwaltung")
    e.pruefe(eintrag and eintrag["pending"], "er ist als wartend gekennzeichnet")
    e.pruefe(eintrag and eintrag["email"] == "neu@example.org",
             f"die E-Mail steht dabei: {eintrag['email'] if eintrag else '-'}")
    e.pruefe(eintrag and eintrag["note"] == "Wohne nebenan",
             "die Begruendung steht dabei")
    e.pruefe(liste[0]["pending"], "Antraege stehen oben in der Liste")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["antraege"] == 1,
             "und die Zahl am Zahnrad steht auf eins")

    e.abschnitt("Freigeben")
    uid = eintrag["id"]
    r = admin.post(f"{BASE}/api/users/{uid}/approve")
    e.pruefe(r.status_code == 200, f"Freigabe = {r.status_code}")
    e.pruefe(not r.json()["pending"] and r.json()["active"],
             "das Konto ist jetzt aktiv")
    e.pruefe(anmelden("neuling", "start123")[1] == 302,
             "und die Anmeldung gelingt")
    e.pruefe(admin.post(f"{BASE}/api/users/{uid}/approve").status_code == 400,
             "ein zweites Freigeben wird abgewiesen")
    sichtbar = [u["username"] for u in admin.get(f"{BASE}/api/state").json()["users"]]
    e.pruefe("neuling" in sichtbar, "jetzt taucht das Konto in der Nutzerliste auf")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["antraege"] == 0,
             "und die Zahl am Zahnrad ist wieder weg")
    e.pruefe(anmelden("neuling", "start123")[0]
             .get(f"{BASE}/api/state").json()["me"]["antraege"] == 0,
             "wer kein Administrator ist, sieht die Zahl nie")

    e.abschnitt("Ablehnen entfernt den Antrag")
    antrag(username="unerwuenscht", display="Jemand", email="a@b.de",
           note="Nur so")
    uid2 = next(u["id"] for u in admin.get(f"{BASE}/api/users").json()
                if u["username"] == "unerwuenscht")
    e.pruefe(admin.delete(f"{BASE}/api/users/{uid2}").status_code == 200,
             "Ablehnen loescht das Konto")
    e.pruefe("unerwuenscht" not in [u["username"] for u in
                                    admin.get(f"{BASE}/api/users").json()],
             "danach ist es fort")

    e.abschnitt("Bremse gegen Massenantraege")
    eigene = requests.Session()
    codes = [antrag(username=f"flut{i}", email=f"f{i}@x.de", sitzung=eigene).text
             for i in range(4)]
    e.pruefe("warte eine Stunde" in codes[-1],
             "nach mehreren Antraegen wird gebremst")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    os._exit(ergebnis)
