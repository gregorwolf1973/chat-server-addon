# Chat Server – Home Assistant Add-on

Selbstgehosteter Messenger für den eigenen Haushalt: Direktchats, Gruppen,
Datei- und Bildversand, Online-Anzeige, Tippen-Anzeige und Push-Benachrichtigungen
auf dem Handy. Läuft als Add-on auf dem Pi, Daten bleiben in `/data`.

## Installation

1. Ordner `chat_server` in dein lokales Add-on-Repository legen
   (z. B. `/addons/chat_server` per Samba oder Studio Code Server).
2. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ → Nach Updates suchen**.
3. „Chat Server" installieren, unter **Konfiguration** `admin_user` und
   `admin_password` setzen, starten.
4. Über **Öffnen** (Ingress) anmelden. Weitere Konten legst du als Administrator
   unter **… → Neues Konto anlegen** an.

## Konfiguration

| Option | Bedeutung |
|---|---|
| `admin_user` / `admin_password` | wird beim ersten Start als Administrator angelegt; spätere Änderungen der Option ändern das Passwort **nicht** (das geht in der Oberfläche) |
| `external_url` | vollständige externe Adresse, z. B. `https://chat.biker633.org` – wird für die Ziel-URL der Push-Benachrichtigungen gebraucht |
| `max_upload_mb` | Größenlimit pro Datei (Standard 25) |

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
