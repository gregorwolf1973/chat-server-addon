# Chat Server — manual

A self-hosted messenger for a family, a shared flat or a club. Direct chats
and groups, files and pictures, voice messages, voice and video calls,
invitations with a place, a map, a personal gallery and push notifications on
your phone. Runs as a Home Assistant add-on, a Raspberry Pi is enough; all
data stays in `/data`.

🇩🇪 [Dieses Handbuch auf Deutsch](./DOCS.md) — the German version is the
original and always the more detailed one.

> **The interface speaks English too.** Switch it under *Einstellungen →
> Aussehen → Sprache* (settings → appearance → language); without a choice it
> follows your browser. This manual sometimes names a button in German with
> the English meaning next to it — handy if someone left the chat in German.

---

## Contents

[Installation](#installation) ·
[Configuration](#configuration) ·
[Reaching it from outside](#reaching-it-from-outside) ·
[Push notifications](#push-notifications) ·
[Messages from Home Assistant](#messages-from-home-assistant) ·
[Accounts](#accounts) ·
[Writing](#writing) ·
[Calls](#calls) ·
[Invitations and events](#invitations-and-events) ·
[Location and maps](#location-and-maps) ·
[Recommendations and moods](#recommendations-and-moods) ·
[Gallery](#gallery) ·
[On a phone](#on-a-phone) ·
[Appearance](#appearance) ·
[Housekeeping](#housekeeping) ·
[Security](#security) ·
[Limits](#limits)

---

## Installation

1. Home Assistant → **Settings → Add-ons → Add-on Store → ⋮ → Repositories**,
   add `https://github.com/gregorwolf1973/chat-server-addon`.
2. Install **Chat Server**.
3. Under **Configuration** set `admin_user` and `admin_password`, start it.
4. **Open** (Ingress) and sign in. Create further accounts as administrator
   under **… → Benutzer verwalten** (manage users).

## Configuration

| Option | Default | Meaning |
|---|---|---|
| `admin_user` / `admin_password` | `admin` | Created as administrator on the **first** start. Changing the option later does **not** change the password — do that inside the app |
| `external_url` | empty | Full public address, e.g. `https://chat.example.org`. Push notifications need it to open the right page |
| `api_token` | empty | Token for `POST /api/notify`. Better left empty: the add-on generates one, shows it in the settings and can rotate it there |
| `max_upload_mb` | `25` | Largest file, 1 to 200 |
| `allow_registration` | `true` | Whether strangers may request an account. Approval by an administrator is always required |
| `retention_days` | `0` | Delete messages and attachments older than X days. `0` means never |
| `sprache` | `browser` | Default language: `browser`, `de` or `en`. A personal choice overrides it |
| `stun_server` | Google | For calls from outside |
| `turn_server` / `turn_username` / `turn_password` | empty | Only needed when a direct connection fails |
| `log_level` | `info` | `debug`, `info`, `warning` or `error` |

`/data` holds `chat.db` (the database), `uploads/` (files), `avatars/`
(profile pictures), plus the session key and the API token.

## Reaching it from outside

Inside the home network **Ingress** is enough — no open port.

From outside you need **HTTPS**. Browsers hand out camera, microphone,
location and push only over a secure connection, so without it calls, voice
messages, the map and notifications all stay unavailable.

**Cloudflare Tunnel** (recommended, nothing open on the router). Add a public
hostname pointing at the add-on:

```
chat.example.org  ->  http://172.30.32.1:8099
```

Use `172.30.32.1` rather than `homeassistant`, which resolves to IPv6. Then
set `external_url: https://chat.example.org` and restart the add-on.

A reverse proxy with your own certificate works just as well.

## Push notifications

* Only over **HTTPS**, so over the external address — not over the Ingress
  URL, whose path token changes.
* When the browser has already been granted permission, the device
  re-subscribes silently on every visit. The very first time a small bar asks
  once; browsers require a real tap for that question, and a dialog that
  opens by itself is refused silently.
* iOS 16.4 and later: the page must first be installed through
  **Share → Add to Home Screen**, otherwise Safari offers no push at all.
* The VAPID key pair is generated on first start and lives in
  `/data/vapid.json`. Delete it and every device has to subscribe again.

## Messages from Home Assistant

The add-on creates an account named *Home Assistant*. `POST /api/notify`
posts as that account into a group or to a person.

The token belongs in the **`Authorization` header**, never in the URL — the
access log records every request line, and the token would sit there in
plain text.

```yaml
# secrets.yaml
chat_token: "Bearer YOUR-TOKEN"
```

```yaml
rest_command:
  chat_message:
    url: "http://localhost:8099/api/notify"
    method: POST
    headers:
      Authorization: !secret chat_token
    content_type: "application/json"
    payload: '{"room": "{{ room }}", "message": "{{ message }}"}'
```

`room` matches a group by name, or a person by user name. A new token can be
generated under **Einstellungen → Home Assistant → Neu** (settings → new);
the old one stops working immediately.

## Accounts

**Requesting access.** With `allow_registration` on, the sign-in page offers
**Zugang beantragen** (request access). The applicant gives a name, a
password, optionally e-mail, phone and a reason, and must tick the data
protection consent. An administrator has to approve before the account works.
Three requests per hour and address; no more than 20 unanswered requests at
a time.

**Noticing a request.** Administrators get a push notification, a short
on-screen notice, and a red number on the gear at the bottom left that stays
until the request is dealt with.

**Forgotten password.** The add-on sends no mail. Under the sign-in form,
**Passwort vergessen?** notifies the administrators instead; the request
appears at the top of the user management with **Neues Passwort** (new
password) and **Erledigt** (done) next to it. A made-up user name gets
exactly the same answer as a real one, so the page cannot be used to find out
which accounts exist.

**Managing users.** Administrators can create accounts, reset passwords,
grant and revoke administrator rights, lock and delete. The last remaining
administrator cannot be demoted or locked. Deleting keeps the messages but
shows them under *Gelöschtes Konto* (deleted account).

**Friends.** Both sides have to ask; only then does it count. Friendship
carries recommendations, moods and birthdays beyond the conversations you
share.

**The display name** of the whole app is set by an administrator under
**Einstellungen → Name**. It shows in the sidebar, the window title, the
sign-in page and the web manifest.

## Writing

* **Reply** quotes the message above it; **forward** moves a message into
  another conversation, keeping the attachment without copying the file
* **Delete** empties the text and the attachment; the row itself stays
* **Search** — the 🔍 at the top searches text and file names from two
  characters, in one conversation or in all. Hits replace the history; a tap
  jumps to the message, with thirty either side, and it lights up briefly
* Two arrows bottom right: one to the end, one to the previous day. Scrolling
  up loads fifty older messages at a time
* **Voice messages**: hold the button, release to send. A short tone marks
  the start
* The **paperclip** hides sharing your location, creating an invitation and
  starting a poll
* Several pictures at once become an **album** in one bubble; each picture
  stays its own message
* A tap on a picture or video opens the **media viewer**: full screen, swipe
  to page, a timeline underneath, oldest first

## Calls

📞 and 🎥 at the top of a conversation. It is always a **round**, never a
one-to-one ring: anyone may join, anyone may leave, the call runs until the
last person hangs up. Up to six people.

Everyone else sees a banner with **Annehmen** (accept) and **Ablehnen**
(decline), independent of which conversation they have open, plus a ringtone
and a buzz on the phone. Ringing stops by itself after 45 seconds; the banner
stays as long as the call runs. Whoever has the app closed gets a push
notification.

Audio and video travel **directly between the participants** (WebRTC); the
server only brokers. From outside a **STUN** server is needed so each device
learns its public address — that is the preset Google one, and it never sees
picture or sound. When a direct connection cannot be made — strict firewalls,
carrier-grade NAT — a **TURN** server would have to relay the whole stream.
None is preset, and one is only worth setting up if calls actually fail. Note
that a TURN operator sees who talks to whom, and for how long.

**Sounds.** Under settings: all, calls only, or silent. Ringtone selectable
from five patterns, all generated in the browser — no audio file ships with
the add-on, so a custom one cannot be supplied. Individual conversations can
be muted for an hour, eight hours or indefinitely.

## Invitations and events

An invitation carries a title, a time, a place (typed, picked on the map or
taken from the current position), a description, a picture and tags such as
music, dancing, film or sport. Everyone answers yes, no or maybe.

**Cancelling** is reserved for whoever invited — deliberately not even the
administrator. A cancelled event **disappears** from the conversation, from
the lists and from search, which makes cancelling final; the confirmation
says so beforehand.

**An event without a conversation** is created under **Termine** (events).
You choose who sees it:

* **Selected friends**, ticked individually
* **Everyone within** 1, 5, 10 or 25 km of the event

For the radius the server has to know where the *viewer* is. That works
either because they are sharing their location anyway, or because the
interface passes the coordinates along for that one request — never stored.
Without either, such invitations stay invisible.

**Birthdays** of people in your circle appear among the events, 🎂 with the
age being reached. Switchable in the settings; your own birthday stays stored
either way.

## Location and maps

Sharing your location always runs out on its own — you pick the duration.
Three scopes: one conversation, all friends, or everyone within up to 25 km.
For the radius you have to be sharing yourself; otherwise the server would
not know where you are, and it is not meant to.

The **live map** shows shared locations, invitations with a place and
recommendations. Filters by period, by tag and by distance. The distance is
computed **in the browser** — your position is not sent for that.

Two kinds of map exist. The **outline map** ships inside the add-on and asks
nobody; it is used for the small preview under a location message. Street
maps are shown in the full map views, with tiles from OpenStreetMap — the one
place where anything is fetched from a third party. Switch it off under
**Einstellungen → Karten**.

**In Karten öffnen** (open in maps) hands the point to the device's own map
app; Android asks which one. Google Maps, Apple Maps or OpenStreetMap can be
chosen instead.

## Recommendations and moods

**Empfehlungen** (recommendations) are tips for cinema, pub, restaurant,
walks and so on — with stars, a picture, a place and a note. Visible to your
circle. They can be filtered by distance from where you are.

**Stimmung** (mood) is a short note about what you feel like right now, with
an emoji, a duration and optionally your location. Others tap **Ich mach mit**
(I'm in). One note per person; a new one replaces the old. A tap on the name
opens the conversation with that person.

## Gallery

What you send into a conversation is seen by its members and no one else.
Pictures and films can be released beyond that: under **Medien** every one of
your own tiles carries a mark.

| Mark | Meaning |
|---|---|
| 🔒 | not released — visible only inside the conversation |
| 👥 | released to your confirmed friends |
| 🌍 | released to everyone with an account |

**＋ Bild hinzufügen** in your own gallery puts a picture or film straight in,
without it ever appearing in a conversation. A release **holds the file**:
deleting the message it once arrived with, or the retention period expiring,
no longer takes it away. The ✕ on a tile deletes it for good, everywhere.

Under each picture two numbers, and they mean different things:

* **❤️ hearts** — everyone who can see the picture sees the count
* **💬 comments** are a **private exchange** between you and the owner. No
  other visitor can read them, and the *count* shows only your own thread —
  otherwise the number alone would reveal that someone else had written

The owner sees the threads separated by person and answers in each one. You
may delete your own comment, nobody else's.

Reaching a gallery: in a one-to-one conversation, **🎞️ Galerie** next to the
name at the top. Your own: **Galerie** at the bottom left.

## On a phone

* Every control is at least **44 px** on touch devices; with a mouse the
  interface stays compact
* **Dialogs fill the screen** instead of floating as a narrow window. Input
  fields are 16 px — any smaller and iOS zooms in when you tap
* **When the keyboard opens**, the layout follows the visible viewport rather
  than `100dvh`, which does not shrink. Without that the browser would push
  the whole page up to reveal the input and take the header with it
* The last message stays at the bottom — on opening, while images load, and
  with the keyboard up
* **In landscape** the call controls move on top of the video; otherwise the
  tiles would push them off screen
* On the first visit one bar asks for all permissions at once —
  notifications, microphone, camera, location

## Appearance

Light and dark, or follow the device. Chat backgrounds are patterns drawn in
the browser, not images, and they do not scroll with the content. The colour
of your own bubbles is set once and applies everywhere.

The sidebar has five tabs: conversations, maps, moods, events,
recommendations. Their numbers count only what is **new** since you last
looked.

## Housekeeping

`retention_days` deletes messages and attachments older than X days. `0`, the
default, means never — a messenger that throws away memories unasked would be
an imposition. An administrator can also trigger a run immediately. Events,
recommendations and accounts are never touched; this is only about the
history. A picture released to the gallery is kept.

Uploads under `/data/uploads` are **excluded from the backup** — at up to
200 MB per file every snapshot would become unwieldy. Database, keys and
profile pictures are backed up. Remove `backup_exclude` from `config.yaml` if
you want the files included.

## Security

* Passwords are hashed. A session ends the moment the account is locked or
  the password changes — on every device
* Sign-in throttling: **eight** failed attempts lock an account for a quarter
  of an hour, regardless of where they come from. A much higher limit applies
  per address, because behind a tunnel everyone shares one
* A **Content Security Policy** on every page: scripts only from the add-on,
  the one inline script carrying a nonce that changes per request. Images
  come from here, the sole exception being map tiles
* The realtime channel **refuses connections from a foreign origin**
* Uploaded files are never served as HTML; the browser-supplied content type
  is not trusted
* `X-Forwarded-For` is not believed blindly — behind Cloudflare
  `CF-Connecting-IP` counts, which cannot be forged. No throttle depends on
  the address alone
* Registration requests are capped at 20 open ones

## Limits

* **No end-to-end encryption.** Transport is encrypted; on the server the
  messages are in the clear
* Deleted messages keep their row; text and file reference are emptied
* No directory, no phone numbers, no federation with other servers
