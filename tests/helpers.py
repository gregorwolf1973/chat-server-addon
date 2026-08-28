"""Gemeinsames Handwerkszeug fuer die Tests."""
import io
import time

import requests

BASE = "http://127.0.0.1:8099"
ADMIN = ("admin", "test1234")

# Ein winziges, gueltiges PNG (1x1 Pixel).
PNG = (bytes.fromhex("89504e470d0a1a0a0000000d494844520000000100000001080600"
                     "00001f15c4890000000a49444154789c6300010000050001")
       + b"\x0d\x0a\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


class Ergebnis:
    """Sammelt Pruefungen und haelt fest, ob alle bestanden wurden."""

    def __init__(self):
        self.werte = []

    def pruefe(self, bedingung, text):
        bedingung = bool(bedingung)
        print(("  OK   " if bedingung else "  FEHL ") + text)
        self.werte.append(bedingung)
        return bedingung

    def abschnitt(self, titel):
        print(f"\n== {titel} ==")

    @property
    def alle_bestanden(self):
        return all(self.werte)

    def bilanz(self):
        print(f"\n{sum(self.werte)}/{len(self.werte)} Pruefungen bestanden")
        return 0 if self.alle_bestanden else 1


def anmelden(benutzer, passwort):
    """Gibt (Sitzung, Statuscode) zurueck. 302 heisst: Anmeldung geglueckt."""
    s = requests.Session()
    r = s.post(f"{BASE}/login", data={"username": benutzer, "password": passwort},
               allow_redirects=False)
    return s, r.status_code


def als_admin():
    s, code = anmelden(*ADMIN)
    assert code == 302, f"Der Administrator kam nicht hinein (Status {code})"
    return s


def eigene_id(sitzung):
    return sitzung.get(f"{BASE}/api/state").json()["me"]["id"]


def hochladen(sitzung, name, inhalt, mime):
    return sitzung.post(f"{BASE}/api/upload",
                        files={"file": (name, io.BytesIO(inhalt), mime)})


_verbindungen = {}


def verbindung(sitzung):
    """Eine offene Socket.IO-Verbindung je Sitzung.

    Fuer jede Nachricht neu zu verbinden waere unrealistisch - die Oberflaeche
    haelt eine Verbindung offen - und bringt den Entwicklungsserver bei
    schnellem Auf und Ab ins Straucheln.
    """
    import socketio

    if sitzung not in _verbindungen:
        cookie = "; ".join(f"{c.name}={c.value}" for c in sitzung.cookies)
        # Ohne reconnection=False versucht der Client nach einer
        # serverseitigen Trennung - etwa weil das Konto gesperrt wurde -
        # endlos neu zu verbinden und der Testlauf endet nie.
        sio = socketio.Client(reconnection=False)
        sio.connect(BASE, headers={"Cookie": cookie}, transports=["polling"],
                    wait_timeout=10)
        _verbindungen[sitzung] = sio
    return _verbindungen[sitzung]


def senden_mit_antwort(sitzung, raum, body="", datei=None, album=None, ort=None):
    """Wie senden(), gibt aber die Empfangsbestaetigung des Servers zurueck."""
    return verbindung(sitzung).call("send", {"room_id": raum, "body": body,
                                             "file_id": datei, "album": album,
                                             "ort": ort}, timeout=8)


def senden(sitzung, raum, body="", datei=None, warten=1.0):
    """Eine Nachricht ueber Socket.IO schicken - so wie die Oberflaeche es tut."""
    verbindung(sitzung).emit("send", {"room_id": raum, "body": body,
                                      "file_id": datei})
    time.sleep(warten)


def verbindungen_schliessen():
    for sio in _verbindungen.values():
        try:
            sio.disconnect()
        except Exception:  # noqa: BLE001
            pass
    _verbindungen.clear()
