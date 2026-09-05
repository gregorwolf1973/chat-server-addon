"""Die Anmeldung und ihre Bremse gegen Durchprobieren."""
import os
import sys

import requests

from helpers import BASE, Ergebnis, als_admin, anmelden, verbindungen_schliessen


def main():
    e = Ergebnis()
    admin = als_admin()
    admin.post(f"{BASE}/api/users", json={"username": "opfer",
                                          "display_name": "Opfer",
                                          "password": "richtig123"})

    e.abschnitt("Anmelden")
    e.pruefe(anmelden("opfer", "richtig123")[1] == 302, "mit richtigem Passwort")
    e.pruefe(anmelden("OPFER", "richtig123")[1] == 302, "Schreibweise ist egal")
    e.pruefe(anmelden("opfer", "falsch")[1] == 200, "falsches Passwort scheitert")

    e.abschnitt("Nach zu vielen Fehlversuchen wird gebremst")
    # Eine eigene Sitzung, damit die Zaehlung sauber beginnt
    codes = []
    for i in range(9):
        s = requests.Session()
        r = s.post(f"{BASE}/login",
                   data={"username": "opfer", "password": f"daneben{i}"},
                   allow_redirects=False)
        codes.append(r.status_code)
    e.pruefe(429 in codes, f"irgendwann kommt 429: {codes}")
    e.pruefe(codes.index(429) >= 5,
             f"aber nicht schon beim ersten Versuch (ab Nr. {codes.index(429) + 1})")

    r = requests.post(f"{BASE}/login",
                      data={"username": "opfer", "password": "richtig123"},
                      allow_redirects=False)
    e.pruefe(r.status_code == 429,
             "auch das richtige Passwort wird waehrend der Sperre abgewiesen")
    e.pruefe("Fehlversuche" in r.text, "und der Grund steht auf der Seite")

    e.abschnitt("Andere Konten bleiben unbehelligt")
    # Wichtig hinter Tunnel und Reverse Proxy: dort haben alle dieselbe
    # Adresse. Eine Sperre je Konto darf niemanden sonst treffen.
    e.pruefe(anmelden("admin", "test1234")[1] == 302,
             "der Administrator kommt weiterhin hinein")
    admin.post(f"{BASE}/api/users", json={"username": "dritte",
                                          "display_name": "Dritte",
                                          "password": "auchgut123"})
    e.pruefe(anmelden("dritte", "auchgut123")[1] == 302,
             "und ein frisches Konto ebenfalls")

    e.abschnitt("Passwort vergessen")
    r = requests.get(f"{BASE}/passwort-vergessen")
    e.pruefe(r.status_code == 200, f"die Seite ist offen = {r.status_code}")
    e.pruefe("Passwort vergessen" in r.text, "und traegt die Ueberschrift")
    e.pruefe('name="username"' in r.text, "mit einem Feld fuer den Namen")
    # Der Verweis steht ueber zwei Zeilen - deshalb auf die Adresse pruefen
    e.pruefe("passwort-vergessen" in requests.get(f"{BASE}/login").text,
             "die Anmeldeseite verweist darauf")

    # Drei Bitten je Stunde und Adresse sind erlaubt; die vierte soll bremsen.
    # Deshalb sind die Schritte hier so geordnet, dass sie mit dreien
    # auskommen.
    e.pruefe(requests.post(f"{BASE}/passwort-vergessen",
                           data={"username": "opfer"}).status_code == 200,
             "eine Bitte laesst sich stellen")
    bitten = admin.get(f"{BASE}/api/passwort-bitten").json()
    e.pruefe(len(bitten) == 1, f"der Administrator sieht sie = {len(bitten)}")
    e.pruefe(bitten and bitten[0]["username"] == "opfer", "mit dem Namen")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["bitten"] == 1,
             "und die Zahl am Zahnrad steht auf eins")
    opfer_id = bitten[0]["user_id"]

    # Ein eigenes Konto fuer die Rechtefrage - "opfer" ist von der Bremse
    # weiter oben in dieser Reihe noch gesperrt.
    admin.post(f"{BASE}/api/users", json={"username": "neugier",
                                          "display_name": "Neugier",
                                          "password": "start123"})
    gast, code = anmelden("neugier", "start123")
    e.pruefe(code == 302, f"das Testkonto kommt hinein = {code}")
    e.pruefe(gast.get(f"{BASE}/api/passwort-bitten").status_code == 403,
             "wer kein Administrator ist, sieht die Liste nicht")
    e.pruefe(gast.delete(f"{BASE}/api/passwort-bitten/{opfer_id}"
                         ).status_code == 403, "und kann sie nicht abhaken")

    e.pruefe(admin.delete(f"{BASE}/api/passwort-bitten/{opfer_id}"
                          ).status_code == 200, "der Administrator hakt sie ab")
    e.pruefe(admin.get(f"{BASE}/api/passwort-bitten").json() == [], "und sie ist weg")

    # Zweite Bitte: diesmal raeumt das neue Passwort sie ab
    e.pruefe(requests.post(f"{BASE}/passwort-vergessen",
                           data={"username": "opfer"}).status_code == 200,
             "eine zweite Bitte geht auch")
    e.pruefe(len(admin.get(f"{BASE}/api/passwort-bitten").json()) == 1,
             "sie steht wieder da")
    e.pruefe(admin.post(f"{BASE}/api/users/{opfer_id}/password",
                        json={"password": "ganzneu123"}).status_code == 200,
             "der Administrator setzt ein neues Passwort")
    e.pruefe(admin.get(f"{BASE}/api/passwort-bitten").json() == [],
             "damit ist die Bitte erledigt")
    e.pruefe(admin.get(f"{BASE}/api/state").json()["me"]["bitten"] == 0,
             "und die Zahl wieder weg")

    # Dritte Bitte: ein erfundener Name darf nicht zu unterscheiden sein
    r3 = requests.post(f"{BASE}/passwort-vergessen",
                       data={"username": "gibtesnicht"})
    e.pruefe(r3.status_code == 200, "ein erfundener Name wird angenommen")
    e.pruefe("Danke" in r3.text,
             "mit derselben Antwort wie ein echter - sonst liesse sich raten,"
             " welche Namen es gibt")
    e.pruefe(admin.get(f"{BASE}/api/passwort-bitten").json() == [],
             "angelegt wird dabei nichts")

    e.abschnitt("Auch die Bitten sind gebremst")
    vierte = requests.post(f"{BASE}/passwort-vergessen",
                           data={"username": "opfer"})
    e.pruefe(vierte.status_code == 429,
             f"die vierte in einer Stunde wird gebremst = {vierte.status_code}")

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    os._exit(ergebnis)
