# Chat Server — a self-hosted messenger as a Home Assistant add-on

A messenger for a family, a shared flat or a club that runs on your own
hardware. No accounts with anyone else, no phone numbers, no advertising.
Everything lives in `/data` on the machine running Home Assistant — a
Raspberry Pi is enough.

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgregorwolf1973%2Fchat-server-addon)

🇩🇪 [Diese Seite auf Deutsch](./README.md)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/gregorwolf1973)

> **Language:** German and English. Switch it under *Einstellungen →
> Aussehen → Sprache* (settings → appearance → language); without a choice the
> chat follows your browser. Comments and identifiers in the source stay
> German.

---

## What it does

**Conversations**
* Direct chats and groups, quoted replies, forwarding, deleting
* Images, video, audio and file attachments (25 MB by default, up to 200);
  several images arrive as one album
* Emoji picker, presence, "is typing", unread counter
* Full-text search over the history — one conversation or all of them
* Voice messages: hold the button, release to send

**Talking and seeing**
* Voice and video calls, including group calls with up to six people
* Peer-to-peer over WebRTC; the server only brokers the connection
* Selectable ringtone, mute per person and per group

**Making plans**
* Invitations with a place, a picture, tags and yes/no/maybe
* Events that belong to no conversation — visible to hand-picked friends, or
  to everyone within a radius of up to 25 km
* Birthdays of people in your circle, switchable

**Showing what is going on**
* A live map with shared locations, invitations and recommendations
* Share your location with one conversation, with all friends, or with
  everyone nearby — always with an expiry time
* Recommendations (cinema, pub, a walk …) with stars and a distance filter
* "What I feel like" — short mood notes others can join

**Pictures beyond the conversation**
* A personal gallery: release pictures to friends or to everyone
* Hearts are counted publicly, **comments stay a private exchange** between
  the owner and the one writing
* Full-screen media viewer with swiping and a timeline

**From Home Assistant**
* `POST /api/notify` sends messages from automations into a group or to a
  person — "washing machine is done", "motion in the garden"

**On a phone**
* Web Push notifications, also while the app is closed
* Full-screen dialogs, touch targets from 44 px, light and dark themes
* Add to home screen and it behaves like an app

---

## Installing

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ →
   Repositories**, add
   `https://github.com/gregorwolf1973/chat-server-addon`
   (or use the button above).
2. Install **Chat Server**.
3. Under **Configuration** set `admin_user` and `admin_password`, then start.
4. **Open** (Ingress), sign in, and create further accounts under
   **… → Benutzer verwalten** (manage users).

## Configuration

| Option | Default | Meaning |
|---|---|---|
| `admin_user` | `admin` | Created as administrator on first start |
| `admin_password` | — | Change it. Later edits here do **not** change the password; that happens inside the app |
| `external_url` | empty | Full public address, e.g. `https://chat.example.org`. Needed so push notifications open the right page |
| `api_token` | empty | Token for `POST /api/notify`. Better left empty: the add-on then generates one, shows it in the settings and can rotate it there |
| `max_upload_mb` | `25` | Largest file, 1 to 200 |
| `allow_registration` | `true` | Whether strangers may request an account. An administrator still has to approve every one |
| `retention_days` | `0` | Delete messages and attachments older than X days. `0` means never |
| `sprache` | `browser` | Which language applies until someone picks one: `browser`, `de` or `en` |
| `stun_server` | Google | For calls from outside the home network |
| `turn_server` … | empty | Only needed when a direct connection fails |
| `log_level` | `info` | `debug` through `error` |

## Reaching it from outside

Inside your home network **Ingress** is enough — no open port, nothing to set
up.

From outside you need HTTPS, because browsers hand out camera, microphone,
location and push only over a secure connection. Two ways:

* **Cloudflare Tunnel** (recommended, no port open on the router)
* **Reverse proxy** with your own certificate

Both are described in [chat_server/DOCS.md](./chat_server/DOCS.md) (German).

---

## How it is built

| | |
|---|---|
| Server | Python, Flask, Flask-SocketIO |
| Storage | SQLite in `/data`, files next to it |
| Front end | One HTML, one CSS, one JavaScript — no bundler, no framework |
| Maps | Leaflet, shipped with the add-on; tiles from OpenStreetMap, switchable |
| Calls | WebRTC between the participants, Socket.IO for signalling |
| Sounds | generated in the browser, no audio files |

Nothing is fetched from a third party at runtime — with a single exception:
the map tiles, and those can be turned off.

## What it deliberately does **not** do

* **No end-to-end encryption.** The transport is encrypted; on the server the
  messages sit in the clear. Whoever owns the server can read them — at home,
  that is you
* No directory, no phone numbers, no ties to other services
* Deleted messages keep their row; text and attachment are emptied

## Security in brief

* Passwords are hashed; a session ends the moment an account is locked or its
  password changes
* Sign-in is throttled: eight failed attempts lock an account for 15 minutes
* A Content Security Policy on every page; scripts only from the add-on
* The realtime channel refuses connections from a foreign origin
* Self-registration is capped and always needs an administrator's approval
* Uploaded files are never served as HTML

Details under *Sicherheit und Sicherungen* in
[DOCS.md](./chat_server/DOCS.md).

---

## Hacking on it

The add-on runs without Home Assistant:

```bash
python -m venv .venv
.venv/bin/pip install -r chat_server/requirements.txt -r tests/requirements.txt
cd chat_server/app
DATA_DIR=/tmp/chat ADMIN_USER=admin ADMIN_PASSWORD=test1234 python server.py
```

The chat is then on `http://127.0.0.1:8099`. `run.sh` and bashio are not
needed for this.

**Test suites** — 18 of them, roughly 780 assertions. Each needs a freshly
started server on an empty `DATA_DIR`:

```bash
PYTHONPATH=tests python tests/test_security.py
```

`tests/test_aufraeumen.py` additionally needs `RETENTION_DAYS=1`.

Comments and identifiers in the source are German, matching the interface.

## Licence

MIT — see [LICENSE](./LICENSE).
