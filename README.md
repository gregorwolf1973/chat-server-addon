# Chat Server — selbstgehosteter Messenger als Home-Assistant-Add-on

Ein Messenger für Familie, WG oder Verein, der auf der eigenen Hardware läuft.
Keine Konten bei fremden Anbietern, keine Telefonnummern, keine Werbung. Alles
liegt in `/data` auf dem Gerät, auf dem Home Assistant läuft — auch auf einem
Raspberry Pi.

[![Repository zu Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgregorwolf1973%2Fchat-server-addon)

🇬🇧 [This page in English](./README.en.md)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

> **Sprache:** Deutsch und Englisch. Umschaltbar in den Einstellungen; ohne
> Wahl richtet sich der Chat nach dem Browser.

---

## Was er kann

**Unterhalten**
* Direktchats und Gruppen, Antworten mit Zitat, Weiterleiten, Löschen
* Bilder, Videos, Tondateien und Anhänge (Voreinstellung 25 MB, bis 200
  einstellbar); mehrere Bilder werden zu einem Album
* Emoji-Auswahl, Online-Anzeige, „schreibt gerade", Ungelesen-Zähler
* Volltextsuche über den Verlauf — in einer Unterhaltung oder in allen
* Sprachnachrichten: Knopf gedrückt halten, loslassen schickt ab

**Reden und sehen**
* Sprach- und Videoanrufe, auch als Gruppenrunde mit bis zu sechs Personen
* Läuft direkt von Gerät zu Gerät (WebRTC); der Server vermittelt nur
* Klingelton wählbar, Stummschaltung je Person und Gruppe

**Verabreden**
* Einladungen mit Ort, Bild, Merkmalen und Zu-/Absage
* Termine auch ohne Unterhaltung — für ausgewählte Freunde oder für alle im
  Umkreis von bis zu 25 km
* Geburtstage aus dem eigenen Kreis, abschaltbar

**Zeigen, wo etwas los ist**
* Live-Karte mit Standortfreigaben, Einladungen und Empfehlungen
* Standort teilen an eine Unterhaltung, an alle Freunde oder an alle in der
  Nähe — immer mit Ablaufzeit
* Empfehlungen (Kino, Kneipe, Wanderung …) mit Sternen und Entfernungsfilter
* „Worauf ich Lust hätte" — kurze Stimmungsmeldungen mit „ich mach mit"

**Bilder über die Unterhaltung hinaus**
* Persönliche Galerie: freigeben für Freunde oder für alle
* Herzen zählt jeder, **Kommentare bleiben ein Zwiegespräch** zwischen der
  Person und dem Schreibenden
* Bildschirmfüllende Medienschau mit Wischen und Zeitleiste

**Aus Home Assistant heraus**
* `POST /api/notify` schickt Nachrichten aus Automationen in eine Gruppe oder
  an eine Person — „Waschmaschine ist fertig", „Bewegung im Garten"

**Auf dem Handy**
* Push-Benachrichtigungen über Web Push, auch bei geschlossener App
* Dialoge im Vollbild, Bedienelemente ab 44 Pixel, hell und dunkel
* Zur Startseite hinzufügen — dann verhält es sich wie eine App

---

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ →
   Repositories** und `https://github.com/gregorwolf1973/chat-server-addon`
   hinzufügen (oder den Knopf oben verwenden).
2. **Chat Server** installieren.
3. Unter **Konfiguration** `admin_user` und `admin_password` setzen, starten.
4. **Öffnen** (Ingress), anmelden, unter **… → Benutzer verwalten** weitere
   Konten anlegen.

## Konfiguration

| Option | Voreinstellung | Bedeutung |
|---|---|---|
| `admin_user` | `admin` | Wird beim ersten Start als Administrator angelegt |
| `admin_password` | — | Bitte ändern. Spätere Änderungen hier wirken **nicht**; das Passwort ändert man in der Oberfläche |
| `external_url` | leer | Vollständige externe Adresse, z. B. `https://chat.example.org`. Nötig, damit Push-Nachrichten die richtige Seite öffnen |
| `api_token` | leer | Token für `POST /api/notify`. Leer lassen: dann erzeugt das Add-on eines und zeigt es in den Einstellungen |
| `max_upload_mb` | `25` | Größte Datei, 1 bis 200 |
| `allow_registration` | `true` | Ob sich Fremde selbst einen Zugang beantragen dürfen |
| `retention_days` | `0` | Nachrichten und Anhänge älter als X Tage löschen. `0` = nie |
| `sprache` | `browser` | Welche Sprache gilt, solange niemand selbst gewählt hat: `browser`, `de` oder `en` |
| `stun_server` | Google | Für Anrufe von unterwegs |
| `turn_server` … | leer | Nur nötig, wenn eine direkte Verbindung scheitert |
| `log_level` | `info` | `debug` bis `error` |

## Von unterwegs erreichbar machen

Im Heimnetz genügt **Ingress** — kein offener Port, keine Einrichtung.

Von außen braucht es HTTPS, denn Kamera, Mikrofon, Standort und Push geben
Browser nur über eine gesicherte Verbindung frei. Zwei Wege:

* **Cloudflare Tunnel** (empfohlen, kein Port am Router offen)
* **Reverse Proxy** mit eigenem Zertifikat

Beides ist in [chat_server/DOCS.md](./chat_server/DOCS.md) beschrieben.

---

## Wie es gebaut ist

| | |
|---|---|
| Server | Python, Flask, Flask-SocketIO |
| Ablage | SQLite in `/data`, Dateien daneben im Verzeichnis |
| Oberfläche | Ein HTML, ein CSS, ein JavaScript — kein Bündler, kein Framework |
| Karten | Leaflet, im Add-on mitgeliefert; Kacheln von OpenStreetMap, abschaltbar |
| Anrufe | WebRTC im Netz der Beteiligten, Socket.IO als Vermittlung |
| Töne | im Browser erzeugt, keine Tondateien |

Nichts wird zur Laufzeit von fremden Servern nachgeladen — mit einer einzigen
Ausnahme: die Kartenkacheln, und die lassen sich abschalten.

## Was der Chat **nicht** kann

Damit niemand die falsche Erwartung mitbringt:

* **Keine Ende-zu-Ende-Verschlüsselung.** Die Verbindung ist verschlüsselt,
  auf dem Server liegen die Nachrichten im Klartext. Wer den Server hat, hat
  die Nachrichten — das bist bei dir zu Hause du
* Kein Verzeichnis, keine Telefonnummern, keine Verknüpfung mit anderen
  Diensten
* Keine Übersetzung, die Oberfläche ist deutsch
* Gelöschte Nachrichten bleiben als Datensatz stehen, Text und Anhang werden
  geleert

## Sicherheit in Stichworten

* Passwörter gehasht; eine Sitzung endet sofort beim Sperren oder bei einem
  neuen Passwort
* Anmeldung gebremst: acht Fehlversuche je Konto sperren es eine Viertelstunde
* Inhaltsrichtlinie (CSP) auf allen Seiten, Skripte nur aus dem Add-on
* Der Datenstrom nimmt keine Verbindung von fremder Herkunft an
* Selbstregistrierung ist gedeckelt und braucht immer die Freigabe eines
  Administrators
* Hochgeladene Dateien werden nie als HTML ausgeliefert

Ausführlich unter *Sicherheit und Sicherungen* in
[DOCS.md](./chat_server/DOCS.md).

---

## Mitentwickeln

Das Add-on lässt sich ohne Home Assistant starten:

```bash
python -m venv .venv
.venv/bin/pip install -r chat_server/requirements.txt -r tests/requirements.txt
cd chat_server/app
DATA_DIR=/tmp/chat ADMIN_USER=admin ADMIN_PASSWORD=test1234 python server.py
```

Danach steht der Chat auf `http://127.0.0.1:8099`. `run.sh` und bashio werden
dafür nicht gebraucht.

**Testreihen** — 19 Stück, gut 800 Prüfungen. Jede braucht einen frisch
gestarteten Server auf einem leeren `DATA_DIR`:

```bash
PYTHONPATH=tests python tests/test_security.py
```

`tests/test_aufraeumen.py` braucht zusätzlich `RETENTION_DAYS=1`.

## Lizenz

MIT — siehe [LICENSE](./LICENSE).
