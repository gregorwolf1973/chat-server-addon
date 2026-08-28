# Chat Server – Home Assistant Add-on

Selbstgehosteter Messenger für den eigenen Haushalt: Direktchats, Gruppen,
Datei- und Bildversand, Online-Anzeige, Tippen-Anzeige und Push-Benachrichtigungen
auf dem Handy. Läuft als Add-on auf dem Pi, Daten bleiben in `/data`.

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
   und `https://github.com/gregorwolf1973/chat-server-addon` hinzufügen.
2. „Chat Server“ installieren, unter **Konfiguration** `admin_user` und
   `admin_password` setzen, starten.
3. Über **Öffnen** (Ingress) anmelden. Weitere Konten legst du als Administrator
   unter **… → Benutzer verwalten** an.

## Konfiguration

| Option | Bedeutung |
|---|---|
| `admin_user` / `admin_password` | wird beim ersten Start als Administrator angelegt; spätere Änderungen der Option ändern das Passwort **nicht** (das geht in der Oberfläche) |
| `external_url` | vollständige externe Adresse, z. B. `https://chat.biker633.org` – wird für die Ziel-URL der Push-Benachrichtigungen gebraucht |
| `max_upload_mb` | Größenlimit pro Datei (Standard 25) |
| `allow_registration` | ob sich Leute selbst um Zugang bewerben dürfen (Standard: ja). Freigeben musst du sie trotzdem – ohne Freigabe kommt niemand hinein |

## Externer Zugriff über Cloudflare Tunnel

Ingress reicht fürs Heimnetz, für Handy-Push brauchst du eine eigene Subdomain.
In der Tunnel-Konfiguration einen Public Hostname anlegen:

```
chat.biker633.org  ->  http://172.30.32.1:8099
```

`172.30.32.1` statt `homeassistant` verwenden (der Name löst auf IPv6 auf).
Danach `external_url: https://chat.biker633.org` setzen und das Add-on neu starten.

## Push-Benachrichtigungen

* Funktionieren nur über **HTTPS**, also über die externe Adresse – nicht über die
  Ingress-URL, deren Pfad-Token sich ändert.
* Auf dem Handy die Seite öffnen, unten links auf **Push** tippen und erlauben.
* iOS ab 16.4: die Seite muss vorher über **Teilen → Zum Home-Bildschirm** als
  App installiert werden, sonst bietet Safari kein Push an.
* Der VAPID-Schlüssel wird beim ersten Start erzeugt und liegt in `/data/vapid.json`.
  Wird er gelöscht, müssen sich alle Geräte neu für Push anmelden.

## Nachrichten aus Home Assistant

Das Add-on legt ein Konto „Home Assistant" an. Über `POST /api/notify` schreibt
eine Automation in eine Gruppe oder direkt an eine Person. Das Token steht in der
Option `api_token`; bleibt sie leer, wird beim ersten Start eines erzeugt und
in `/data/api_token.txt` abgelegt (im Log steht nur der Pfad, nicht das Token).

```yaml
# configuration.yaml
rest_command:
  chat_nachricht:
    url: "http://172.30.32.1:8099/api/notify"
    method: POST
    headers:
      Authorization: !secret chat_token   # "Bearer <token>"
      Content-Type: application/json
    payload: '{"room": "{{ room }}", "message": "{{ message }}"}'
```

```yaml
# Automation
action:
  - service: rest_command.chat_nachricht
    data:
      room: Familie          # Gruppenname oder Benutzername
      message: "Waschmaschine ist fertig"
```

Ist `room` ein Benutzername, entsteht beim ersten Mal automatisch ein Direktchat
mit „Home Assistant". Ist niemand online, geht die Nachricht zusätzlich als Push
aufs Handy.

## Zugang beantragen

Auf der Anmeldeseite steht **Zugang beantragen**. Wer das ausfüllt, gibt
Benutzernamen, Anzeigenamen, ein Passwort, **E-Mail oder Telefonnummer** und
eine kurze Begründung an.

Der Antrag legt noch kein nutzbares Konto an: Bis zur Freigabe kommt niemand
hinein, und der Name taucht auch in keiner Auswahlliste auf. Administratoren
finden die Anträge oben unter **… → Benutzer verwalten**, mit Kontaktdaten
und Begründung, und entscheiden mit **Freigeben** oder **Ablehnen**
(letzteres entfernt den Antrag). Wer als Administrator Push eingeschaltet
hat, bekommt bei jedem neuen Antrag eine Benachrichtigung.

