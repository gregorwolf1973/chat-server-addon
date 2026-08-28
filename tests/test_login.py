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

    verbindungen_schliessen()
    return e.bilanz()


if __name__ == "__main__":
    ergebnis = main()
    sys.stdout.flush()
    os._exit(ergebnis)