Die Seite steht offen im Netz, deshalb nimmt sie höchstens drei Anträge je
Stunde und Absender an. Ganz abschalten lässt sie sich mit der Option
`allow_registration`.

## Benutzer verwalten

Administratoren finden unter **… → Benutzer verwalten** alle Konten mit ihren
Aktionen:

* **Passwort** – setzt ein neues Passwort. Das Konto wird dabei auf allen
  Geräten abgemeldet, damit ein vergessenes Passwort niemanden aussperrt.
  Gib das neue Passwort persönlich weiter und lass es danach selbst ändern.
* **Admin / Kein Admin** – vergibt oder entzieht Administratorrechte.
* **Sperren / Entsperren** – verwehrt den Zugang, ohne etwas zu löschen.
  Laufende Sitzungen enden sofort. Gesperrte Konten erscheinen nicht mehr in
  der Auswahl für neue Unterhaltungen, ihre Nachrichten bleiben stehen.
* **Löschen** – entfernt das Konto endgültig. Die Nachrichten bleiben im
  Verlauf, erscheinen aber unter „Gelöschtes Konto“, damit fremde
  Unterhaltungen keine Lücken bekommen.

Am eigenen Konto steht nur **Passwort** zur Verfügung, und der letzte
verbliebene Administrator lässt sich weder entmachten noch sperren – sonst
könnte niemand mehr Konten verwalten.

## Bilder für Personen und Gruppen

Jeder kann sein eigenes Bild setzen: **… → Einstellungen → Bild wählen**.
Das Gruppenbild ändert man, indem man in der Gruppe oben auf das runde Bild
neben dem Namen tippt – das darf jedes Mitglied. In einem Direktchat steht
dort das Bild der Gegenseite, dort gibt es nichts einzustellen.

Wer kein Bild hat, erscheint mit seinen Initialen auf farbigem Grund. Die
Farbe bleibt für dieselbe Person immer gleich.

Bilder werden **im Browser** auf 256 Pixel verkleinert und mittig quadratisch
zugeschnitten, bevor sie hochgeladen werden – aus einem Handyfoto werden so
rund 30 KB statt mehrerer Megabyte. Ein ersetztes Bild wird vom Server
gelöscht, es sammelt sich nichts an.

## Bilder und Dateien

Der Knopf **Medien** unten links öffnet alles, was in deinen Unterhaltungen
geteilt wurde – Bilder als Raster, Dateien als Liste, jeweils mit Absender,
Unterhaltung und Zeitpunkt. Über die Auswahl oben lässt sich auf eine
einzelne Unterhaltung einschränken.

Sichtbar ist nur, was ohnehin sichtbar wäre: Medien aus Unterhaltungen, in
denen du Mitglied bist.

Beim Löschen verschwindet die Datei aus dem Verlauf **und vom Server** – die
Bytes bleiben nicht liegen. Eigene Dateien darf jeder löschen, fremde nur ein
Administrator. Dasselbe gilt, wenn du eine Nachricht mit Anhang löschst: der
Anhang geht mit.

## Antworten und Löschen

* Auf eine Sprechblase tippen blendet **Antworten** und **Löschen** ein.
* Zitate erscheinen als Balken über der Nachricht; ein Tipp darauf springt zum
  Original im Verlauf.
* Gelöschte Nachrichten verschwinden bei allen sofort und hinterlassen den
  Hinweis „Nachricht gelöscht". Administratoren dürfen fremde Nachrichten löschen.

## Technik

* Flask + Flask-SocketIO im `threading`-Modus mit `simple-websocket` – kein
  gevent/eventlet, dadurch keine Kompilierung auf aarch64.
* SQLite unter `/data/chat.db` (WAL), Uploads unter `/data/uploads`.
* Ingress über `ReverseProxied`-Middleware, die **nach** `SocketIO(app)` gewrappt
  wird, damit auch `/socket.io` den Prefix verliert.
* Der eingebaute Werkzeug-Server ist für eine Handvoll Nutzer ausreichend. Bei
  spürbarer Last wäre gunicorn mit gevent-websocket der nächste Schritt.

## Grenzen

* Transportverschlüsselung über TLS, **keine** Ende-zu-Ende-Verschlüsselung.
* Keine Sprach- oder Videoanrufe, keine Lesebestätigungen über den
  Ungelesen-Zähler hinaus.
* Gelöschte Nachrichten werden als gelöscht markiert, der Datensatz bleibt in der
  Datenbank (Text und Dateiverweis werden geleert).
