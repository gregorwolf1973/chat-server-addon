#!/usr/bin/env python3
"""Chat Server - Home Assistant Add-on.

Flask + Socket.IO, SQLite unter /data, Web-Push fuer Benachrichtigungen.
"""
import base64
import json
import datetime
import logging
import math
import os
import secrets
import sqlite3
import threading
import time
from functools import wraps

from flask import (Flask, abort, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "chat.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
VAPID_PATH = os.path.join(DATA_DIR, "vapid.json")
SECRET_PATH = os.path.join(DATA_DIR, "secret.key")
TOKEN_PATH = os.path.join(DATA_DIR, "api_token.txt")

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
def _opt(name):
    """bashio liefert fuer nicht gesetzte optionale Werte den Text 'null'."""
    val = (os.environ.get(name) or "").strip()
    return "" if val in ("null", "None") else val


EXTERNAL_URL = _opt("EXTERNAL_URL").rstrip("/")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()
ALLOW_REGISTRATION = _opt("ALLOW_REGISTRATION").lower() not in ("false", "0", "off")
# Fuer Anrufe von unterwegs muss ein Geraet seine oeffentliche Adresse
# kennen. Das leistet ein STUN-Server; er erfaehrt nur diese Adresse, nie
# Bild oder Ton. Wer gar nichts nach draussen geben will, traegt hier nichts
# ein - dann funktionieren Anrufe im Heimnetz, aber nicht von unterwegs.
STUN_SERVER = _opt("STUN_SERVER") or "stun:stun.l.google.com:19302"
if STUN_SERVER.lower() in ("aus", "off", "none", "-"):
    STUN_SERVER = ""
# Scheitert auch das - etwa in Mobilfunknetzen mit strenger Abschottung -,
# hilft nur ein TURN-Server, der die Daten weiterreicht. Er muss selbst
# betrieben werden; einen brauchbaren kostenlosen gibt es nicht.
TURN_SERVER = _opt("TURN_SERVER")
TURN_BENUTZER = _opt("TURN_USERNAME")
TURN_PASSWORT = _opt("TURN_PASSWORD")
# Nachrichten und Anhaenge aelter als so viele Tage werden entfernt. 0 heisst
# nie - ein Messenger, der ungefragt Erinnerungen wegwirft, waere eine
# Zumutung.
try:
    AUFBEWAHRUNG_TAGE = max(0, int(_opt("RETENTION_DAYS") or 0))
except ValueError:
    AUFBEWAHRUNG_TAGE = 0

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("chat")


# --------------------------------------------------------------------------
# Ingress: HA setzt X-Ingress-Path, Flask muss den Prefix kennen
# --------------------------------------------------------------------------
class ReverseProxied:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get("HTTP_X_INGRESS_PATH")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path = environ.get("PATH_INFO", "")
            if path.startswith(script_name):
                environ["PATH_INFO"] = path[len(script_name):]
        return self.app(environ, start_response)


def load_secret():
    if os.path.exists(SECRET_PATH):
        return open(SECRET_PATH, "rb").read()
    key = secrets.token_bytes(32)
    with open(SECRET_PATH, "wb") as fh:
        fh.write(key)
    os.chmod(SECRET_PATH, 0o600)
    return key


app = Flask(__name__)
app.secret_key = load_secret()
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 90

# Bewusst KEIN SESSION_COOKIE_SECURE und keine Einschraenkung von
# cors_allowed_origins: Das Add-on ist ueber zwei Wege zugleich erreichbar -
# per TLS ueber die externe Adresse und per http ueber den Ingress von Home
# Assistant. Ein Secure-Cookie wuerde die Anmeldung im Heimnetz unmoeglich
# machen, und der Ursprung unter Ingress ist die Adresse der
# Home-Assistant-Oberflaeche, die hier niemand kennt. Gegen fremde Seiten
# schuetzt SameSite=Lax: das Cookie verlaesst den Browser bei Aufrufen von
# dritter Seite gar nicht erst.
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*",
                    max_http_buffer_size=MAX_UPLOAD_MB * 1024 * 1024)

# WICHTIG: erst nach SocketIO() wrappen, damit der Ingress-Prefix auch fuer
# /socket.io entfernt wird - sonst findet der WebSocket unter Ingress nichts.
app.wsgi_app = ReverseProxied(app.wsgi_app)

# user_id -> Anzahl offener Verbindungen
ONLINE = {}
ONLINE_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Datenbank
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    pw_version INTEGER NOT NULL DEFAULT 0,
    pending INTEGER NOT NULL DEFAULT 0,
    email TEXT,
    phone TEXT,
    note TEXT,
    avatar TEXT,
    geburtstag TEXT,
    zustimmung_at INTEGER,
    karten_kacheln INTEGER NOT NULL DEFAULT 1,
    ton_stufe TEXT,
    blasenfarbe TEXT,
    karten_app TEXT,
    klingelton TEXT,
    geburtstage_an INTEGER NOT NULL DEFAULT 1,
    gesehen_karten INTEGER,
    gesehen_stimmung INTEGER,
    gesehen_termine INTEGER,
    gesehen_tipps INTEGER,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY,
    name TEXT,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    avatar TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS room_members (
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    last_read INTEGER NOT NULL DEFAULT 0,
    color TEXT,
    hintergrund TEXT,
    stumm_bis INTEGER,
    PRIMARY KEY (room_id, user_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    body TEXT,
    file_id INTEGER,
    reply_to INTEGER,
    deleted INTEGER NOT NULL DEFAULT 0,
    album TEXT,
    weitergeleitet INTEGER NOT NULL DEFAULT 0,
    poll_id INTEGER,
    event_id INTEGER,
    sprachdauer INTEGER,
    lat REAL,
    lon REAL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_room ON messages(room_id, id);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    stored_name TEXT NOT NULL,
    orig_name TEXT NOT NULL,
    mime TEXT,
    size INTEGER,
    user_id INTEGER,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    frage TEXT NOT NULL,
    mehrfach INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS poll_options (
    id INTEGER PRIMARY KEY,
    poll_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    platz INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS poll_votes (
    poll_id INTEGER NOT NULL,
    option_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (poll_id, option_id, user_id)
);
-- Bilder und Filme, die jemand ueber die Unterhaltung hinaus freigibt.
-- Ein Eintrag je Datei; wer sie sehen darf, steht in art.
-- Serverweite Einstellungen. Bisher steht nur der Anzeigename darin; die
-- Tabelle ist der Platz fuer alles Weitere, was allen gemeinsam gehoert und
-- nicht am einzelnen Konto haengt.
-- Wer sein Passwort vergessen hat, hinterlaesst hier eine Bitte. Eine je
-- Person: ein zweites Mal fragen verschiebt nur den Zeitpunkt. Zuruecksetzen
-- kann sie nur ein Administrator - per Mail ginge es nicht, das Add-on
-- verschickt keine.
CREATE TABLE IF NOT EXISTS passwort_bitten (
    user_id INTEGER PRIMARY KEY,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS einstellungen (
    schluessel TEXT PRIMARY KEY,
    wert TEXT
);
CREATE TABLE IF NOT EXISTS galerie (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    art TEXT NOT NULL,
    titel TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS galerie_herzen (
    galerie_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (galerie_id, user_id)
);
-- Ein Kommentar gehoert immer zu einem Zwiegespraech zwischen der Person,
-- der das Bild gehoert, und genau einer anderen. mit_id sagt, wer diese
-- andere ist - beim Schreiben der Besucher selbst, bei einer Antwort der
-- Besitzerin die Person, der sie antwortet. Sonst waere nicht zu trennen,
-- wer welchen Faden lesen darf.
CREATE TABLE IF NOT EXISTS galerie_worte (
    id INTEGER PRIMARY KEY,
    galerie_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    mit_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS event_gaeste (
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (event_id, user_id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    -- 0 heisst: haengt an keiner Unterhaltung. Wer den Termin sehen darf,
    -- steht dann in sicht und in event_gaeste.
    room_id INTEGER NOT NULL,
    sicht TEXT,
    umkreis_km INTEGER,
    user_id INTEGER NOT NULL,
    titel TEXT NOT NULL,
    beschreibung TEXT,
    ort_text TEXT,
    lat REAL,
    lon REAL,
    beginnt_at INTEGER,
    file_id INTEGER,
    kategorien TEXT,
    abgesagt INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS event_antworten (
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    antwort TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (event_id, user_id)
);
CREATE TABLE IF NOT EXISTS live_orte (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    genauigkeit REAL,
    bis_at INTEGER NOT NULL,
    art TEXT,
    umkreis_km INTEGER,
    begonnen_at INTEGER,
    updated_at INTEGER NOT NULL,
    UNIQUE (user_id, room_id)
);
CREATE TABLE IF NOT EXISTS stimmungen (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    emoji TEXT,
    text TEXT NOT NULL,
    lat REAL,
    lon REAL,
    bis_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS stimmung_mit (
    stimmung_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (stimmung_id, user_id)
);
CREATE TABLE IF NOT EXISTS tipps (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    art TEXT NOT NULL,
    titel TEXT NOT NULL,
    ort_text TEXT,
    lat REAL,
    lon REAL,
    sterne INTEGER NOT NULL,
    text TEXT,
    file_id INTEGER,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tipp_marken (
    tipp_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (tipp_id, user_id)
);
CREATE TABLE IF NOT EXISTS freundschaften (
    klein_id INTEGER NOT NULL,
    gross_id INTEGER NOT NULL,
    angefragt_von INTEGER NOT NULL,
    bestaetigt INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (klein_id, gross_id)
);
CREATE TABLE IF NOT EXISTS push_subs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    endpoint TEXT UNIQUE NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def raw_db():
    """Verbindung ausserhalb eines Request-Kontexts (Push-Thread, Setup)."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


BOT_USERNAME = "homeassistant"
# Konten, die die Verwaltung nicht anfassen darf. Das Bot-Konto schreibt die
# Nachrichten aus Home Assistant, das Archiv-Konto haelt die Nachrichten
# geloeschter Nutzer.
GONE_USERNAME = "geloeschtes-konto"
SYSTEM_USERS = (BOT_USERNAME, GONE_USERNAME)


# Hintergrundmuster: kein hochgeladenes Bild, sondern eines aus einer festen
# Liste. Es wird in der Oberflaeche gezeichnet, liegt also weder als Datei auf
# dem Pi noch lenkt es vom Text ab.
MUSTER = ("punkte", "karo", "wellen", "kreuze", "blaetter", "kritzel")


def migrate(conn):
    """Fehlende Spalten aelterer Installationen nachziehen."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
    if "reply_to" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN reply_to INTEGER")
    if "deleted" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
    if "album" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN album TEXT")
    if "weitergeleitet" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN weitergeleitet"
                     " INTEGER NOT NULL DEFAULT 0")
    for spalte in ("lat", "lon"):
        if spalte not in cols:
            conn.execute(f"ALTER TABLE messages ADD COLUMN {spalte} REAL")
    if "poll_id" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN poll_id INTEGER")
    if "event_id" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN event_id INTEGER")
    if "sprachdauer" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN sprachdauer INTEGER")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "pw_version" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pw_version INTEGER NOT NULL DEFAULT 0")
    if "pending" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pending INTEGER NOT NULL DEFAULT 0")
    if "zustimmung_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN zustimmung_at INTEGER")
    for spalte in ("email", "phone", "note", "avatar", "geburtstag"):
        if spalte not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {spalte} TEXT")
    if "ton_stufe" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN ton_stufe TEXT")
    if "blasenfarbe" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN blasenfarbe TEXT")
    if "karten_app" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN karten_app TEXT")
    if "klingelton" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN klingelton TEXT")
    if "geburtstage_an" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN geburtstage_an"
                     " INTEGER NOT NULL DEFAULT 1")
    for bereich in ("karten", "stimmung", "termine", "tipps"):
        if f"gesehen_{bereich}" not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN gesehen_{bereich} INTEGER")
    if "karten_kacheln" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN karten_kacheln"
                     " INTEGER NOT NULL DEFAULT 1")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(live_orte)")}
    if cols and "begonnen_at" not in cols:
        conn.execute("ALTER TABLE live_orte ADD COLUMN begonnen_at INTEGER")
    if cols and "art" not in cols:
        conn.execute("ALTER TABLE live_orte ADD COLUMN art TEXT")
    if cols and "umkreis_km" not in cols:
        conn.execute("ALTER TABLE live_orte ADD COLUMN umkreis_km INTEGER")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)")}
    if cols and "sicht" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN sicht TEXT")
    if cols and "umkreis_km" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN umkreis_km INTEGER")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(rooms)")}
    if "avatar" not in cols:
        conn.execute("ALTER TABLE rooms ADD COLUMN avatar TEXT")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(room_members)")}
    if "color" not in cols:
        conn.execute("ALTER TABLE room_members ADD COLUMN color TEXT")
    if "stumm_bis" not in cols:
        conn.execute("ALTER TABLE room_members ADD COLUMN stumm_bis INTEGER")
    if "hintergrund" not in cols:
        conn.execute("ALTER TABLE room_members ADD COLUMN hintergrund TEXT")
    else:
        # Frueher stand hier der Dateiname eines hochgeladenen Bildes. Jetzt
        # steht dort ein Mustername; alles andere ist wertlos.
        marks = ",".join("?" * len(MUSTER))
        conn.execute(f"UPDATE room_members SET hintergrund=NULL"
                     f" WHERE hintergrund IS NOT NULL"
                     f" AND hintergrund NOT IN ({marks})", MUSTER)
    conn.commit()


def load_api_token():
    """Token fuer die Home-Assistant-Schnittstelle - aus Option oder /data."""
    configured = _opt("API_TOKEN")
    if configured:
        log.info("Token fuer die Home-Assistant-Schnittstelle aus der Add-on-Option")
        return configured
    if os.path.exists(TOKEN_PATH):
        log.info("Token fuer die Home-Assistant-Schnittstelle steht in %s", TOKEN_PATH)
        return open(TOKEN_PATH).read().strip()
    token = secrets.token_urlsafe(32)
    with open(TOKEN_PATH, "w") as fh:
        fh.write(token)
    os.chmod(TOKEN_PATH, 0o600)
    # Das Token selbst gehoert nicht ins Add-on-Log - das ist in der
    # Oberflaeche sichtbar und landet in Fehlerberichten.
    log.info("Token fuer die Home-Assistant-Schnittstelle erzeugt: %s", TOKEN_PATH)
    return token


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(AVATAR_DIR, exist_ok=True)
    conn = raw_db()
    conn.executescript(SCHEMA)
    conn.commit()
    migrate(conn)

    # Bot-Konto fuer Nachrichten aus Home Assistant (kein Login moeglich)
    if conn.execute("SELECT id FROM users WHERE username=?",
                    (BOT_USERNAME,)).fetchone() is None:
        conn.execute(
            "INSERT INTO users (username, display_name, pw_hash, is_admin, created_at)"
            " VALUES (?,?,?,0,?)",
            (BOT_USERNAME, "Home Assistant", "!", int(time.time())))
        conn.commit()

    admin_user = os.environ.get("ADMIN_USER", "admin").strip()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    row = conn.execute("SELECT id FROM users WHERE username=?",
                       (admin_user,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (username, display_name, pw_hash, is_admin, created_at)"
            " VALUES (?,?,?,1,?)",
            (admin_user, admin_user, generate_password_hash(admin_pw), int(time.time())))
        conn.commit()
        log.info("Administrator '%s' angelegt", admin_user)
    conn.close()


# --------------------------------------------------------------------------
# Web-Push
# --------------------------------------------------------------------------
def ensure_vapid():
    if os.path.exists(VAPID_PATH):
        return json.load(open(VAPID_PATH))
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    pub_raw = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint)
    data = {
        "private_pem": priv_pem,
        "public_key": base64.urlsafe_b64encode(pub_raw).decode().rstrip("="),
    }
    with open(VAPID_PATH, "w") as fh:
        json.dump(data, fh)
    os.chmod(VAPID_PATH, 0o600)
    log.info("VAPID-Schluesselpaar erzeugt")
    return data


init_db()
API_TOKEN = load_api_token()

VAPID = ensure_vapid()
VAPID_KEY_PATH = os.path.join(DATA_DIR, "vapid_private.pem")
if not os.path.exists(VAPID_KEY_PATH):
    with open(VAPID_KEY_PATH, "w") as fh:
        fh.write(VAPID["private_pem"])
    os.chmod(VAPID_KEY_PATH, 0o600)


def push_to_users(user_ids, title, body, url):
    """Sendet Push an alle Abos der genannten Nutzer (im Hintergrund)."""
    if not user_ids:
        return

    def worker():
        try:
            from pywebpush import WebPushException, webpush
        except ImportError:
            return
        conn = raw_db()
        marks = ",".join("?" * len(user_ids))
        subs = conn.execute(
            f"SELECT * FROM push_subs WHERE user_id IN ({marks})",
            list(user_ids)).fetchall()
        for sub in subs:
            payload = json.dumps({"title": title, "body": body, "url": url})
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                    },
                    data=payload,
                    vapid_private_key=VAPID_KEY_PATH,
                    vapid_claims={"sub": "mailto:admin@localhost"},
                    ttl=86400,
                )
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                if status in (404, 410):
                    conn.execute("DELETE FROM push_subs WHERE id=?", (sub["id"],))
                    conn.commit()
                else:
                    log.warning("Push fehlgeschlagen: %s", exc)
            except Exception as exc:  # noqa: BLE001
                log.warning("Push-Fehler: %s", exc)
        conn.close()

    threading.Thread(target=worker, daemon=True).start()


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------
# Nur diese Typen liefern wir direkt im Browser aus. Der MIME-Typ eines
# Uploads kommt aus dem Multipart-Header des Clients, ist also frei waehlbar -
# ein "text/html" wuerde als Seite auf unserem eigenen Origin laufen und das
# Sitzungs-Cookie preisgeben. Alles Uebrige geht als Download raus.
IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp",
               "image/avif", "image/heic", "image/heif"}
# Video und Ton koennen im Abspieler laufen, ohne Skripte auszufuehren.
VIDEO_MIMES = {"video/mp4", "video/webm", "video/ogg", "video/quicktime"}
AUDIO_MIMES = {"audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav", "audio/webm",
               "audio/aac", "audio/flac"}
PLAY_MIMES = VIDEO_MIMES | AUDIO_MIMES
INLINE_MIMES = IMAGE_MIMES | PLAY_MIMES


def safe_mime(raw):
    mime = (raw or "").split(";")[0].strip().lower()
    return mime if mime in INLINE_MIMES else "application/octet-stream"


def statisch(dateiname):
    """Adresse einer statischen Datei mit Aenderungsstempel.

    Ohne diesen Anhang liefert der Browser nach einem Update weiter die alte
    app.js und style.css aus seinem Zwischenspeicher - die Oberflaeche sieht
    dann kaputt aus oder Knoepfe fehlen, obwohl das Add-on aktuell ist.
    """
    adresse = url_for("static", filename=dateiname)
    try:
        stempel = int(os.path.getmtime(os.path.join(app.static_folder, dateiname)))
    except OSError:
        return adresse
    return f"{adresse}?v={stempel}"


# Wie die Oberflaeche heissen soll. Das Add-on selbst bleibt "Chat Server" -
# hier geht es nur um den Namen, den die Leute lesen.
ANZEIGENAME_STANDARD = "Wosislos"
ANZEIGENAME_MAX = 40


def einstellung_lesen(schluessel, standard="", conn=None):
    conn = conn or db()
    row = conn.execute("SELECT wert FROM einstellungen WHERE schluessel=?",
                       (schluessel,)).fetchone()
    return row["wert"] if row and row["wert"] else standard


def einstellung_setzen(schluessel, wert, conn=None):
    conn = conn or db()
    conn.execute("INSERT INTO einstellungen (schluessel, wert) VALUES (?,?)"
                 " ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert",
                 (schluessel, wert))
    conn.commit()


def anzeigename():
    return einstellung_lesen("anzeigename", ANZEIGENAME_STANDARD)


@app.context_processor
def vorlagen_werte():
    """Steht allen Vorlagen zur Verfuegung - etwa fuer den Link zur Anmeldung."""
    return {"registration_open": ALLOW_REGISTRATION, "statisch": statisch,
            "anzeigename": anzeigename(),
            "csp_nonce": g.get("csp_nonce", "")}


# Kartenkacheln sind die einzige Stelle, an der die Oberflaeche etwas von
# einem fremden Server holt. Alles andere kommt von hier.
KACHEL_HERKUNFT = "https://tile.openstreetmap.org https://*.tile.openstreetmap.org"


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    # Ein Netz unter der Oberflaeche: sollte je ein fremder Text als HTML
    # durchrutschen, kann er wenigstens kein Skript starten und nichts
    # nachladen. Das eine Skript in der Seite traegt dafuer eine Kennung, die
    # bei jedem Aufruf wechselt.
    #
    # style-src braucht 'unsafe-inline': die Oberflaeche setzt Farben und
    # Groessen an einzelnen Elementen ueber style="...", und dafuer gibt es
    # keine Kennung. Angriffe ueber Stilangaben sind ungleich harmloser als
    # ueber Skripte.
    if "Content-Security-Policy" not in resp.headers:
        nonce = g.get("csp_nonce", "")
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' data: blob: {KACHEL_HERKUNFT}; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "form-action 'self'; "
            "frame-ancestors *")
    return resp


@app.before_request
def csp_nonce_setzen():
    g.csp_nonce = secrets.token_urlsafe(16)


def session_user(conn=None):
    """Der angemeldete Nutzer - oder None, wenn die Sitzung nicht mehr gilt.

    Eine Sitzung verfaellt sofort, wenn das Konto gesperrt wurde oder das
    Passwort sich geaendert hat (pw_version). Damit wirkt ein Zuruecksetzen
    durch den Administrator auf allen Geraeten, nicht erst beim Abmelden.
    """
    uid = session.get("uid")
    if not uid:
        return None
    conn = conn or db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if row is None or not row["active"]:
        return None
    # Sitzungen von vor diesem Update haben kein "pwv" - die zaehlen als 0 und
    # bleiben damit gueltig, solange das Passwort unveraendert ist.
    if session.get("pwv", 0) != row["pw_version"]:
        return None
    return row


def current_user():
    return session_user()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session_user() is None:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "nicht angemeldet"}), 401
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        me = session_user()
        if me is None:
            session.clear()
            return jsonify({"error": "nicht angemeldet"}), 401
        if not me["is_admin"]:
            return jsonify({"error": "Das darf nur ein Administrator."}), 403
        return fn(*args, **kwargs)
    return wrapper


def is_member(room_id, user_id):
    return db().execute(
        "SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",
        (room_id, user_id)).fetchone() is not None


def room_payload(room, uid, conn=None):
    conn = conn or db()
    members = conn.execute(
        "SELECT u.id, u.display_name, u.avatar FROM room_members m"
        " JOIN users u ON u.id=m.user_id WHERE m.room_id=?",
        (room["id"],)).fetchall()
    name = room["name"]
    if not room["is_group"]:
        other = [m for m in members if m["id"] != uid]
        name = other[0]["display_name"] if other else "Notizen"
    last = conn.execute(
        "SELECT m.id, m.body, m.created_at, m.file_id, m.deleted, u.display_name"
        " FROM messages m JOIN users u ON u.id=m.user_id"
        " WHERE m.room_id=? ORDER BY m.id DESC LIMIT 1",
        (room["id"],)).fetchone()
    eigenes = conn.execute(
        "SELECT last_read, hintergrund, stumm_bis FROM room_members"
        " WHERE room_id=? AND user_id=?",
        (room["id"], uid)).fetchone()
    unread = conn.execute(
        "SELECT COUNT(*) c FROM messages WHERE room_id=? AND id>? AND user_id<>?",
        (room["id"], eigenes["last_read"] if eigenes else 0, uid)).fetchone()["c"]
    with ONLINE_LOCK:
        online = [m["id"] for m in members if m["id"] in ONLINE]
    return {
        "id": room["id"],
        "name": name,
        "is_group": bool(room["is_group"]),
        "avatar": room["avatar"],
        "hintergrund": eigenes["hintergrund"] if eigenes else None,
        "stumm_bis": eigenes["stumm_bis"] if eigenes else None,
        "members": [dict(m) for m in members],
        "online": online,
        "unread": unread,
        "anruf": anruf_stand(room["id"]),
        "last": {
            "text": ("Nachricht geloescht" if last["deleted"]
                     else (last["body"] or ("Datei" if last["file_id"] else ""))) if last else "",
            "author": last["display_name"] if last else "",
            "at": last["created_at"] if last else 0,
        } if last else None,
    }


def join_user_sockets(user_id, room_id):
    """Offene Verbindungen eines Nutzers sofort dem neuen Raum zuordnen,
    damit Nachrichten ohne Neuladen ankommen."""
    try:
        sids = list(socketio.server.manager.get_participants("/", f"user:{user_id}"))
    except Exception:  # noqa: BLE001
        return
    for entry in sids:
        sid = entry[0] if isinstance(entry, tuple) else entry
        socketio.server.enter_room(sid, f"room:{room_id}", namespace="/")


def disconnect_user(user_id):
    """Offene Verbindungen eines Kontos trennen - nach Sperre, Loeschung oder
    zurueckgesetztem Passwort soll niemand weiter mitlesen."""
    try:
        sids = list(socketio.server.manager.get_participants("/", f"user:{user_id}"))
    except Exception:  # noqa: BLE001
        return
    for entry in sids:
        sid = entry[0] if isinstance(entry, tuple) else entry
        try:
            socketio.server.disconnect(sid, namespace="/")
        except Exception:  # noqa: BLE001
            pass


def msg_payload(row):
    deleted = bool(row["deleted"])
    out = {
        "id": row["id"],
        "room_id": row["room_id"],
        "user_id": row["user_id"],
        "author": row["display_name"],
        "album": row["album"],
        "weitergeleitet": bool(row["weitergeleitet"]),
        "sprachdauer": row["sprachdauer"],
        "ort": ({"lat": row["lat"], "lon": row["lon"]}
                if row["lat"] is not None and row["lon"] is not None else None),
        "poll": (poll_payload(row["poll_id"], session.get("uid"))
                 if row["poll_id"] else None),
        "event": (event_payload(row["event_id"], session.get("uid"))
                  if row["event_id"] else None),
        "body": "" if deleted else row["body"],
        "at": row["created_at"],
        "deleted": deleted,
        "file": None,
        "reply": None,
    }
    if row["reply_to"] and row["q_author"] is not None:
        out["reply"] = {
            "id": row["reply_to"],
            "author": row["q_author"],
            "text": "Nachricht geloescht" if row["q_deleted"]
                    else (row["q_body"] or ("Datei" if row["q_file"] else "")),
        }
    if deleted:
        return out
    if row["file_id"]:
        out["file"] = {
            "id": row["file_id"],
            "name": row["orig_name"],
            "mime": row["mime"],
            "size": row["size"],
        }
    return out


def poll_payload(poll_id, uid, conn=None):
    """Frage, Antworten, Stimmen - und was ich selbst gewaehlt habe."""
    conn = conn or db()
    poll = conn.execute("SELECT * FROM polls WHERE id=?", (poll_id,)).fetchone()
    if poll is None:
        return None
    optionen = conn.execute(
        "SELECT * FROM poll_options WHERE poll_id=? ORDER BY platz",
        (poll_id,)).fetchall()
    stimmen = conn.execute(
        "SELECT v.option_id, v.user_id, u.display_name FROM poll_votes v"
        " JOIN users u ON u.id=v.user_id WHERE v.poll_id=?",
        (poll_id,)).fetchall()
    je_option = {}
    for s in stimmen:
        je_option.setdefault(s["option_id"], []).append(
            {"id": s["user_id"], "name": s["display_name"]})
    # Wie viele Personen haben ueberhaupt abgestimmt? Bei Mehrfachwahl ist das
    # weniger als die Summe der Stimmen.
    teilnehmer = len({s["user_id"] for s in stimmen})
    return {
        "id": poll["id"],
        "frage": poll["frage"],
        "mehrfach": bool(poll["mehrfach"]),
        "teilnehmer": teilnehmer,
        "optionen": [{
            "id": o["id"],
            "text": o["text"],
            "stimmen": len(je_option.get(o["id"], [])),
            "wer": je_option.get(o["id"], []),
            "meine": any(w["id"] == uid for w in je_option.get(o["id"], [])),
        } for o in optionen],
    }


# Fuer Termine erlaubte Merkmale. Eine feste Liste, damit die Filter spaeter
# verlaesslich sind - freie Schlagworte waeren nach zwei Wochen ein Wildwuchs.
KATEGORIEN = ["musik", "tanz", "alkohol", "essen", "film", "sport",
              "spiele", "draussen", "kultur", "reden"]
ANTWORTEN = ("ja", "nein", "vielleicht")


def event_payload(event_id, uid, conn=None):
    """Termin mit Zu- und Absagen - und was ich selbst geantwortet habe."""
    conn = conn or db()
    ev = conn.execute(
        "SELECT e.*, u.display_name, u.avatar, f.mime FROM events e"
        " JOIN users u ON u.id=e.user_id"
        " LEFT JOIN files f ON f.id=e.file_id WHERE e.id=?",
        (event_id,)).fetchone()
    if ev is None:
        return None
    antworten = conn.execute(
        "SELECT a.antwort, a.user_id, u.display_name, u.avatar"
        " FROM event_antworten a JOIN users u ON u.id=a.user_id"
        " WHERE a.event_id=?", (event_id,)).fetchall()
    je_antwort = {a: [] for a in ANTWORTEN}
    meine = ""
    for a in antworten:
        if a["antwort"] in je_antwort:
            je_antwort[a["antwort"]].append(
                {"id": a["user_id"], "name": a["display_name"],
                 "avatar": a["avatar"]})
        if a["user_id"] == uid:
            meine = a["antwort"]
    gaeste = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM event_gaeste WHERE event_id=?",
        (event_id,)).fetchall()]
    return {
        "id": ev["id"],
        "room_id": ev["room_id"],
        "sicht": ev["sicht"] or "raum",
        "umkreis_km": ev["umkreis_km"],
        "gaeste": gaeste,
        "titel": ev["titel"],
        "beschreibung": ev["beschreibung"] or "",
        "ort_text": ev["ort_text"] or "",
        "ort": ({"lat": ev["lat"], "lon": ev["lon"]}
                if ev["lat"] is not None and ev["lon"] is not None else None),
        "beginnt_at": ev["beginnt_at"],
        "file_id": ev["file_id"],
        "kategorien": [k for k in (ev["kategorien"] or "").split(",") if k],
        "abgesagt": bool(ev["abgesagt"]),
        "von": {"id": ev["user_id"], "name": ev["display_name"],
                "avatar": ev["avatar"]},
        "meine": meine,
        "wer": je_antwort,
        "created_at": ev["created_at"],
    }


# Wer einen Termin sehen darf, der an keiner Unterhaltung haengt.
# "raum" ist der alte Weg und bleibt die Voreinstellung.
EVENT_SICHT = ("raum", "freunde", "umkreis")
EVENT_UMKREIS_MAX_KM = 25


def event_sichtbar(ev, uid, conn=None, ort=None):
    """Darf ich diesen Termin sehen?

    ev ist eine Zeile aus events. Fuer den Umkreis braucht es einen
    Standpunkt: entweder den mitgeschickten (ort) oder den, den ich gerade
    selbst teile. Ohne beides bleibt die Einladung unsichtbar - der Server
    weiss dann schlicht nicht, ob ich in der Naehe bin.
    """
    conn = conn or db()
    if ev["user_id"] == uid:
        return True
    sicht = ev["sicht"] or "raum"
    if sicht == "raum":
        return is_member(ev["room_id"], uid)
    if sicht == "freunde":
        return bool(conn.execute(
            "SELECT 1 FROM event_gaeste WHERE event_id=? AND user_id=?",
            (ev["id"], uid)).fetchone())
    if sicht == "umkreis":
        if ev["lat"] is None or ev["lon"] is None:
            return False
        wo = ort
        if wo is None:
            meiner = conn.execute(
                "SELECT lat, lon FROM live_orte WHERE user_id=? AND bis_at>?"
                " ORDER BY updated_at DESC LIMIT 1",
                (uid, int(time.time()))).fetchone()
            if meiner is None:
                return False
            wo = (meiner["lat"], meiner["lon"])
        weite = _entfernung_km(wo[0], wo[1], ev["lat"], ev["lon"])
        return weite <= (ev["umkreis_km"] or EVENT_UMKREIS_MAX_KM)
    return False


def event_gaeste_setzen(conn, event_id, uid, ids):
    """Die ausgewaehlten Freunde eines Termins neu setzen.

    Nur bestaetigte Freunde - eine erfundene Kennung soll niemanden
    hineinschmuggeln, der gar nicht dazugehoert.
    """
    freunde = meine_freunde(uid, conn)
    gewaehlt = set()
    for roh in (ids or []):
        try:
            n = int(roh)
        except (TypeError, ValueError):
            continue
        if n in freunde:
            gewaehlt.add(n)
    conn.execute("DELETE FROM event_gaeste WHERE event_id=?", (event_id,))
    conn.executemany(
        "INSERT INTO event_gaeste (event_id, user_id) VALUES (?,?)",
        [(event_id, n) for n in sorted(gewaehlt)])
    return gewaehlt


def _standort_aus_anfrage():
    """lat/lon aus der Abfrage - nur fuer diese eine Antwort, nie gespeichert."""
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    return (lat, lon)


def offene_bitten(conn=None):
    """Wie viele Leute gerade auf ein neues Passwort warten."""
    conn = conn or db()
    return conn.execute(
        "SELECT COUNT(*) c FROM passwort_bitten b"
        " JOIN users u ON u.id=b.user_id WHERE u.active=1").fetchone()["c"]


def offene_antraege(conn=None):
    """Wie viele Zugangsantraege noch auf eine Antwort warten.

    Nur fuer Administratoren gedacht: die Zahl steht am Zahnrad, damit ein
    Antrag nicht liegen bleibt, weil man die kurze Meldung verpasst hat.
    """
    conn = conn or db()
    marks = ",".join("?" * len(SYSTEM_USERS))
    return conn.execute(
        f"SELECT COUNT(*) c FROM users WHERE pending=1"
        f" AND username NOT IN ({marks})", SYSTEM_USERS).fetchone()["c"]


def mein_kreis(uid, conn=None):
    """Alle, mit denen ich etwas zu tun habe.

    Das sind meine bestaetigten Freunde und alle, mit denen ich mindestens
    eine Unterhaltung teile. Die Freundschaft reicht ueber die
    Unterhaltungen hinaus - so erreicht eine Empfehlung auch jemanden, mit
    dem ich noch nie geschrieben habe. Umgekehrt bleibt die Familie im
    Kreis, ohne dass alle einander erst bestaetigen muessen.
    """
    conn = conn or db()
    rows = conn.execute(
        "SELECT DISTINCT b.user_id FROM room_members a"
        " JOIN room_members b ON b.room_id=a.room_id"
        " WHERE a.user_id=? AND b.user_id<>?", (uid, uid)).fetchall()
    return {r["user_id"] for r in rows} | meine_freunde(uid, conn)


# Wer darf meinen Standort sehen? Bisher immer nur eine Unterhaltung. Jetzt
# zusaetzlich der ganze Freundeskreis oder alle in einem Umkreis. Die
# Entfernung wird beim Abrufen gerechnet - so wandert die Freigabe mit, wenn
# man sich bewegt, und es liegt keine Liste von Personen herum.
FREIGABE_ARTEN = ("raum", "freunde", "umkreis")
UMKREIS_MAX_KM = 25


def _entfernung_km(a_lat, a_lon, b_lat, b_lon):
    """Luftlinie in Kilometern (Haversine)."""
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    x = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(x)))


def live_sichtbar(uid, conn=None):
    """Laufende Standortfreigaben, die ich sehen darf.

    Drei Wege dorthin: die Freigabe gilt einer Unterhaltung, in der ich bin;
    sie gilt allen Freunden und ich bin einer; oder sie gilt einem Umkreis
    und ich stehe gerade darin. Fuer den Umkreis muss ich selbst einen
    Standort teilen - sonst weiss der Server nicht, wo ich bin, und das soll
    er auch nur dann wissen.
    """
    conn = conn or db()
    jetzt = int(time.time())
    rows = conn.execute(
        "SELECT l.*, u.display_name, u.avatar, r.name AS raumname, r.is_group"
        " FROM live_orte l JOIN users u ON u.id=l.user_id"
        " LEFT JOIN rooms r ON r.id=l.room_id"
        " WHERE l.bis_at>? ORDER BY l.updated_at DESC", (jetzt,)).fetchall()
    meine_raeume = {r["room_id"] for r in conn.execute(
        "SELECT room_id FROM room_members WHERE user_id=?", (uid,)).fetchall()}
    freunde = meine_freunde(uid, conn)
    # Der eigene Standort - Grundlage fuer die Umkreisfreigaben
    meiner = next((r for r in rows if r["user_id"] == uid), None)

    raus = []
    for r in rows:
        art = r["art"] or "raum"
        if r["user_id"] == uid:
            pass
        elif art == "raum":
            if r["room_id"] not in meine_raeume:
                continue
        elif art == "freunde":
            if r["user_id"] not in freunde:
                continue
        elif art == "umkreis":
            if meiner is None:
                continue
            weite = _entfernung_km(meiner["lat"], meiner["lon"], r["lat"], r["lon"])
            if weite > (r["umkreis_km"] or UMKREIS_MAX_KM):
                continue
        else:
            continue
        name = r["raumname"]
        if art != "raum":
            name = "Freunde" if art == "freunde" else f"{r['umkreis_km']} km"
        elif not r["is_group"]:
            name = "Direkt"
        raus.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "begonnen_at": r["begonnen_at"] or r["updated_at"],
            "name": r["display_name"],
            "avatar": r["avatar"],
            "room_id": r["room_id"],
            "raum": name,
            "art": art,
            "lat": r["lat"],
            "lon": r["lon"],
            "genauigkeit": r["genauigkeit"],
            "bis_at": r["bis_at"],
            "updated_at": r["updated_at"],
            "ich": r["user_id"] == uid,
        })
    return raus


def _koordinaten(data):
    """Breite und Laenge aus einer Anfrage - oder None, wenn unbrauchbar."""
    try:
        lat, lon = float(data.get("lat")), float(data.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    return lat, lon


def _genauigkeit(data):
    try:
        wert = float(data.get("genauigkeit"))
    except (TypeError, ValueError):
        return None
    return wert if 0 <= wert <= 100000 else None


def stimmung_mitteilen(uid, conn=None):
    """Meinen Kreis anstossen, die Pinnwand neu zu laden."""
    for ziel in mein_kreis(uid, conn) | {uid}:
        socketio.emit("stimmung_geaendert", {}, to=f"user:{ziel}")


def stimmung_payload(row, uid, conn=None):
    conn = conn or db()
    mit = conn.execute(
        "SELECT m.user_id, u.display_name, u.avatar FROM stimmung_mit m"
        " JOIN users u ON u.id=m.user_id WHERE m.stimmung_id=?",
        (row["id"],)).fetchall()
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["display_name"],
        "avatar": row["avatar"],
        "emoji": row["emoji"] or "",
        "text": row["text"],
        "ort": ({"lat": row["lat"], "lon": row["lon"]}
                if row["lat"] is not None and row["lon"] is not None else None),
        "bis_at": row["bis_at"],
        "created_at": row["created_at"],
        "mit": [{"id": m["user_id"], "name": m["display_name"],
                 "avatar": m["avatar"]} for m in mit],
        "ich_mache_mit": any(m["user_id"] == uid for m in mit),
        "meine": row["user_id"] == uid,
    }


def stimmungen_sichtbar(uid, conn=None):
    """Eigene Stimmung plus die aus meinem Kreis, solange sie gilt."""
    conn = conn or db()
    jetzt = int(time.time())
    erlaubt = mein_kreis(uid, conn) | {uid}
    rows = conn.execute(
        "SELECT s.*, u.display_name, u.avatar FROM stimmungen s"
        " JOIN users u ON u.id=s.user_id WHERE s.bis_at>?"
        " ORDER BY s.created_at DESC", (jetzt,)).fetchall()
    return [stimmung_payload(r, uid, conn) for r in rows
            if r["user_id"] in erlaubt]


# Ein abgesagter Termin verschwindet aus dem Verlauf. Die Nachricht bleibt
# in der Datenbank - die Zu- und Absagen haengen daran -, sie wird nur nicht
# mehr ausgeliefert. Sonst stuende eine durchgestrichene Einladung fuer
# immer da.
OHNE_ABGESAGTE = (" AND (m.event_id IS NULL OR m.event_id NOT IN"
                  " (SELECT id FROM events WHERE abgesagt=1))")

MSG_QUERY = (
    "SELECT m.*, u.display_name, f.orig_name, f.mime, f.size,"
    " p.body AS q_body, p.file_id AS q_file, p.deleted AS q_deleted,"
    " pu.display_name AS q_author"
    " FROM messages m JOIN users u ON u.id=m.user_id"
    " LEFT JOIN files f ON f.id=m.file_id"
    " LEFT JOIN messages p ON p.id=m.reply_to"
    " LEFT JOIN users pu ON pu.id=p.user_id")


# --------------------------------------------------------------------------
# Seiten
# --------------------------------------------------------------------------
# Die Registrierung steht offen im Netz. Ohne Bremse koennte sie jemand mit
# Antraegen fluten - drei je Stunde und Adresse reichen fuer echte Anfragen.
ANTRAEGE = {}
ANTRAEGE_LOCK = threading.Lock()
ANTRAEGE_PRO_STUNDE = 3
# Zweite Bremse, die nicht an der Adresse haengt: mehr als so viele
# unbeantwortete Antraege duerfen nicht gleichzeitig offen sein. Wer die
# Absenderadresse faelscht, kommt an der ersten Bremse vorbei - an dieser
# nicht. Der Administrator raeumt sie ab, dann geht es weiter.
ANTRAEGE_OFFEN_MAX = 20


def zu_viele_antraege(adresse, grenze=None):
    grenze = ANTRAEGE_PRO_STUNDE if grenze is None else grenze
    jetzt = time.time()
    with ANTRAEGE_LOCK:
        frisch = [t for t in ANTRAEGE.get(adresse, []) if jetzt - t < 3600]
        # Nebenbei aufraeumen, damit die Tabelle nicht unbegrenzt waechst
        for schluessel in [k for k, v in ANTRAEGE.items()
                           if all(jetzt - t >= 3600 for t in v)]:
            ANTRAEGE.pop(schluessel, None)
        if len(frisch) >= grenze:
            ANTRAEGE[adresse] = frisch
            return True
        frisch.append(jetzt)
        ANTRAEGE[adresse] = frisch
        return False


@app.route("/register", methods=["GET", "POST"])
def register_page():
    """Selbstregistrierung - das Konto wartet danach auf Freigabe."""
    if not ALLOW_REGISTRATION:
        return render_template("register.html", closed=True), 403
    if request.method == "GET":
        return render_template("register.html")

    formular = {
        "username": (request.form.get("username") or "").strip().lower(),
        "display_name": (request.form.get("display_name") or "").strip(),
        "email": (request.form.get("email") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "note": (request.form.get("note") or "").strip(),
        "geburtstag": (request.form.get("geburtstag") or "").strip(),
    }
    passwort = request.form.get("password") or ""

    def zurueck(fehler):
        return render_template("register.html", error=fehler, form=formular)

    if not formular["username"] or not formular["display_name"]:
        return zurueck("Benutzername und Anzeigename werden gebraucht.")
    if formular["username"] in SYSTEM_USERS:
        return zurueck("Dieser Benutzername ist vergeben.")
    if len(passwort) < MIN_PASSWORD:
        return zurueck(f"Das Passwort braucht mindestens {MIN_PASSWORD} Zeichen.")
    if not formular["email"] and not formular["phone"]:
        return zurueck("Gib eine E-Mail-Adresse oder eine Telefonnummer an, "
                       "damit wir dich erreichen koennen.")
    if not formular["note"]:
        return zurueck("Schreib kurz, weshalb du Zugang moechtest.")
    # Das Geburtsdatum ist freiwillig - aber wenn eines dasteht, muss es
    # stimmen, sonst taucht die Person nie in der Terminliste auf.
    geburtstag, fehler = geburtstag_pruefen(formular["geburtstag"])
    if fehler:
        return zurueck(fehler)
    # Ohne Haken kein Konto - und der Zeitpunkt wird festgehalten, sonst
    # laesst sich spaeter nicht sagen, dass jemand zugestimmt hat.
    if not request.form.get("zustimmung"):
        return zurueck("Ohne dein Einverstaendnis zur Speicherung koennen wir "
                       "kein Konto anlegen.")
    if offene_antraege() >= ANTRAEGE_OFFEN_MAX:
        log.warning("Zugangsantrag abgewiesen: %s Antraege liegen schon offen",
                    ANTRAEGE_OFFEN_MAX)
        return render_template(
            "register.html",
            error="Zurzeit liegen zu viele unbeantwortete Anträge vor. "
                  "Bitte versuche es später noch einmal."), 429
    if zu_viele_antraege(_absender()):
        return zurueck("Es sind schon mehrere Antraege von dir eingegangen. "
                       "Bitte warte eine Stunde.")

    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, pw_hash, is_admin, active,"
            " pending, email, phone, note, geburtstag, zustimmung_at,"
            " created_at) VALUES (?,?,?,0,0,1,?,?,?,?,?,?)",
            (formular["username"], formular["display_name"],
             generate_password_hash(passwort), formular["email"][:200],
             formular["phone"][:60], formular["note"][:1000], geburtstag,
             int(time.time()), int(time.time())))
        conn.commit()
    except sqlite3.IntegrityError:
        return zurueck("Diesen Benutzernamen gibt es schon.")

    row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    log.info("Neuer Zugangsantrag von '%s'", formular["username"])
    socketio.emit("user_pending", user_payload(row))
    benachrichtige_admins(conn, formular["display_name"])
    return render_template("register.html", done=True)


def benachrichtige_admins(conn, name):
    """Administratoren per Push ueber einen neuen Antrag informieren."""
    admins = [r["id"] for r in conn.execute(
        "SELECT id FROM users WHERE is_admin=1 AND active=1").fetchall()]
    if not admins:
        return
    ziel = f"{EXTERNAL_URL}/" if EXTERNAL_URL else "./"
    push_to_users(admins, "Neuer Zugangsantrag",
                  f"{name} moechte Zugang zum Chat", ziel)


# Die Anmeldeseite ist ueber den Tunnel oeffentlich erreichbar. Ohne Bremse
# koennte jemand in Ruhe Passwoerter durchprobieren. Gezaehlt wird nach
# Absender *und* nach Kontoname - sonst hilft es nichts, wenn die Versuche
# von wechselnden Adressen kommen.
VERSUCHE = {}
VERSUCHE_LOCK = threading.Lock()
SPERRE_SEKUNDEN = 900
# Je Konto streng: acht Fehlgriffe reichen niemandem, der sein Passwort kennt.
MAX_JE_KONTO = 8
# Je Absender grosszuegig: hinter Tunnel und Reverse Proxy koennen alle
# dieselbe Adresse haben - eine strenge Grenze wuerde die ganze Familie
# aussperren, sobald jemand ein einzelnes Konto angreift.
MAX_JE_ADRESSE = 40


def _absender():
    """Woher die Anfrage kommt - so gut, wie es sich feststellen laesst.

    X-Forwarded-For schickt der Client mit; wer will, schreibt dort etwas
    Erfundenes hinein und umgeht damit jede Bremse, die nach Adresse zaehlt.
    Cloudflare dagegen *ersetzt* CF-Connecting-IP durch die wirkliche Adresse,
    egal was der Client behauptet - dieser Wert ist also belastbar, solange
    das Add-on nur ueber den Tunnel erreichbar ist.

    Bleibt es bei X-Forwarded-For, ist der Wert nur ein Anhaltspunkt. Deshalb
    haengt keine Bremse allein daran: die Anmeldung zaehlt zusaetzlich je
    Konto, die Registrierung zusaetzlich als Gesamtzahl.
    """
    echt = request.headers.get("CF-Connecting-IP", "").strip()
    if echt:
        return echt
    weiter = request.headers.get("X-Forwarded-For", "")
    return (weiter.split(",")[0].strip() if weiter
            else (request.remote_addr or "?"))


def gesperrt(schluessel, grenze):
    """Sind fuer diesen Schluessel zu viele Fehlversuche aufgelaufen?"""
    jetzt = time.time()
    with VERSUCHE_LOCK:
        for k in [k for k, v in VERSUCHE.items()
                  if all(jetzt - z >= SPERRE_SEKUNDEN for z in v)]:
            VERSUCHE.pop(k, None)
        frisch = [z for z in VERSUCHE.get(schluessel, [])
                  if jetzt - z < SPERRE_SEKUNDEN]
        VERSUCHE[schluessel] = frisch
        return len(frisch) >= grenze


def fehlversuch(*schluessel):
    jetzt = time.time()
    with VERSUCHE_LOCK:
        for k in schluessel:
            VERSUCHE.setdefault(k, []).append(jetzt)


def versuche_vergessen(*schluessel):
    with VERSUCHE_LOCK:
        for k in schluessel:
            VERSUCHE.pop(k, None)


# Wer sein Passwort vergessen hat, kann es sich nicht selbst schicken lassen -
# das Add-on verschickt keine Mail. Stattdessen erfaehrt der Administrator
# davon und setzt es zurueck. Dieselbe Bremse wie bei den Zugangsantraegen,
# damit daraus keine Flut wird.
BITTEN_PRO_STUNDE = 3


@app.route("/passwort-vergessen", methods=["GET", "POST"])
def passwort_vergessen():
    """Bitte um ein neues Passwort - der Administrator setzt es zurueck."""
    if request.method == "GET":
        return render_template("vergessen.html")

    name = (request.form.get("username") or "").strip().lower()
    if zu_viele_antraege(_absender(), BITTEN_PRO_STUNDE):
        log.warning("Passwortbitte gebremst fuer %r", name or "(leer)")
        return render_template(
            "vergessen.html",
            error="Zu viele Anfragen. Bitte warte eine Stunde."), 429

    conn = db()
    row = conn.execute(
        "SELECT id, display_name FROM users"
        " WHERE lower(username)=? AND active=1 AND pending=0", (name,)).fetchone()
    # Immer dieselbe Antwort, ob es das Konto gibt oder nicht. Sonst liesse
    # sich hier durchprobieren, welche Benutzernamen vergeben sind.
    if row is not None:
        conn.execute("INSERT INTO passwort_bitten (user_id, created_at)"
                     " VALUES (?,?) ON CONFLICT(user_id) DO UPDATE"
                     " SET created_at=excluded.created_at",
                     (row["id"], int(time.time())))
        conn.commit()
        admins = [r["id"] for r in conn.execute(
            "SELECT id FROM users WHERE is_admin=1 AND active=1").fetchall()]
        ziel = f"{EXTERNAL_URL}/" if EXTERNAL_URL else "./"
        push_to_users(admins, "Passwort vergessen",
                      f"{row['display_name']} braucht ein neues Passwort", ziel)
        socketio.emit("passwort_bitte", {"name": row["display_name"]})
        log.info("Passwortbitte von Nutzer %s", row["id"])
    return render_template("vergessen.html", done=True)


@app.get("/api/passwort-bitten")
@admin_required
def api_passwort_bitten():
    """Wer wartet auf ein neues Passwort."""
    rows = db().execute(
        "SELECT b.user_id, b.created_at, u.display_name, u.username, u.email"
        " FROM passwort_bitten b JOIN users u ON u.id=b.user_id"
        " WHERE u.active=1 ORDER BY b.created_at", ()).fetchall()
    return jsonify([{"user_id": r["user_id"], "name": r["display_name"],
                     "username": r["username"], "email": r["email"] or "",
                     "at": r["created_at"]} for r in rows])


@app.delete("/api/passwort-bitten/<int:user_id>")
@admin_required
def api_passwort_bitte_weg(user_id):
    """Die Bitte abhaken, ohne das Passwort zu aendern."""
    conn = db()
    conn.execute("DELETE FROM passwort_bitten WHERE user_id=?", (user_id,))
    conn.commit()
    return jsonify({"ok": True})


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        adresse, konto = f"ip:{_absender()}", f"konto:{username}"
        if gesperrt(konto, MAX_JE_KONTO) or gesperrt(adresse, MAX_JE_ADRESSE):
            log.warning("Anmeldung gebremst: zu viele Fehlversuche fuer '%s'",
                        username or "(leer)")
            return render_template(
                "login.html",
                error="Zu viele Fehlversuche. Bitte warte eine Viertelstunde."), 429
        # Neue Konten werden klein gespeichert, das Konto aus admin_user aber
        # so, wie es in der Option steht - deshalb hier unabhaengig von der
        # Schreibweise suchen.
        row = db().execute("SELECT * FROM users WHERE lower(username)=?",
                           (username,)).fetchone()
        if row is not None and row["pending"]:
            return render_template(
                "login.html", error="Dein Zugang wurde noch nicht freigegeben. "
                                    "Ein Administrator prueft die Anfrage.")
        if row is not None and not row["active"]:
            return render_template(
                "login.html", error="Dieses Konto ist gesperrt. Wende dich an einen Administrator.")
        if row and check_password_hash(row["pw_hash"], password):
            versuche_vergessen(adresse, konto)
            session.permanent = True
            session["uid"] = row["id"]
            session["pwv"] = row["pw_version"]
            return redirect(url_for("index"))
        fehlversuch(adresse, konto)
        return render_template("login.html",
                               error="Benutzername oder Passwort stimmt nicht.")
    if session.get("uid"):
        return redirect(url_for("index"))
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/")
@login_required
def index():
    user = current_user()
    return render_template("index.html", me=dict(user), base=request.script_root,
                           vapid=VAPID["public_key"])


@app.get("/manifest.webmanifest")
def manifest():
    """Das Manifest wird erzeugt, damit die Symbole eine Kennung tragen.

    Als feste Datei behielt der Browser - und schlimmer: das Betriebssystem
    nach dem Hinzufuegen zum Home-Bildschirm - das alte Symbol. Die Adressen
    wechseln jetzt mit der Datei. Relative Angaben loesen gegen diese Route
    auf, unter Ingress also gegen den Ingress-Pfad.
    """
    return jsonify({
        "name": anzeigename(),
        "short_name": anzeigename(),
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#0e1416",
        "theme_color": "#0e1416",
        "icons": [
            {"src": statisch("icon-192.png"), "sizes": "192x192",
             "type": "image/png", "purpose": "any"},
            {"src": statisch("icon-512.png"), "sizes": "512x512",
             "type": "image/png", "purpose": "any"},
        ],
    })


@app.route("/sw.js")
def service_worker():
    resp = app.send_static_file("sw.js")
    resp.headers["Service-Worker-Allowed"] = request.script_root or "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/state")
@login_required
def api_state():
    uid = session["uid"]
    me = current_user()
    conn = db()
    rooms = conn.execute(
        "SELECT r.* FROM rooms r JOIN room_members m ON m.room_id=r.id"
        " WHERE m.user_id=?", (uid,)).fetchall()
    marks = ",".join("?" * len(SYSTEM_USERS))
    users = conn.execute(
        "SELECT id, username, display_name, is_admin, active, avatar FROM users"
        f" WHERE username NOT IN ({marks}) AND pending=0 ORDER BY display_name",
        SYSTEM_USERS).fetchall()
    with ONLINE_LOCK:
        online = list(ONLINE.keys())
    payload = [room_payload(r, uid, conn) for r in rooms]
    payload.sort(key=lambda r: (r["last"]["at"] if r["last"] else 0), reverse=True)
    return jsonify({
        "me": {"id": uid, "name": me["display_name"],
               "is_admin": bool(me["is_admin"]), "avatar": me["avatar"],
               "kacheln": bool(me["karten_kacheln"]),
               "geburtstag": me["geburtstag"],
               "ton_stufe": me["ton_stufe"] or "alle",
               "blasenfarbe": me["blasenfarbe"],
               "karten_app": me["karten_app"] or "geraet",
               "klingelton": me["klingelton"] or "klassisch",
               "antraege": offene_antraege(conn) if me["is_admin"] else 0,
               "bitten": offene_bitten(conn) if me["is_admin"] else 0,
               "geburtstage_an": bool(me["geburtstage_an"]),
               "gesehen": gesehen_lesen(me)},
        "anzeigename": anzeigename(),
        "rooms": payload,
        "users": [dict(u) for u in users],
        "online": online,
        "freunde": sorted(meine_freunde(uid, conn)),
        "freund_anfragen": offene_anfragen(uid, conn),
        "live": live_sichtbar(uid, conn),
        "stimmung": stimmungen_sichtbar(uid, conn),
    })


@app.get("/api/rooms/<int:room_id>/messages")
@login_required
def api_messages(room_id):
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    before = request.args.get("before", type=int)
    um = request.args.get("um", type=int)
    limit = min(request.args.get("limit", 50, type=int), 200)
    if um:
        # Rund um eine bestimmte Nachricht - dorthin springt die Suche. Die
        # Haelfte davor, die Haelfte danach, damit der Treffer in der Mitte
        # steht und man sieht, worum es ging.
        halb = max(1, limit // 2)
        davor = db().execute(MSG_QUERY + " WHERE m.room_id=? AND m.id<=?"
                             + OHNE_ABGESAGTE + " ORDER BY m.id DESC LIMIT ?",
                             (room_id, um, halb)).fetchall()
        danach = db().execute(MSG_QUERY + " WHERE m.room_id=? AND m.id>?"
                              + OHNE_ABGESAGTE + " ORDER BY m.id LIMIT ?",
                              (room_id, um, halb)).fetchall()
        rows = list(reversed(davor)) + list(danach)
        return jsonify([msg_payload(r) for r in rows])
    if before:
        rows = db().execute(MSG_QUERY + " WHERE m.room_id=? AND m.id<?"
                            + OHNE_ABGESAGTE + " ORDER BY m.id DESC LIMIT ?",
                            (room_id, before, limit)).fetchall()
    else:
        rows = db().execute(MSG_QUERY + " WHERE m.room_id=?"
                            + OHNE_ABGESAGTE + " ORDER BY m.id DESC LIMIT ?",
                            (room_id, limit)).fetchall()
    return jsonify([msg_payload(r) for r in reversed(rows)])


@app.get("/api/suche")
@login_required
def api_suche():
    """Nachrichten durchsuchen - in einer Unterhaltung oder in allen.

    Gesucht wird im Text und in Dateinamen. Geloeschte Nachrichten bleiben
    aussen vor; ihr Text steht zwar noch in der Datenbank, aber wer sie
    geloescht hat, will sie nicht ueber die Suche wiederfinden.
    """
    uid = session["uid"]
    frage = (request.args.get("q") or "").strip()
    if len(frage) < 2:
        return jsonify({"treffer": [], "mehr": False})
    raum = request.args.get("room", type=int)
    grenze = min(request.args.get("limit", 60, type=int), 200)
    # LIKE kennt % und _ als Platzhalter. Wer nach "100_" sucht, meint das
    # aber woertlich - deshalb ein eigenes Fluchtzeichen.
    muster = "%" + (frage.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")) + "%"
    args = [uid]
    sql = (MSG_QUERY + " JOIN room_members rm ON rm.room_id=m.room_id"
           " AND rm.user_id=? WHERE m.deleted=0"
           " AND (m.body LIKE ? ESCAPE '\\' OR f.orig_name LIKE ? ESCAPE '\\')"
           + OHNE_ABGESAGTE)
    args += [muster, muster]
    if raum:
        if not is_member(raum, uid):
            abort(403)
        sql += " AND m.room_id=?"
        args.append(raum)
    sql += " ORDER BY m.id DESC LIMIT ?"
    args.append(grenze + 1)
    rows = db().execute(sql, args).fetchall()
    mehr = len(rows) > grenze
    return jsonify({"treffer": [msg_payload(r) for r in rows[:grenze]],
                    "mehr": mehr})


@app.post("/api/rooms/<int:room_id>/read")
@login_required
def api_mark_read(room_id):
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    last = db().execute("SELECT MAX(id) m FROM messages WHERE room_id=?",
                        (room_id,)).fetchone()["m"] or 0
    db().execute("UPDATE room_members SET last_read=? WHERE room_id=? AND user_id=?",
                 (last, room_id, uid))
    db().commit()
    return jsonify({"ok": True, "last_read": last})


@app.post("/api/rooms")
@login_required
def api_create_room():
    uid = session["uid"]
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    members = set(int(x) for x in data.get("members", []))
    members.add(uid)
    conn = db()
    now = int(time.time())

    if not data.get("is_group"):
        if len(members) != 2:
            return jsonify({"error": "Ein Direktchat braucht genau eine Gegenseite."}), 400
        other = [m for m in members if m != uid][0]
        existing = conn.execute(
            "SELECT r.id FROM rooms r"
            " JOIN room_members a ON a.room_id=r.id AND a.user_id=?"
            " JOIN room_members b ON b.room_id=r.id AND b.user_id=?"
            " WHERE r.is_group=0", (uid, other)).fetchone()
        if existing:
            return jsonify({"id": existing["id"], "existing": True})
        cur = conn.execute(
            "INSERT INTO rooms (name, is_group, created_by, created_at) VALUES (NULL,0,?,?)",
            (uid, now))
    else:
        if not name:
            return jsonify({"error": "Die Gruppe braucht einen Namen."}), 400
        cur = conn.execute(
            "INSERT INTO rooms (name, is_group, created_by, created_at) VALUES (?,1,?,?)",
            (name, uid, now))
    room_id = cur.lastrowid
    conn.executemany(
        "INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)",
        [(room_id, m) for m in members])
    conn.commit()
    room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    for member in members:
        join_user_sockets(member, room_id)
        socketio.emit("room_added", room_payload(room, member, conn),
                      to=f"user:{member}")
    return jsonify({"id": room_id})


def raum_aufraeumen(conn, room_id):
    """Raum mitsamt Nachrichten, Anhaengen und Bild entfernen."""
    dateien = [r["file_id"] for r in conn.execute(
        "SELECT DISTINCT file_id FROM messages WHERE room_id=? AND file_id IS NOT NULL",
        (room_id,)).fetchall()]
    raum = conn.execute("SELECT avatar FROM rooms WHERE id=?", (room_id,)).fetchone()
    # Termine haengen an der Unterhaltung - mit ihr verschwinden auch die
    # Zusagen, die Bilder und laufende Standortfreigaben.
    dateien += [r["file_id"] for r in conn.execute(
        "SELECT file_id FROM events WHERE room_id=? AND file_id IS NOT NULL",
        (room_id,)).fetchall()]
    conn.execute("DELETE FROM event_antworten WHERE event_id IN"
                 " (SELECT id FROM events WHERE room_id=?)", (room_id,))
    conn.execute("DELETE FROM events WHERE room_id=?", (room_id,))
    conn.execute("DELETE FROM live_orte WHERE room_id=?", (room_id,))
    conn.execute("DELETE FROM messages WHERE room_id=?", (room_id,))
    conn.execute("DELETE FROM room_members WHERE room_id=?", (room_id,))
    conn.execute("DELETE FROM rooms WHERE id=?", (room_id,))
    conn.commit()
    for file_id in dateien:
        datei_aufraeumen(conn, file_id)
    if raum and raum["avatar"]:
        avatar_entfernen(raum["avatar"])


@app.post("/api/rooms/<int:room_id>/leave")
@login_required
def api_leave_room(room_id):
    """Die Unterhaltung fuer mich beenden - andere behalten sie."""
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    conn = db()
    conn.execute("DELETE FROM room_members WHERE room_id=? AND user_id=?",
                 (room_id, uid))
    # Wer geht, teilt hier auch seinen Standort nicht mehr
    conn.execute("DELETE FROM live_orte WHERE room_id=? AND user_id=?",
                 (room_id, uid))
    conn.commit()
    # Bleibt niemand ausser dem Bot uebrig, kann der Raum ganz weg
    rest = conn.execute(
        "SELECT COUNT(*) c FROM room_members m JOIN users u ON u.id=m.user_id"
        " WHERE m.room_id=? AND u.username<>?", (room_id, BOT_USERNAME)).fetchone()["c"]
    if rest == 0:
        raum_aufraeumen(conn, room_id)
        socketio.emit("room_removed", {"id": room_id})
    else:
        socketio.emit("room_removed", {"id": room_id}, to=f"user:{uid}")
        socketio.emit("room_changed", {"id": room_id}, to=f"room:{room_id}")
    log.info("Nutzer %s hat Raum %s verlassen", uid, room_id)
    return jsonify({"ok": True, "geloescht": rest == 0})


@app.delete("/api/rooms/<int:room_id>")
@admin_required
def api_delete_room(room_id):
    """Die Unterhaltung fuer alle entfernen - samt Nachrichten und Anhaengen."""
    conn = db()
    if conn.execute("SELECT 1 FROM rooms WHERE id=?", (room_id,)).fetchone() is None:
        return jsonify({"error": "Diese Unterhaltung gibt es nicht."}), 404
    raum_aufraeumen(conn, room_id)
    socketio.emit("room_removed", {"id": room_id})
    log.info("Raum %s wurde vollstaendig geloescht", room_id)
    return jsonify({"ok": True})


@app.post("/api/rooms/<int:room_id>/members")
@login_required
def api_add_member(room_id):
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    conn = db()
    room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if not room or not room["is_group"]:
        return jsonify({"error": "Nur Gruppen koennen Mitglieder aufnehmen."}), 400
    new_id = int(request.get_json(force=True).get("user_id"))
    conn.execute("INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)",
                 (room_id, new_id))
    conn.commit()
    join_user_sockets(new_id, room_id)
    socketio.emit("room_added", room_payload(room, new_id, conn), to=f"user:{new_id}")
    # Auch die schon Anwesenden muessen es erfahren - sonst fehlt der Neue in
    # ihrer Mitgliederliste, bis sie die Seite neu laden.
    socketio.emit("room_changed", {"id": room_id}, to=f"room:{room_id}")
    log.info("Nutzer %s wurde zu Raum %s hinzugefuegt", new_id, room_id)
    return jsonify({"ok": True})


MIN_PASSWORD = 6


def target_user(user_id):
    """Zielkonto einer Verwaltungsaktion pruefen.

    Gibt (row, fehlerantwort) zurueck - genau eines davon ist gesetzt.
    """
    row = db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        return None, (jsonify({"error": "Dieses Konto gibt es nicht."}), 404)
    if row["username"] in SYSTEM_USERS:
        return None, (jsonify({"error": "Systemkonten lassen sich nicht "
                                        "verwalten."}), 400)
    return row, None


def other_admins(exclude_id):
    """Wie viele aktive Administratoren gibt es ausser diesem einen?"""
    return db().execute(
        "SELECT COUNT(*) c FROM users WHERE is_admin=1 AND active=1 AND id<>?",
        (exclude_id,)).fetchone()["c"]


def user_payload(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "is_admin": bool(row["is_admin"]),
        "active": bool(row["active"]),
        "pending": bool(row["pending"]),
        "email": row["email"] or "",
        "phone": row["phone"] or "",
        "note": row["note"] or "",
        "created_at": row["created_at"],
    }


@app.get("/api/users")
@admin_required
def api_list_users():
    marks = ",".join("?" * len(SYSTEM_USERS))
    rows = db().execute(
        "SELECT * FROM users"
        f" WHERE username NOT IN ({marks})"
        " ORDER BY pending DESC, active DESC, display_name", SYSTEM_USERS).fetchall()
    return jsonify([user_payload(r) for r in rows])


@app.post("/api/users")
@admin_required
def api_create_user():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    display = (data.get("display_name") or username).strip()
    password = data.get("password") or ""
    if not username:
        return jsonify({"error": "Der Benutzername fehlt."}), 400
    if username in SYSTEM_USERS:
        return jsonify({"error": "Dieser Benutzername ist vergeben."}), 400
    if len(password) < MIN_PASSWORD:
        return jsonify({"error": f"Das Passwort braucht mindestens "
                                 f"{MIN_PASSWORD} Zeichen."}), 400
    try:
        cur = db().execute(
            "INSERT INTO users (username, display_name, pw_hash, is_admin, created_at)"
            " VALUES (?,?,?,?,?)",
            (username, display, generate_password_hash(password),
             1 if data.get("is_admin") else 0, int(time.time())))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Diesen Benutzernamen gibt es schon."}), 400
    row = db().execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(user_payload(row))


@app.post("/api/users/<int:user_id>/password")
@admin_required
def api_reset_password(user_id):
    """Passwort zuruecksetzen - meldet das Konto auf allen Geraeten ab."""
    row, err = target_user(user_id)
    if err:
        return err
    new = (request.get_json(force=True).get("password") or "")
    if len(new) < MIN_PASSWORD:
        return jsonify({"error": f"Das Passwort braucht mindestens "
                                 f"{MIN_PASSWORD} Zeichen."}), 400
    db().execute("UPDATE users SET pw_hash=?, pw_version=pw_version+1 WHERE id=?",
                 (generate_password_hash(new), user_id))
    # Wer ein neues Passwort bekommen hat, wartet nicht mehr darauf
    db().execute("DELETE FROM passwort_bitten WHERE user_id=?", (user_id,))
    db().commit()
    if row["id"] == session.get("uid"):
        session["pwv"] = row["pw_version"] + 1  # eigene Sitzung weiterlaufen lassen
    else:
        disconnect_user(user_id)
    log.info("Passwort von '%s' wurde zurueckgesetzt", row["username"])
    return jsonify({"ok": True})


@app.get("/api/token")
@admin_required
def api_token_lesen():
    """Das Token fuer die Home-Assistant-Schnittstelle - nur fuer Verwalter."""
    return jsonify({"token": API_TOKEN,
                    "aus_option": bool(_opt("API_TOKEN"))})


@app.post("/api/token/neu")
@admin_required
def api_token_neu():
    """Ein frisches Token erzeugen - das alte gilt sofort nicht mehr.

    Noetig, wenn das alte irgendwo aufgetaucht ist, wo es nicht hingehoert:
    in einem Protokollauszug, einem Bildschirmfoto, einer Nachricht. Steht
    das Token in der Add-on-Option, gehoert es dorthin und wird hier nicht
    angeruehrt.
    """
    global API_TOKEN
    if _opt("API_TOKEN"):
        return jsonify({"error": "Das Token steht in der Add-on-Option."
                                 " Ändere es dort und starte das Add-on neu."}), 400
    neu = secrets.token_urlsafe(32)
    with open(TOKEN_PATH, "w") as fh:
        fh.write(neu)
    os.chmod(TOKEN_PATH, 0o600)
    API_TOKEN = neu
    log.warning("Token fuer die Home-Assistant-Schnittstelle neu erzeugt von"
                " Nutzer %s - alte Automationen schlagen ab jetzt fehl",
                session["uid"])
    return jsonify({"ok": True, "token": neu})


@app.post("/api/users/<int:user_id>/approve")
@admin_required
def api_approve_user(user_id):
    """Einen Zugangsantrag freigeben - das Konto wird damit nutzbar."""
    row, err = target_user(user_id)
    if err:
        return err
    if not row["pending"]:
        return jsonify({"error": "Dieses Konto wartet nicht auf Freigabe."}), 400
    db().execute("UPDATE users SET pending=0, active=1 WHERE id=?", (user_id,))
    db().commit()
    row = db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    log.info("Zugang fuer '%s' freigegeben", row["username"])
    socketio.emit("user_changed", user_payload(row))
    return jsonify(user_payload(row))


@app.patch("/api/users/<int:user_id>")
@admin_required
def api_update_user(user_id):
    """Anzeigename, Administratorrecht und Sperre aendern."""
    row, err = target_user(user_id)
    if err:
        return err
    me = current_user()
    data = request.get_json(force=True)
    sets, args = [], []

    if "display_name" in data:
        display = (data.get("display_name") or "").strip()
        if not display:
            return jsonify({"error": "Der Anzeigename darf nicht leer sein."}), 400
        sets.append("display_name=?")
        args.append(display)

    if "is_admin" in data:
        want = 1 if data.get("is_admin") else 0
        if not want and row["is_admin"] and not other_admins(user_id):
            return jsonify({"error": "Das ist der letzte Administrator - "
                                     "erst einen zweiten ernennen."}), 400
        if not want and row["id"] == me["id"]:
            return jsonify({"error": "Die eigenen Administratorrechte kannst du "
                                     "nicht abgeben."}), 400
        sets.append("is_admin=?")
        args.append(want)

    if "active" in data:
        want = 1 if data.get("active") else 0
        if not want and row["id"] == me["id"]:
            return jsonify({"error": "Du kannst dich nicht selbst sperren."}), 400
        if not want and row["is_admin"] and not other_admins(user_id):
            return jsonify({"error": "Das ist der letzte Administrator - "
                                     "erst einen zweiten ernennen."}), 400
        sets.append("active=?")
        args.append(want)

    if not sets:
        return jsonify({"error": "Es wurde nichts zum Aendern angegeben."}), 400
    args.append(user_id)
    db().execute(f"UPDATE users SET {','.join(sets)} WHERE id=?", args)
    db().commit()

    row = db().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row["active"]:
        disconnect_user(user_id)
    socketio.emit("user_changed", user_payload(row))
    return jsonify(user_payload(row))


@app.delete("/api/users/<int:user_id>")
@admin_required
def api_delete_user(user_id):
    """Konto endgueltig entfernen.

    Die Nachrichten bleiben im Verlauf stehen - sie wandern auf ein
    Archiv-Konto, sonst rissen sie Loecher in fremde Unterhaltungen.
    """
    row, err = target_user(user_id)
    if err:
        return err
    me = current_user()
    if row["id"] == me["id"]:
        return jsonify({"error": "Das eigene Konto kannst du nicht loeschen."}), 400
    if row["is_admin"] and not other_admins(user_id):
        return jsonify({"error": "Das ist der letzte Administrator - "
                                 "erst einen zweiten ernennen."}), 400

    conn = db()
    gone = conn.execute("SELECT id FROM users WHERE username=?",
                        (GONE_USERNAME,)).fetchone()
    if gone is None:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, pw_hash, is_admin, active,"
            " created_at) VALUES (?,?,'!',0,0,?)",
            (GONE_USERNAME, "Geloeschtes Konto", int(time.time())))
        gone_id = cur.lastrowid
    else:
        gone_id = gone["id"]

    conn.execute("UPDATE messages SET user_id=? WHERE user_id=?", (gone_id, user_id))
    conn.execute("UPDATE files SET user_id=? WHERE user_id=?", (gone_id, user_id))
    conn.execute("DELETE FROM room_members WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM push_subs WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM live_orte WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM stimmung_mit WHERE user_id=? OR stimmung_id IN"
                 " (SELECT id FROM stimmungen WHERE user_id=?)",
                 (user_id, user_id))
    conn.execute("DELETE FROM stimmungen WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM event_antworten WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM freundschaften WHERE klein_id=? OR gross_id=?",
                 (user_id, user_id))
    conn.execute("DELETE FROM tipp_marken WHERE user_id=? OR tipp_id IN"
                 " (SELECT id FROM tipps WHERE user_id=?)", (user_id, user_id))
    conn.execute("DELETE FROM tipps WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()

    disconnect_user(user_id)
    socketio.emit("user_removed", {"id": user_id})
    log.info("Konto '%s' wurde geloescht", row["username"])
    return jsonify({"ok": True})


@app.post("/api/me/password")
@login_required
def api_change_password():
    data = request.get_json(force=True)
    new = data.get("new") or ""
    me = current_user()
    if not check_password_hash(me["pw_hash"], data.get("old") or ""):
        return jsonify({"error": "Das aktuelle Passwort stimmt nicht."}), 400
    if len(new) < MIN_PASSWORD:
        return jsonify({"error": f"Das neue Passwort braucht mindestens "
                                 f"{MIN_PASSWORD} Zeichen."}), 400
    db().execute("UPDATE users SET pw_hash=?, pw_version=pw_version+1 WHERE id=?",
                 (generate_password_hash(new), me["id"]))
    db().commit()
    # Die eigene Sitzung soll weiterlaufen, andere Geraete fliegen raus.
    session["pwv"] = me["pw_version"] + 1
    return jsonify({"ok": True})


@app.post("/api/me/karten")
@login_required
def api_set_karten():
    """Strassenkarte an oder aus.

    Ist sie aus, bleibt es bei den Umrissen aus dem Add-on und es geht keine
    einzige Anfrage nach draussen. Die Einstellung haengt am Konto, nicht am
    Geraet - eine Entscheidung ueber die eigenen Daten soll nicht davon
    abhaengen, mit welchem Telefon man sich gerade anmeldet.
    """
    an = 1 if request.get_json(force=True).get("kacheln") else 0
    conn = db()
    conn.execute("UPDATE users SET karten_kacheln=? WHERE id=?",
                 (an, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "kacheln": bool(an)})


@app.post("/api/upload")
@login_required
def api_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Keine Datei ausgewaehlt."}), 400
    stored = secrets.token_hex(16)
    path = os.path.join(UPLOAD_DIR, stored)
    file.save(path)
    size = os.path.getsize(path)
    mime = safe_mime(file.mimetype)
    cur = db().execute(
        "INSERT INTO files (stored_name, orig_name, mime, size, user_id, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (stored, secure_filename(file.filename), mime, size,
         session["uid"], int(time.time())))
    db().commit()
    return jsonify({"id": cur.lastrowid, "name": file.filename,
                    "mime": mime, "size": size})


@app.get("/files/<int:file_id>")
@login_required
def api_file(file_id):
    row = db().execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        abort(404)
    ok = db().execute(
        "SELECT 1 FROM messages m JOIN room_members rm ON rm.room_id=m.room_id"
        " WHERE m.file_id=? AND rm.user_id=?", (file_id, session["uid"])).fetchone()
    if not ok:
        # Das Bild einer Einladung haengt am Termin, nicht an einer Nachricht
        ok = db().execute(
            "SELECT 1 FROM events e JOIN room_members rm ON rm.room_id=e.room_id"
            " WHERE e.file_id=? AND rm.user_id=?",
            (file_id, session["uid"])).fetchone()
    if not ok:
        # Und das Bild eines Tipps am Tipp - sichtbar fuer den Kreis
        tipp = db().execute("SELECT user_id FROM tipps WHERE file_id=?",
                            (file_id,)).fetchone()
        if tipp and tipp["user_id"] in mein_kreis(session["uid"]) | {session["uid"]}:
            ok = True
    if not ok:
        # Und was jemand fuer die Galerie freigegeben hat, sehen die, fuer die
        # es freigegeben ist - auch ohne gemeinsame Unterhaltung.
        eintrag = db().execute("SELECT * FROM galerie WHERE file_id=?",
                               (file_id,)).fetchone()
        if eintrag and galerie_sichtbar(eintrag, session["uid"]):
            ok = True
    if not ok and row["user_id"] != session["uid"]:
        abort(403)
    # safe_mime auch beim Ausliefern: Dateien aus aelteren Installationen
    # tragen noch den vom Client gesetzten Typ in der Datenbank.
    mime = safe_mime(row["mime"])
    inline = mime in INLINE_MIMES and request.args.get("dl") != "1"
    resp = send_file(os.path.join(UPLOAD_DIR, row["stored_name"]),
                     mimetype=mime,
                     download_name=row["orig_name"],
                     as_attachment=not inline)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; img-src 'self'; media-src 'self'")
    return resp


# --------------------------------------------------------------------------
# Profilbilder
# --------------------------------------------------------------------------
# Die Oberflaeche verkleinert Bilder vor dem Hochladen auf 256 Pixel. Was
# hier ankommt, ist also klein - die Grenze faengt nur ab, wenn jemand am
# Browser vorbei etwas Grosses schickt.
MAX_AVATAR_BYTES = 512 * 1024


def avatar_speichern(datei):
    """Bild pruefen und ablegen. Gibt den Dateinamen zurueck."""
    mime = safe_mime(datei.mimetype)
    if mime not in IMAGE_MIMES:
        return None, "Als Profilbild geht nur ein Bild (PNG, JPEG, GIF oder WebP)."
    name = secrets.token_hex(16)
    pfad = os.path.join(AVATAR_DIR, name)
    datei.save(pfad)
    if os.path.getsize(pfad) > MAX_AVATAR_BYTES:
        os.remove(pfad)
        return None, "Das Bild ist zu gross."
    return name, None


def avatar_entfernen(name):
    if not name:
        return
    try:
        os.remove(os.path.join(AVATAR_DIR, name))
    except FileNotFoundError:
        pass
    except OSError as exc:  # noqa: BLE001
        log.warning("Profilbild %s liess sich nicht entfernen: %s", name, exc)


@app.get("/avatars/<kind>/<int:ziel_id>")
@login_required
def api_avatar(kind, ziel_id):
    if kind == "u":
        row = db().execute("SELECT avatar FROM users WHERE id=?", (ziel_id,)).fetchone()
    elif kind == "r":
        # Raumbilder sehen nur Mitglieder
        if not is_member(ziel_id, session["uid"]):
            abort(403)
        row = db().execute("SELECT avatar FROM rooms WHERE id=?", (ziel_id,)).fetchone()
    else:
        abort(404)
    if row is None or not row["avatar"]:
        abort(404)
    pfad = os.path.join(AVATAR_DIR, row["avatar"])
    if not os.path.exists(pfad):
        abort(404)
    resp = send_file(pfad, mimetype="image/*")
    # Der Name wechselt bei jedem neuen Bild, die Adresse darf also lange gelten
    resp.headers["Cache-Control"] = "private, max-age=604800"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'"
    return resp


@app.post("/api/me/avatar")
@login_required
def api_set_my_avatar():
    datei = request.files.get("file")
    if not datei or not datei.filename:
        return jsonify({"error": "Kein Bild ausgewaehlt."}), 400
    name, fehler = avatar_speichern(datei)
    if fehler:
        return jsonify({"error": fehler}), 400
    me = current_user()
    alt = me["avatar"]
    db().execute("UPDATE users SET avatar=? WHERE id=?", (name, me["id"]))
    db().commit()
    avatar_entfernen(alt)
    socketio.emit("avatar_changed", {"kind": "u", "id": me["id"], "avatar": name})
    return jsonify({"avatar": name})


@app.delete("/api/me/avatar")
@login_required
def api_clear_my_avatar():
    me = current_user()
    db().execute("UPDATE users SET avatar=NULL WHERE id=?", (me["id"],))
    db().commit()
    avatar_entfernen(me["avatar"])
    socketio.emit("avatar_changed", {"kind": "u", "id": me["id"], "avatar": None})
    return jsonify({"ok": True})


@app.post("/api/rooms/<int:room_id>/avatar")
@login_required
def api_set_room_avatar(room_id):
    """Gruppenbild - jedes Mitglied der Gruppe darf es setzen."""
    room = db().execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if room is None or not is_member(room_id, session["uid"]):
        abort(403)
    if not room["is_group"]:
        return jsonify({"error": "Ein Direktchat zeigt das Bild der Person."}), 400
    datei = request.files.get("file")
    if not datei or not datei.filename:
        return jsonify({"error": "Kein Bild ausgewaehlt."}), 400
    name, fehler = avatar_speichern(datei)
    if fehler:
        return jsonify({"error": fehler}), 400
    db().execute("UPDATE rooms SET avatar=? WHERE id=?", (name, room_id))
    db().commit()
    avatar_entfernen(room["avatar"])
    socketio.emit("avatar_changed", {"kind": "r", "id": room_id, "avatar": name},
                  to=f"room:{room_id}")
    return jsonify({"avatar": name})


@app.post("/api/rooms/<int:room_id>/poll")
@login_required
def api_create_poll(room_id):
    """Abstimmung anlegen - sie erscheint als Nachricht in der Unterhaltung."""
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    data = request.get_json(force=True)
    frage = (data.get("frage") or "").strip()
    roh = data.get("optionen") or []
    optionen = []
    for o in roh:
        text = (str(o) or "").strip()
        if text and text not in optionen:
            optionen.append(text[:120])
    if not frage:
        return jsonify({"error": "Die Frage fehlt."}), 400
    if len(optionen) < 2:
        return jsonify({"error": "Es braucht mindestens zwei Antworten."}), 400
    if len(optionen) > 12:
        return jsonify({"error": "Mehr als zwoelf Antworten sind zu viel."}), 400

    conn = db()
    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO polls (room_id, user_id, frage, mehrfach, created_at)"
        " VALUES (?,?,?,?,?)",
        (room_id, uid, frage[:300], 1 if data.get("mehrfach") else 0, now))
    poll_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO poll_options (poll_id, text, platz) VALUES (?,?,?)",
        [(poll_id, text, i) for i, text in enumerate(optionen)])
    cur = conn.execute(
        "INSERT INTO messages (room_id, user_id, body, poll_id, created_at)"
        " VALUES (?,?,'',?,?)", (room_id, uid, poll_id, now))
    msg_id = cur.lastrowid
    conn.execute("UPDATE room_members SET last_read=? WHERE room_id=? AND user_id=?",
                 (msg_id, room_id, uid))
    conn.commit()

    row = conn.execute(MSG_QUERY + " WHERE m.id=?", (msg_id,)).fetchone()
    socketio.emit("message", msg_payload(row), to=f"room:{room_id}")
    mitglieder = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=?", (room_id,)).fetchall()]
    with ONLINE_LOCK:
        abwesend = [m for m in mitglieder if m != uid and m not in ONLINE]
    ziel = f"{EXTERNAL_URL}/?room={room_id}" if EXTERNAL_URL else f"?room={room_id}"
    push_to_users(abwesend, "Neue Abstimmung", frage[:180], ziel)
    return jsonify({"ok": True, "poll_id": poll_id, "message_id": msg_id})


@app.post("/api/polls/<int:poll_id>/vote")
@login_required
def api_vote(poll_id):
    """Stimme abgeben oder zuruecknehmen."""
    uid = session["uid"]
    conn = db()
    poll = conn.execute("SELECT * FROM polls WHERE id=?", (poll_id,)).fetchone()
    if poll is None or not is_member(poll["room_id"], uid):
        abort(403)
    try:
        option_id = int(request.get_json(force=True).get("option_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Es wurde keine Antwort ausgewaehlt."}), 400
    gehoert = conn.execute(
        "SELECT 1 FROM poll_options WHERE id=? AND poll_id=?",
        (option_id, poll_id)).fetchone()
    if not gehoert:
        return jsonify({"error": "Diese Antwort gehoert nicht zur Frage."}), 400

    hatte = conn.execute(
        "SELECT 1 FROM poll_votes WHERE poll_id=? AND option_id=? AND user_id=?",
        (poll_id, option_id, uid)).fetchone()
    if hatte:
        # Noch einmal tippen nimmt die Stimme zurueck
        conn.execute("DELETE FROM poll_votes WHERE poll_id=? AND option_id=?"
                     " AND user_id=?", (poll_id, option_id, uid))
    else:
        if not poll["mehrfach"]:
            conn.execute("DELETE FROM poll_votes WHERE poll_id=? AND user_id=?",
                         (poll_id, uid))
        conn.execute(
            "INSERT INTO poll_votes (poll_id, option_id, user_id, created_at)"
            " VALUES (?,?,?,?)", (poll_id, option_id, uid, int(time.time())))
    conn.commit()
    # Jeder sieht seine eigene Wahl markiert, deshalb nur ein Anstoss zum
    # Nachladen statt der fertigen Auswertung.
    socketio.emit("poll_changed", {"poll_id": poll_id, "room_id": poll["room_id"]},
                  to=f"room:{poll['room_id']}")
    return jsonify(poll_payload(poll_id, uid, conn))


@app.get("/api/polls/<int:poll_id>")
@login_required
def api_get_poll(poll_id):
    uid = session["uid"]
    poll = db().execute("SELECT room_id FROM polls WHERE id=?",
                        (poll_id,)).fetchone()
    if poll is None or not is_member(poll["room_id"], uid):
        abort(403)
    return jsonify(poll_payload(poll_id, uid))


# --------------------------------------------------------------------------
# Hintergrundmuster
# --------------------------------------------------------------------------
# Kein hochgeladenes Bild, sondern ein Muster aus einer festen Liste. Es wird
# in der Oberflaeche gezeichnet, liegt also weder als Datei auf dem Pi noch
# lenkt es vom Text ab - so wie bei WhatsApp.
@app.post("/api/rooms/<int:room_id>/hintergrund")
@login_required
def api_set_hintergrund(room_id):
    """Muster waehlen - gilt nur fuer den, der es setzt."""
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    muster = (request.get_json(force=True).get("muster") or "").strip().lower()
    if muster and muster not in MUSTER:
        return jsonify({"error": "Dieses Muster gibt es nicht."}), 400
    conn = db()
    conn.execute("UPDATE room_members SET hintergrund=? WHERE room_id=? AND user_id=?",
                 (muster or None, room_id, uid))
    conn.commit()
    return jsonify({"ok": True, "hintergrund": muster or None})


# --------------------------------------------------------------------------
# Empfehlungen
# --------------------------------------------------------------------------
# Was war gut? Jeder schreibt seine eigene Empfehlung; es gibt bewusst keine
# gemeinsame Bewertung, die sich mitteln liesse. Ein Tipp von jemandem, den
# man kennt, ist mehr wert als ein Durchschnitt aus tausend Sternen.
TIPP_ARTEN = {
    "film": "🎬 Film",
    "kino": "🍿 Kino",
    "restaurant": "🍽 Restaurant",
    "bar": "🍺 Bar",
    "cafe": "☕ Café",
    "hotel": "🛏 Hotel",
    "ausflug": "🥾 Ausflug",
    "musik": "🎵 Musik",
    "buch": "📖 Buch",
    "sonstiges": "✨ Sonstiges",
}


def tipp_payload(row, uid, conn=None):
    conn = conn or db()
    marken = conn.execute(
        "SELECT m.user_id, u.display_name, u.avatar FROM tipp_marken m"
        " JOIN users u ON u.id=m.user_id WHERE m.tipp_id=?",
        (row["id"],)).fetchall()
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["display_name"],
        "avatar": row["avatar"],
        "art": row["art"],
        "titel": row["titel"],
        "ort_text": row["ort_text"] or "",
        "ort": ({"lat": row["lat"], "lon": row["lon"]}
                if row["lat"] is not None and row["lon"] is not None else None),
        "sterne": row["sterne"],
        "text": row["text"] or "",
        "file_id": row["file_id"],
        "created_at": row["created_at"],
        "meiner": row["user_id"] == uid,
        "gemerkt": [{"id": m["user_id"], "name": m["display_name"],
                     "avatar": m["avatar"]} for m in marken],
        "ich_merke": any(m["user_id"] == uid for m in marken),
    }


TIPP_QUERY = ("SELECT t.*, u.display_name, u.avatar FROM tipps t"
              " JOIN users u ON u.id=t.user_id")


@app.get("/api/tipps")
@login_required
def api_tipps():
    """Empfehlungen aus meinem Kreis - meine eigenen immer dabei."""
    uid = session["uid"]
    conn = db()
    erlaubt = mein_kreis(uid, conn) | {uid}
    art = (request.args.get("art") or "").strip().lower()
    rows = conn.execute(TIPP_QUERY + " ORDER BY t.created_at DESC LIMIT 300"
                        ).fetchall()
    raus = [tipp_payload(r, uid, conn) for r in rows
            if r["user_id"] in erlaubt
            and (not art or art == r["art"])]
    return jsonify({"tipps": raus, "arten": TIPP_ARTEN})


@app.post("/api/tipps")
@login_required
def api_tipp_anlegen():
    uid = session["uid"]
    data = request.get_json(force=True)
    titel = (data.get("titel") or "").strip()
    if not titel:
        return jsonify({"error": "Es fehlt der Name."}), 400
    art = (data.get("art") or "").strip().lower()
    if art not in TIPP_ARTEN:
        art = "sonstiges"
    try:
        sterne = int(data.get("sterne") or 0)
    except (TypeError, ValueError):
        sterne = 0
    sterne = max(1, min(5, sterne)) if sterne else 0
    if not sterne:
        return jsonify({"error": "Wie viele Sterne gibst du?"}), 400
    punkt = _koordinaten(data) if data.get("lat") is not None else None

    conn = db()
    file_id = data.get("file_id")
    if file_id is not None:
        try:
            file_id = int(file_id)
        except (TypeError, ValueError):
            file_id = None
        if file_id is not None and not conn.execute(
                "SELECT 1 FROM files WHERE id=? AND user_id=?",
                (file_id, uid)).fetchone():
            file_id = None

    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO tipps (user_id, art, titel, ort_text, lat, lon, sterne,"
        " text, file_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (uid, art, titel[:200], (data.get("ort_text") or "").strip()[:200],
         punkt[0] if punkt else None, punkt[1] if punkt else None,
         sterne, (data.get("text") or "").strip()[:2000], file_id, now))
    conn.commit()
    for ziel in mein_kreis(uid, conn):
        socketio.emit("tipps_geaendert", {}, to=f"user:{ziel}")
    row = conn.execute(TIPP_QUERY + " WHERE t.id=?", (cur.lastrowid,)).fetchone()
    log.info("Nutzer %s hat einen Tipp angelegt (%s)", uid, art)
    return jsonify(tipp_payload(row, uid, conn))


@app.patch("/api/tipps/<int:tipp_id>")
@login_required
def api_tipp_aendern(tipp_id):
    """Nur der eigene Tipp - fremde Empfehlungen gehoeren nicht mir."""
    uid = session["uid"]
    conn = db()
    row = conn.execute("SELECT * FROM tipps WHERE id=?", (tipp_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Den gibt es nicht."}), 404
    if row["user_id"] != uid:
        return jsonify({"error": "Das ist nicht dein Tipp."}), 403

    data = request.get_json(force=True)
    felder, werte = [], []
    if "titel" in data:
        titel = (data.get("titel") or "").strip()
        if not titel:
            return jsonify({"error": "Es fehlt der Name."}), 400
        felder.append("titel=?")
        werte.append(titel[:200])
    if "art" in data:
        art = (data.get("art") or "").strip().lower()
        felder.append("art=?")
        werte.append(art if art in TIPP_ARTEN else "sonstiges")
    if "sterne" in data:
        try:
            sterne = max(1, min(5, int(data.get("sterne"))))
        except (TypeError, ValueError):
            return jsonify({"error": "Die Bewertung ist unbrauchbar."}), 400
        felder.append("sterne=?")
        werte.append(sterne)
    for name, grenze in (("ort_text", 200), ("text", 2000)):
        if name in data:
            felder.append(f"{name}=?")
            werte.append((data.get(name) or "").strip()[:grenze])
    if "lat" in data or "lon" in data:
        if data.get("lat") is None or data.get("lon") is None:
            felder += ["lat=?", "lon=?"]
            werte += [None, None]
        else:
            punkt = _koordinaten(data)
            if punkt is None:
                return jsonify({"error": "Der Ort ist unbrauchbar."}), 400
            felder += ["lat=?", "lon=?"]
            werte += [punkt[0], punkt[1]]
    altes_bild = None
    if "file_id" in data:
        roh = data.get("file_id")
        neu_id = None
        if roh is not None:
            try:
                neu_id = int(roh)
            except (TypeError, ValueError):
                neu_id = None
            if neu_id is not None and not conn.execute(
                    "SELECT 1 FROM files WHERE id=? AND user_id=?",
                    (neu_id, uid)).fetchone():
                neu_id = None
        if neu_id != row["file_id"]:
            altes_bild = row["file_id"]
        felder.append("file_id=?")
        werte.append(neu_id)

    if felder:
        werte.append(tipp_id)
        conn.execute(f"UPDATE tipps SET {', '.join(felder)} WHERE id=?", werte)
        conn.commit()
        if altes_bild:
            datei_aufraeumen(conn, altes_bild)
        for ziel in mein_kreis(uid, conn):
            socketio.emit("tipps_geaendert", {}, to=f"user:{ziel}")
    row = conn.execute(TIPP_QUERY + " WHERE t.id=?", (tipp_id,)).fetchone()
    return jsonify(tipp_payload(row, uid, conn))


@app.post("/api/tipps/<int:tipp_id>/merken")
@login_required
def api_tipp_merken(tipp_id):
    """Will ich auch - noch einmal tippen nimmt es zurueck."""
    uid = session["uid"]
    conn = db()
    row = conn.execute(TIPP_QUERY + " WHERE t.id=?", (tipp_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Den gibt es nicht."}), 404
    if row["user_id"] != uid and row["user_id"] not in mein_kreis(uid, conn):
        abort(403)
    hatte = conn.execute("SELECT 1 FROM tipp_marken WHERE tipp_id=? AND user_id=?",
                         (tipp_id, uid)).fetchone()
    if hatte:
        conn.execute("DELETE FROM tipp_marken WHERE tipp_id=? AND user_id=?",
                     (tipp_id, uid))
    else:
        conn.execute("INSERT INTO tipp_marken (tipp_id, user_id, created_at)"
                     " VALUES (?,?,?)", (tipp_id, uid, int(time.time())))
    conn.commit()
    socketio.emit("tipps_geaendert", {}, to=f"user:{row['user_id']}")
    return jsonify(tipp_payload(row, uid, conn))


@app.delete("/api/tipps/<int:tipp_id>")
@login_required
def api_tipp_loeschen(tipp_id):
    uid = session["uid"]
    conn = db()
    row = conn.execute("SELECT user_id, file_id FROM tipps WHERE id=?",
                       (tipp_id,)).fetchone()
    if row is None:
        return jsonify({"ok": True})
    if row["user_id"] != uid and not current_user()["is_admin"]:
        return jsonify({"error": "Das ist nicht dein Tipp."}), 403
    conn.execute("DELETE FROM tipp_marken WHERE tipp_id=?", (tipp_id,))
    conn.execute("DELETE FROM tipps WHERE id=?", (tipp_id,))
    conn.commit()
    if row["file_id"]:
        datei_aufraeumen(conn, row["file_id"])
    for ziel in mein_kreis(uid, conn):
        socketio.emit("tipps_geaendert", {}, to=f"user:{ziel}")
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Altes automatisch loeschen
# --------------------------------------------------------------------------
# Ein Familienserver sammelt ueber Jahre Gigabyte an Bildern. Wer will, laesst
# alles aelter als X Tage verschwinden. Voreingestellt ist 0, also nie - ein
# Messenger, der ungefragt Erinnerungen wegwirft, waere eine Zumutung.
AUFRAEUM_STUNDEN = 6


def alt_aufraeumen(tage=None):
    """Nachrichten und Anhaenge aelter als X Tage entfernen.

    Gibt zurueck, wie viel weg ist. Termine, Empfehlungen und Konten bleiben
    unberuehrt - hier geht es nur um den Verlauf.
    """
    tage = AUFBEWAHRUNG_TAGE if tage is None else tage
    if not tage or tage <= 0:
        return {"nachrichten": 0, "dateien": 0}
    grenze = int(time.time()) - tage * 86400
    conn = raw_db()
    try:
        dateien = [r["file_id"] for r in conn.execute(
            "SELECT DISTINCT file_id FROM messages"
            " WHERE created_at<? AND file_id IS NOT NULL", (grenze,)).fetchall()]
        weg = conn.execute("SELECT COUNT(*) c FROM messages WHERE created_at<?",
                           (grenze,)).fetchone()["c"]
        if not weg:
            return {"nachrichten": 0, "dateien": 0}
        conn.execute("DELETE FROM messages WHERE created_at<?", (grenze,))
        conn.commit()
        # Erst nach dem Loeschen der Nachrichten: datei_aufraeumen prueft, ob
        # noch etwas an der Datei haengt, und laesst sie sonst in Ruhe.
        entfernt = sum(1 for f in dateien if datei_aufraeumen(conn, f))
        log.info("Aufraeumen: %s Nachrichten und %s Dateien aelter als %s Tage"
                 " entfernt", weg, entfernt, tage)
        return {"nachrichten": weg, "dateien": entfernt}
    finally:
        conn.close()


def aufraeum_schleife():
    """Alle paar Stunden nachsehen. Ohne eingestellte Frist passiert nichts."""
    while True:
        time.sleep(AUFRAEUM_STUNDEN * 3600)
        try:
            if AUFBEWAHRUNG_TAGE > 0:
                alt_aufraeumen()
        except Exception as exc:  # noqa: BLE001
            log.warning("Aufraeumen fehlgeschlagen: %s", exc)


@app.get("/api/aufbewahrung")
@login_required
def api_aufbewahrung():
    """Wie lange Nachrichten bleiben - und was ein Lauf jetzt entfernen wuerde."""
    conn = db()
    grenze = int(time.time()) - AUFBEWAHRUNG_TAGE * 86400
    faellig = 0
    if AUFBEWAHRUNG_TAGE > 0:
        faellig = conn.execute("SELECT COUNT(*) c FROM messages WHERE created_at<?",
                               (grenze,)).fetchone()["c"]
    return jsonify({"tage": AUFBEWAHRUNG_TAGE, "faellig": faellig})


@app.post("/api/aufbewahrung/jetzt")
@login_required
@admin_required
def api_aufbewahrung_jetzt():
    """Von Hand aufraeumen - damit man nicht Stunden warten muss."""
    if AUFBEWAHRUNG_TAGE <= 0:
        return jsonify({"error": "Es ist keine Frist eingestellt."}), 400
    ergebnis = alt_aufraeumen()
    socketio.emit("room_changed", {"id": 0})
    return jsonify(ergebnis)


# --------------------------------------------------------------------------
# Was ist neu?
# --------------------------------------------------------------------------
# Die Zahlen an den Reitern sollen zeigen, was seit dem letzten Blick
# dazugekommen ist - nicht, wie viel es insgesamt gibt. Eine "12" an den
# Tipps, die sich nie aendert, sagt naemlich gar nichts.
BEREICHE = ("karten", "stimmung", "termine", "tipps")

# Sprechblasenfarben: eine feste Liste. Freie Farbwahl fuehrt schnell zu
# Toenen, auf denen die eigene Schrift nicht mehr zu lesen ist.
BLASENFARBEN = ("#1f4a48", "#3b4a6b", "#4a3b5c", "#5c4030", "#2f5136",
                "#5c3040", "#334a5c", "#4a4a2f")


def gesehen_lesen(me):
    return {b: (me[f"gesehen_{b}"] or 0) for b in BEREICHE}


@app.post("/api/gesehen/<bereich>")
@login_required
def api_gesehen(bereich):
    """Merkt sich, dass ich in diesen Abschnitt geschaut habe."""
    if bereich not in BEREICHE:
        return jsonify({"error": "Diesen Abschnitt gibt es nicht."}), 404
    jetzt = int(time.time())
    conn = db()
    conn.execute(f"UPDATE users SET gesehen_{bereich}=? WHERE id=?",
                 (jetzt, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "bereich": bereich, "seit": jetzt})


@app.post("/api/me/blasenfarbe")
@login_required
def api_set_blasenfarbe():
    """Die Farbe der eigenen Sprechblasen - in allen Unterhaltungen."""
    farbe = (request.get_json(force=True).get("farbe") or "").strip().lower()
    if farbe and farbe not in BLASENFARBEN:
        return jsonify({"error": "Diese Farbe gibt es nicht."}), 400
    conn = db()
    conn.execute("UPDATE users SET blasenfarbe=? WHERE id=?",
                 (farbe or None, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "farbe": farbe or None})


@app.get("/api/blasenfarben")
@login_required
def api_blasenfarben():
    return jsonify(list(BLASENFARBEN))


# Womit "In Karten oeffnen" aufmachen soll. "geraet" schickt einen geo:-Verweis
# los und laesst das Telefon entscheiden - unter Android fragt es dann selbst,
# welche App es sein soll. Wo das nicht geht, faellt die Oberflaeche auf eine
# Netzkarte zurueck; welche, steht hier.
KARTEN_APPS = ("geraet", "google", "apple", "osm")


@app.post("/api/me/karten-app")
@login_required
def api_set_karten_app():
    """Welche Kartenanwendung ein Ort oeffnen soll."""
    wahl = (request.get_json(force=True).get("app") or "").strip().lower()
    if wahl not in KARTEN_APPS:
        return jsonify({"error": "Diese Auswahl gibt es nicht."}), 400
    conn = db()
    conn.execute("UPDATE users SET karten_app=? WHERE id=?",
                 (wahl, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "app": wahl})


@app.get("/api/karten-apps")
@login_required
def api_karten_apps():
    return jsonify(list(KARTEN_APPS))


# Der Klingelton wird im Browser erzeugt, nicht als Datei mitgeliefert - hier
# steht nur, welches Muster gemeint ist. So bleibt das Add-on klein und es
# gibt nichts nachzuladen.
KLINGELTOENE = ("klassisch", "sanft", "perlen", "tief", "folge")


@app.post("/api/me/klingelton")
@login_required
def api_set_klingelton():
    """Womit es klingeln soll, wenn jemand anruft."""
    wahl = (request.get_json(force=True).get("ton") or "").strip().lower()
    if wahl not in KLINGELTOENE:
        return jsonify({"error": "Diesen Klingelton gibt es nicht."}), 400
    conn = db()
    conn.execute("UPDATE users SET klingelton=? WHERE id=?", (wahl, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "ton": wahl})


@app.get("/api/klingeltoene")
@login_required
def api_klingeltoene():
    return jsonify(list(KLINGELTOENE))


@app.get("/api/anzeigename")
@login_required
def api_anzeigename_lesen():
    return jsonify({"name": anzeigename(), "standard": ANZEIGENAME_STANDARD})


@app.post("/api/anzeigename")
@login_required
@admin_required
def api_anzeigename_setzen():
    """Wie die Oberflaeche heissen soll - fuer alle zugleich.

    Leer heisst: zurueck zur Voreinstellung. Das Add-on im Store bleibt davon
    unberuehrt, dessen Name steht in config.yaml.
    """
    roh = (request.get_json(force=True).get("name") or "").strip()
    if len(roh) > ANZEIGENAME_MAX:
        return jsonify({"error": f"Höchstens {ANZEIGENAME_MAX} Zeichen."}), 400
    einstellung_setzen("anzeigename", roh)
    neu = anzeigename()
    log.info("Anzeigename auf %r gesetzt von Nutzer %s", neu, session["uid"])
    # Alle offenen Fenster ziehen nach, ohne dass jemand neu laden muss
    socketio.emit("name_geaendert", {"name": neu})
    return jsonify({"ok": True, "name": neu})


# --------------------------------------------------------------------------
# Toene und Stummschaltung
# --------------------------------------------------------------------------
# Die Einstellung haengt am Konto, nicht am Geraet: wer eine Gruppe
# stummschaltet, will das ueberall - nicht nur auf dem Telefon, mit dem er
# gerade zufaellig angemeldet ist.
TON_STUFEN = ("alle", "nur_anrufe", "aus")


@app.get("/api/toene")
@login_required
def api_toene():
    """Die allgemeine Einstellung und alles, was davon abweicht."""
    uid = session["uid"]
    conn = db()
    me = conn.execute("SELECT ton_stufe FROM users WHERE id=?", (uid,)).fetchone()
    stumm = conn.execute(
        "SELECT room_id, stumm_bis FROM room_members"
        " WHERE user_id=? AND stumm_bis IS NOT NULL", (uid,)).fetchall()
    jetzt = int(time.time())
    return jsonify({
        "stufe": (me["ton_stufe"] if me and me["ton_stufe"] else "alle"),
        "stumm": {str(r["room_id"]): r["stumm_bis"] for r in stumm
                  if r["stumm_bis"] == 0 or r["stumm_bis"] > jetzt},
    })


@app.post("/api/toene")
@login_required
def api_set_toene():
    """Wie laut es allgemein sein soll."""
    stufe = (request.get_json(force=True).get("stufe") or "").strip().lower()
    if stufe not in TON_STUFEN:
        return jsonify({"error": "Diese Einstellung gibt es nicht."}), 400
    conn = db()
    conn.execute("UPDATE users SET ton_stufe=? WHERE id=?", (stufe, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "stufe": stufe})


@app.post("/api/rooms/<int:room_id>/stumm")
@login_required
def api_stumm(room_id):
    """Eine Unterhaltung stummschalten - fuer Stunden oder auf Dauer.

    stunden=0 heisst "bis ich es wieder aufhebe"; ohne Angabe wird die
    Stummschaltung beendet.
    """
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    data = request.get_json(force=True)
    if data.get("stunden") is None:
        bis = None
    else:
        try:
            stunden = int(data.get("stunden"))
        except (TypeError, ValueError):
            return jsonify({"error": "Die Dauer ist unbrauchbar."}), 400
        # 0 steht fuer "ohne Ende" - so muss niemand eine Jahreszahl raten
        bis = 0 if stunden <= 0 else int(time.time()) + min(stunden, 8760) * 3600
    conn = db()
    conn.execute("UPDATE room_members SET stumm_bis=? WHERE room_id=? AND user_id=?",
                 (bis, room_id, uid))
    conn.commit()
    return jsonify({"ok": True, "stumm_bis": bis})


def ist_stumm(room_id, uid, conn=None):
    """Soll diese Person fuer diese Unterhaltung nichts hoeren?"""
    conn = conn or db()
    row = conn.execute(
        "SELECT stumm_bis FROM room_members WHERE room_id=? AND user_id=?",
        (room_id, uid)).fetchone()
    if row is None or row["stumm_bis"] is None:
        return False
    return row["stumm_bis"] == 0 or row["stumm_bis"] > int(time.time())


# --------------------------------------------------------------------------
# Geburtstage
# --------------------------------------------------------------------------
# Gespeichert wird das Datum, angezeigt der naechste Geburtstag. Die Angabe
# ist freiwillig - wer sie nicht machen will, taucht eben nicht auf.
def geburtstag_pruefen(roh):
    """'JJJJ-MM-TT' -> derselbe Text, oder None. Zweiter Rueckgabewert ist
    eine Meldung, wenn etwas eingegeben wurde, das nicht taugt."""
    roh = (roh or "").strip()
    if not roh:
        return None, None
    try:
        tag = datetime.date.fromisoformat(roh)
    except ValueError:
        return None, "Das Geburtsdatum ist unbrauchbar."
    heute = datetime.date.today()
    if tag > heute:
        return None, "Das Geburtsdatum liegt in der Zukunft."
    if tag.year < heute.year - 120:
        return None, "Das Geburtsdatum ist zu lange her."
    return tag.isoformat(), None


def naechster_geburtstag(datum, heute=None):
    """Wann hat jemand das naechste Mal Geburtstag - und wie alt wird er?"""
    heute = heute or datetime.date.today()
    tag = datetime.date.fromisoformat(datum)
    # Der 29. Februar wird in Jahren ohne Schalttag am 1. Maerz gefeiert
    def am(jahr):
        try:
            return datetime.date(jahr, tag.month, tag.day)
        except ValueError:
            return datetime.date(jahr, 3, 1)
    naechster = am(heute.year)
    if naechster < heute:
        naechster = am(heute.year + 1)
    return naechster, naechster.year - tag.year


@app.get("/api/geburtstage")
@login_required
def api_geburtstage():
    """Die naechsten Geburtstage aus meinem Kreis - meiner mit dabei."""
    uid = session["uid"]
    conn = db()
    # Wer die Erinnerungen abgeschaltet hat, bekommt eine leere Liste. Der
    # eigene Geburtstag bleibt dabei trotzdem gespeichert - andere sehen ihn
    # weiter, es geht nur um die eigene Anzeige.
    if not conn.execute("SELECT geburtstage_an FROM users WHERE id=?",
                        (uid,)).fetchone()["geburtstage_an"]:
        return jsonify([])
    erlaubt = mein_kreis(uid, conn) | {uid}
    marks = ",".join("?" * len(SYSTEM_USERS))
    rows = conn.execute(
        "SELECT id, display_name, avatar, geburtstag FROM users"
        f" WHERE geburtstag IS NOT NULL AND geburtstag<>''"
        f" AND username NOT IN ({marks}) AND active=1 AND pending=0",
        SYSTEM_USERS).fetchall()
    heute = datetime.date.today()
    raus = []
    for r in rows:
        if r["id"] not in erlaubt:
            continue
        try:
            wann, jahre = naechster_geburtstag(r["geburtstag"], heute)
        except ValueError:
            continue
        raus.append({
            "user_id": r["id"],
            "name": r["display_name"],
            "avatar": r["avatar"],
            "datum": r["geburtstag"],
            "naechster": wann.isoformat(),
            # Mitternacht als Zeitpunkt - die Terminliste sortiert danach
            "naechster_at": int(datetime.datetime.combine(
                wann, datetime.time(0, 0)).timestamp()),
            "wird": jahre,
            "heute": wann == heute,
            "ich": r["id"] == uid,
        })
    raus.sort(key=lambda g: g["naechster_at"])
    return jsonify(raus)


@app.post("/api/me/geburtstage-an")
@login_required
def api_set_geburtstage_an():
    """Geburtstagserinnerungen ein- oder ausschalten."""
    an = 1 if request.get_json(force=True).get("an") else 0
    conn = db()
    conn.execute("UPDATE users SET geburtstage_an=? WHERE id=?",
                 (an, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "an": bool(an)})


@app.post("/api/me/geburtstag")
@login_required
def api_set_geburtstag():
    """Eigenes Geburtsdatum setzen oder wieder loeschen."""
    datum, fehler = geburtstag_pruefen(
        request.get_json(force=True).get("geburtstag"))
    if fehler:
        return jsonify({"error": fehler}), 400
    conn = db()
    conn.execute("UPDATE users SET geburtstag=? WHERE id=?",
                 (datum, session["uid"]))
    conn.commit()
    return jsonify({"ok": True, "geburtstag": datum})


# --------------------------------------------------------------------------
# Freundschaften
# --------------------------------------------------------------------------
# Gegenseitig und in einer Zeile je Paar: die kleinere Kennung steht immer
# links. Ohne diese Regel gaebe es zwei Zeilen fuer dieselbe Freundschaft und
# jede Abfrage muesste beide Richtungen pruefen.
def _paar(a, b):
    return (a, b) if a < b else (b, a)


def freund_status(uid, anderer, conn=None):
    """'freund', 'gesendet', 'erhalten' oder '' - aus meiner Sicht."""
    conn = conn or db()
    klein, gross = _paar(uid, anderer)
    row = conn.execute(
        "SELECT bestaetigt, angefragt_von FROM freundschaften"
        " WHERE klein_id=? AND gross_id=?", (klein, gross)).fetchone()
    if row is None:
        return ""
    if row["bestaetigt"]:
        return "freund"
    return "gesendet" if row["angefragt_von"] == uid else "erhalten"


def meine_freunde(uid, conn=None):
    """Kennungen aller bestaetigten Freunde."""
    conn = conn or db()
    rows = conn.execute(
        "SELECT klein_id, gross_id FROM freundschaften"
        " WHERE bestaetigt=1 AND (klein_id=? OR gross_id=?)",
        (uid, uid)).fetchall()
    return {r["gross_id"] if r["klein_id"] == uid else r["klein_id"]
            for r in rows}


def offene_anfragen(uid, conn=None):
    """Wie viele Anfragen auf meine Antwort warten."""
    conn = conn or db()
    return conn.execute(
        "SELECT COUNT(*) c FROM freundschaften WHERE bestaetigt=0"
        " AND angefragt_von<>? AND (klein_id=? OR gross_id=?)",
        (uid, uid, uid)).fetchone()["c"]


@app.get("/api/freunde")
@login_required
def api_freunde():
    """Freunde, eingegangene und gestellte Anfragen - und wer sonst da ist."""
    uid = session["uid"]
    conn = db()
    marks = ",".join("?" * len(SYSTEM_USERS))
    alle = conn.execute(
        "SELECT id, username, display_name, avatar FROM users"
        f" WHERE username NOT IN ({marks}) AND pending=0 AND active=1"
        " AND id<>? ORDER BY display_name", (*SYSTEM_USERS, uid)).fetchall()
    freunde, eingehend, ausgehend, offen = [], [], [], []
    for u in alle:
        eintrag = dict(u)
        stand = freund_status(uid, u["id"], conn)
        if stand == "freund":
            freunde.append(eintrag)
        elif stand == "erhalten":
            eingehend.append(eintrag)
        elif stand == "gesendet":
            ausgehend.append(eintrag)
        else:
            offen.append(eintrag)
    return jsonify({"freunde": freunde, "eingehend": eingehend,
                    "ausgehend": ausgehend, "andere": offen})


@app.post("/api/freunde/<int:user_id>")
@login_required
def api_freund_anfragen(user_id):
    """Anfragen - oder eine offene Anfrage der Gegenseite annehmen."""
    uid = session["uid"]
    if user_id == uid:
        return jsonify({"error": "Mit sich selbst geht das nicht."}), 400
    conn = db()
    ziel = conn.execute(
        "SELECT username, display_name FROM users WHERE id=? AND active=1"
        " AND pending=0", (user_id,)).fetchone()
    if ziel is None or ziel["username"] in SYSTEM_USERS:
        return jsonify({"error": "Dieses Konto gibt es nicht."}), 404

    klein, gross = _paar(uid, user_id)
    row = conn.execute(
        "SELECT bestaetigt, angefragt_von FROM freundschaften"
        " WHERE klein_id=? AND gross_id=?", (klein, gross)).fetchone()
    now = int(time.time())
    if row is None:
        conn.execute(
            "INSERT INTO freundschaften (klein_id, gross_id, angefragt_von,"
            " bestaetigt, created_at) VALUES (?,?,?,0,?)",
            (klein, gross, uid, now))
        conn.commit()
        socketio.emit("freunde_geaendert", {"anfrage": True}, to=f"user:{user_id}")
        return jsonify({"ok": True, "stand": "gesendet"})
    if row["bestaetigt"]:
        return jsonify({"ok": True, "stand": "freund"})
    if row["angefragt_von"] == uid:
        return jsonify({"ok": True, "stand": "gesendet"})
    # Die Gegenseite hat gefragt - das hier ist die Zusage
    conn.execute(
        "UPDATE freundschaften SET bestaetigt=1 WHERE klein_id=? AND gross_id=?",
        (klein, gross))
    conn.commit()
    for ziel_id in (uid, user_id):
        socketio.emit("freunde_geaendert", {}, to=f"user:{ziel_id}")
    log.info("Nutzer %s und %s sind jetzt befreundet", uid, user_id)
    return jsonify({"ok": True, "stand": "freund"})


@app.delete("/api/freunde/<int:user_id>")
@login_required
def api_freund_loesen(user_id):
    """Zuruecknehmen, ablehnen oder die Freundschaft beenden - eine Taste
    fuer alle drei, denn es laeuft auf dasselbe hinaus."""
    uid = session["uid"]
    klein, gross = _paar(uid, user_id)
    conn = db()
    conn.execute("DELETE FROM freundschaften WHERE klein_id=? AND gross_id=?",
                 (klein, gross))
    conn.commit()
    for ziel_id in (uid, user_id):
        socketio.emit("freunde_geaendert", {}, to=f"user:{ziel_id}")
    return jsonify({"ok": True, "stand": ""})


# --------------------------------------------------------------------------
# Termine
# --------------------------------------------------------------------------
def kategorien_saeubern(roh):
    if not isinstance(roh, list):
        return []
    raus = []
    for k in roh:
        k = str(k or "").strip().lower()
        if k in KATEGORIEN and k not in raus:
            raus.append(k)
    return raus


def event_mitteilen(event_id, room_id):
    """Ueber eine Aenderung am Termin anstossen.

    Haengt der Termin an einer Unterhaltung, geht die Nachricht nur dorthin.
    Ein freier Termin hat keinen solchen Kreis - dort erfahren es alle, und
    jeder holt sich seine Liste neu; was er darin sehen darf, entscheidet
    ohnehin der Server.
    """
    daten = {"event_id": event_id, "room_id": room_id}
    if room_id:
        socketio.emit("event_geaendert", daten, to=f"room:{room_id}")
    else:
        socketio.emit("event_geaendert", daten)


@app.post("/api/rooms/<int:room_id>/event")
@login_required
def api_create_event(room_id):
    """Termin anlegen - er erscheint als Karte in der Unterhaltung."""
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    data = request.get_json(force=True)
    titel = (data.get("titel") or "").strip()
    if not titel:
        return jsonify({"error": "Der Titel fehlt."}), 400

    beginnt = data.get("beginnt_at")
    try:
        beginnt = int(beginnt) if beginnt else None
    except (TypeError, ValueError):
        return jsonify({"error": "Der Zeitpunkt ist unbrauchbar."}), 400

    punkt = _koordinaten(data) if data.get("lat") is not None else None

    conn = db()
    file_id = data.get("file_id")
    if file_id is not None:
        try:
            file_id = int(file_id)
        except (TypeError, ValueError):
            file_id = None
        # Nur eigene, frisch hochgeladene Bilder - sonst liesse sich eine
        # fremde Datei in den eigenen Termin einhaengen.
        if file_id is not None and not conn.execute(
                "SELECT 1 FROM files WHERE id=? AND user_id=?",
                (file_id, uid)).fetchone():
            file_id = None

    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO events (room_id, user_id, titel, beschreibung, ort_text,"
        " lat, lon, beginnt_at, file_id, kategorien, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (room_id, uid, titel[:200],
         (data.get("beschreibung") or "").strip()[:2000],
         (data.get("ort_text") or "").strip()[:200],
         punkt[0] if punkt else None, punkt[1] if punkt else None,
         beginnt, file_id,
         ",".join(kategorien_saeubern(data.get("kategorien"))), now))
    event_id = cur.lastrowid
    # Wer einlaedt, ist selbstverstaendlich dabei
    conn.execute(
        "INSERT INTO event_antworten (event_id, user_id, antwort, created_at)"
        " VALUES (?,?,'ja',?)", (event_id, uid, now))
    cur = conn.execute(
        "INSERT INTO messages (room_id, user_id, body, event_id, created_at)"
        " VALUES (?,?,'',?,?)", (room_id, uid, event_id, now))
    msg_id = cur.lastrowid
    conn.execute("UPDATE room_members SET last_read=? WHERE room_id=? AND user_id=?",
                 (msg_id, room_id, uid))
    conn.commit()

    row = conn.execute(MSG_QUERY + " WHERE m.id=?", (msg_id,)).fetchone()
    socketio.emit("message", msg_payload(row), to=f"room:{room_id}")
    mitglieder = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=?", (room_id,)).fetchall()]
    with ONLINE_LOCK:
        abwesend = [m for m in mitglieder if m != uid and m not in ONLINE]
    ziel = f"{EXTERNAL_URL}/?room={room_id}" if EXTERNAL_URL else f"?room={room_id}"
    push_to_users(abwesend, "Einladung", titel[:180], ziel)
    return jsonify({"ok": True, "event_id": event_id, "message_id": msg_id})


@app.post("/api/events")
@login_required
def api_create_freier_event():
    """Ein Termin, der an keiner Unterhaltung haengt.

    Wer ihn sehen darf, entscheidet sicht: ausgewaehlte Freunde oder alle
    im Umkreis von X Kilometern. Es entsteht keine Sprechblase - der Termin
    steht nur in der Liste und auf der Karte.
    """
    uid = session["uid"]
    data = request.get_json(force=True)
    titel = (data.get("titel") or "").strip()
    if not titel:
        return jsonify({"error": "Der Titel fehlt."}), 400

    sicht = (data.get("sicht") or "freunde").strip().lower()
    if sicht not in ("freunde", "umkreis"):
        return jsonify({"error": "Wähle Freunde oder einen Umkreis."}), 400

    beginnt = data.get("beginnt_at")
    try:
        beginnt = int(beginnt) if beginnt else None
    except (TypeError, ValueError):
        return jsonify({"error": "Der Zeitpunkt ist unbrauchbar."}), 400

    punkt = _koordinaten(data) if data.get("lat") is not None else None
    umkreis = None
    if sicht == "umkreis":
        if punkt is None:
            return jsonify(
                {"error": "Für einen Umkreis braucht der Termin einen Ort."}), 400
        try:
            umkreis = int(data.get("umkreis_km") or 5)
        except (TypeError, ValueError):
            umkreis = 5
        umkreis = max(1, min(EVENT_UMKREIS_MAX_KM, umkreis))

    conn = db()
    file_id = data.get("file_id")
    if file_id is not None:
        try:
            file_id = int(file_id)
        except (TypeError, ValueError):
            file_id = None
        if file_id is not None and not conn.execute(
                "SELECT 1 FROM files WHERE id=? AND user_id=?",
                (file_id, uid)).fetchone():
            file_id = None

    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO events (room_id, sicht, umkreis_km, user_id, titel,"
        " beschreibung, ort_text, lat, lon, beginnt_at, file_id, kategorien,"
        " created_at) VALUES (0,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sicht, umkreis, uid, titel[:200],
         (data.get("beschreibung") or "").strip()[:2000],
         (data.get("ort_text") or "").strip()[:200],
         punkt[0] if punkt else None, punkt[1] if punkt else None,
         beginnt, file_id,
         ",".join(kategorien_saeubern(data.get("kategorien"))), now))
    event_id = cur.lastrowid
    gaeste = set()
    if sicht == "freunde":
        gaeste = event_gaeste_setzen(conn, event_id, uid, data.get("gaeste"))
        if not gaeste:
            conn.execute("DELETE FROM events WHERE id=?", (event_id,))
            conn.commit()
            return jsonify({"error": "Wähle mindestens eine Person aus."}), 400
    conn.execute(
        "INSERT INTO event_antworten (event_id, user_id, antwort, created_at)"
        " VALUES (?,?,'ja',?)", (event_id, uid, now))
    conn.commit()

    # Ausgewaehlte Freunde bekommen Bescheid; beim Umkreis waere das nicht zu
    # beantworten, ohne alle Standorte durchzugehen - dort findet man den
    # Termin ueber die Liste und die Karte.
    if gaeste:
        with ONLINE_LOCK:
            abwesend = [g for g in gaeste if g not in ONLINE]
        ziel = f"{EXTERNAL_URL}/" if EXTERNAL_URL else "?"
        push_to_users(abwesend, "Einladung", titel[:180], ziel)
    event_mitteilen(event_id, 0)
    return jsonify({"ok": True, "event_id": event_id})


@app.post("/api/events/<int:event_id>/antwort")
@login_required
def api_event_antwort(event_id):
    """Zusagen, absagen, vielleicht - oder die Antwort zuruecknehmen."""
    uid = session["uid"]
    conn = db()
    ev = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if ev is None or not event_sichtbar(ev, uid, conn, _standort_aus_anfrage()):
        abort(403)
    if ev["abgesagt"]:
        return jsonify({"error": "Der Termin wurde abgesagt."}), 400
    antwort = (request.get_json(force=True).get("antwort") or "").strip().lower()
    if antwort and antwort not in ANTWORTEN:
        return jsonify({"error": "Diese Antwort gibt es nicht."}), 400
    if not antwort:
        conn.execute("DELETE FROM event_antworten WHERE event_id=? AND user_id=?",
                     (event_id, uid))
    else:
        conn.execute(
            "INSERT INTO event_antworten (event_id, user_id, antwort, created_at)"
            " VALUES (?,?,?,?) ON CONFLICT(event_id, user_id)"
            " DO UPDATE SET antwort=excluded.antwort, created_at=excluded.created_at",
            (event_id, uid, antwort, int(time.time())))
    conn.commit()
    event_mitteilen(event_id, ev["room_id"])
    return jsonify(event_payload(event_id, uid, conn))


@app.get("/api/events/<int:event_id>")
@login_required
def api_get_event(event_id):
    uid = session["uid"]
    conn = db()
    ev = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if ev is None or not event_sichtbar(ev, uid, conn, _standort_aus_anfrage()):
        abort(403)
    return jsonify(event_payload(event_id, uid, conn))


@app.get("/api/events")
@login_required
def api_list_events():
    """Was ansteht - aus allen meinen Unterhaltungen, naechster zuerst.

    Ein Termin rutscht im Verlauf nach oben und ist dann weg; die Liste holt
    ihn zurueck. Ist der Zeitpunkt vorbei, faellt er heraus - die Liste soll
    zeigen, was noch kommt, nicht was war.
    """
    uid = session["uid"]
    grenze = int(time.time())
    conn = db()
    ort = _standort_aus_anfrage()
    # Erst alles, was ueberhaupt in Frage kommt, dann die Sichtprüfung je
    # Termin: die Umkreisfrage laesst sich in SQL nicht sauber stellen.
    rows = conn.execute(
        "SELECT * FROM events"
        " WHERE abgesagt=0 AND (beginnt_at IS NULL OR beginnt_at>?)"
        " AND (room_id IN (SELECT room_id FROM room_members WHERE user_id=?)"
        "      OR user_id=? OR COALESCE(sicht,'raum')<>'raum')"
        " ORDER BY beginnt_at IS NULL, beginnt_at LIMIT 300",
        (grenze, uid, uid)).fetchall()
    sichtbar = [r["id"] for r in rows if event_sichtbar(r, uid, conn, ort)][:50]
    return jsonify([event_payload(i, uid, conn) for i in sichtbar])


@app.patch("/api/events/<int:event_id>")
@login_required
def api_update_event(event_id):
    """Einen Termin nachtraeglich aendern.

    Nur die mitgeschickten Felder werden angefasst - wer den Titel korrigiert,
    verliert nicht den Ort. Fuer Ort und Bild gilt: null loescht sie.
    """
    uid = session["uid"]
    me = current_user()
    conn = db()
    ev = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if ev is None or not event_sichtbar(ev, uid, conn):
        abort(403)
    if ev["user_id"] != uid and not me["is_admin"]:
        return jsonify({"error": "Nur wer eingeladen hat, kann das aendern."}), 403

    data = request.get_json(force=True)
    felder, werte = [], []

    if "titel" in data:
        titel = (data.get("titel") or "").strip()
        if not titel:
            return jsonify({"error": "Der Titel fehlt."}), 400
        felder.append("titel=?")
        werte.append(titel[:200])
    if "beschreibung" in data:
        felder.append("beschreibung=?")
        werte.append((data.get("beschreibung") or "").strip()[:2000])
    if "ort_text" in data:
        felder.append("ort_text=?")
        werte.append((data.get("ort_text") or "").strip()[:200])
    if "kategorien" in data:
        felder.append("kategorien=?")
        werte.append(",".join(kategorien_saeubern(data.get("kategorien"))))
    gaeste_neu = False
    if "gaeste" in data and (ev["sicht"] or "raum") == "freunde":
        # Nur der Gastgeber waehlt aus, wer eingeladen ist - der
        # Administrator darf einen Termin berichtigen, nicht umbesetzen.
        if ev["user_id"] != uid:
            return jsonify(
                {"error": "Nur wer eingeladen hat, kann die Gäste ändern."}), 403
        if not event_gaeste_setzen(conn, event_id, uid, data.get("gaeste")):
            conn.rollback()
            return jsonify({"error": "Wähle mindestens eine Person aus."}), 400
        gaeste_neu = True
    if "umkreis_km" in data and (ev["sicht"] or "raum") == "umkreis":
        try:
            km = int(data.get("umkreis_km") or 5)
        except (TypeError, ValueError):
            km = 5
        felder.append("umkreis_km=?")
        werte.append(max(1, min(EVENT_UMKREIS_MAX_KM, km)))
    if "abgesagt" in data:
        # Absagen und Zuruecknehmen bleiben beim Gastgeber - sonst waere der
        # Weg ueber das Aendern eine Hintertuer um genau diese Regel herum.
        if ev["user_id"] != uid:
            return jsonify(
                {"error": "Nur wer eingeladen hat, kann ab- oder zusagen."}), 403
        felder.append("abgesagt=?")
        werte.append(1 if data.get("abgesagt") else 0)

    if "beginnt_at" in data:
        roh = data.get("beginnt_at")
        if roh is None:
            felder.append("beginnt_at=?")
            werte.append(None)
        else:
            try:
                werte.append(int(roh))
                felder.append("beginnt_at=?")
            except (TypeError, ValueError):
                return jsonify({"error": "Der Zeitpunkt ist unbrauchbar."}), 400

    # Ort: beide Werte zusammen, sonst entstuende ein halber Punkt
    if "lat" in data or "lon" in data:
        if data.get("lat") is None or data.get("lon") is None:
            felder += ["lat=?", "lon=?"]
            werte += [None, None]
        else:
            punkt = _koordinaten(data)
            if punkt is None:
                return jsonify({"error": "Der Ort ist unbrauchbar."}), 400
            felder += ["lat=?", "lon=?"]
            werte += [punkt[0], punkt[1]]

    altes_bild = None
    if "file_id" in data:
        roh = data.get("file_id")
        if roh is None:
            neu_id = None
        else:
            try:
                neu_id = int(roh)
            except (TypeError, ValueError):
                neu_id = None
            if neu_id is not None and not conn.execute(
                    "SELECT 1 FROM files WHERE id=? AND user_id=?",
                    (neu_id, uid)).fetchone():
                neu_id = None
        if neu_id != ev["file_id"]:
            altes_bild = ev["file_id"]
        felder.append("file_id=?")
        werte.append(neu_id)

    if not felder:
        # Die Gaesteliste steht in einer eigenen Tabelle - sie waere sonst mit
        # dem Ende der Anfrage wieder verworfen.
        if gaeste_neu:
            conn.commit()
            event_mitteilen(event_id, ev["room_id"])
        return jsonify(event_payload(event_id, uid, conn))

    werte.append(event_id)
    conn.execute(f"UPDATE events SET {', '.join(felder)} WHERE id=?", werte)
    conn.commit()
    # Das abgeloeste Bild haelt nichts mehr fest
    if altes_bild:
        datei_aufraeumen(conn, altes_bild)

    event_mitteilen(event_id, ev["room_id"])
    log.info("Termin %s von Nutzer %s geaendert", event_id, uid)
    return jsonify(event_payload(event_id, uid, conn))


@app.delete("/api/events/<int:event_id>")
@login_required
def api_delete_event(event_id):
    """Absagen darf allein, wer eingeladen hat.

    Bewusst ohne Ausnahme fuer den Administrator: Wer zu einer Feier laedt,
    entscheidet auch, ob sie stattfindet. Wird ein Termin zum Problem, bleibt
    dem Administrator die Unterhaltung selbst.
    """
    uid = session["uid"]
    conn = db()
    ev = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if ev is None or not event_sichtbar(ev, uid, conn):
        abort(403)
    if ev["user_id"] != uid:
        return jsonify({"error": "Nur wer eingeladen hat, kann absagen."}), 403
    conn.execute("UPDATE events SET abgesagt=1 WHERE id=?", (event_id,))
    conn.commit()
    event_mitteilen(event_id, ev["room_id"])
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Live-Standort
# --------------------------------------------------------------------------
# Die Freigabe gilt immer nur fuer eine Unterhaltung und laeuft von selbst ab.
# Damit ist ohne weiteres Zutun geklaert, wer mitsehen darf: die Mitglieder.
LIVE_MAX_MINUTEN = 8 * 60


@app.get("/api/live")
@login_required
def api_live_lesen():
    return jsonify(live_sichtbar(session["uid"]))


@app.post("/api/live")
@login_required
def api_live_starten():
    """Freigabe starten oder verlaengern."""
    uid = session["uid"]
    data = request.get_json(force=True)
    art = (data.get("art") or "raum").strip().lower()
    if art not in FREIGABE_ARTEN:
        return jsonify({"error": "Diese Art der Freigabe gibt es nicht."}), 400
    umkreis = None
    room_id = 0
    if art == "raum":
        try:
            room_id = int(data.get("room_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Es fehlt die Unterhaltung."}), 400
        if not is_member(room_id, uid):
            abort(403)
    elif art == "umkreis":
        try:
            umkreis = int(data.get("umkreis_km") or UMKREIS_MAX_KM)
        except (TypeError, ValueError):
            return jsonify({"error": "Der Umkreis ist unbrauchbar."}), 400
        # Mehr als 25 km waere keine Nachbarschaft mehr
        umkreis = max(1, min(UMKREIS_MAX_KM, umkreis))
    punkt = _koordinaten(data)
    if punkt is None:
        return jsonify({"error": "Der Standort ist unbrauchbar."}), 400
    try:
        minuten = int(data.get("minuten") or 60)
    except (TypeError, ValueError):
        minuten = 60
    minuten = max(5, min(LIVE_MAX_MINUTEN, minuten))

    now = int(time.time())
    bis = now + minuten * 60
    conn = db()
    conn.execute(
        "INSERT INTO live_orte (user_id, room_id, lat, lon, genauigkeit,"
        " bis_at, art, umkreis_km, begonnen_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(user_id, room_id) DO UPDATE SET lat=excluded.lat,"
        " lon=excluded.lon, genauigkeit=excluded.genauigkeit,"
        " bis_at=excluded.bis_at, art=excluded.art,"
        " umkreis_km=excluded.umkreis_km, updated_at=excluded.updated_at",
        (uid, room_id, punkt[0], punkt[1], _genauigkeit(data), bis, art,
         umkreis, now, now))
    conn.commit()
    if art == "raum":
        socketio.emit("live_geaendert", {"room_id": room_id}, to=f"room:{room_id}")
    else:
        # Eine weite Freigabe geht niemanden ueber einen Raum an - jeder
        # Betroffene erfaehrt es einzeln.
        ziele = meine_freunde(uid, conn) if art == "freunde" else set()
        for ziel in ziele | {uid}:
            socketio.emit("live_geaendert", {}, to=f"user:{ziel}")
    return jsonify({"ok": True, "bis_at": bis, "art": art,
                    "umkreis_km": umkreis})


@app.post("/api/live/ping")
@login_required
def api_live_ping():
    """Neue Position fuer alle laufenden Freigaben - ein Aufruf statt viele."""
    uid = session["uid"]
    data = request.get_json(force=True)
    punkt = _koordinaten(data)
    if punkt is None:
        return jsonify({"error": "Der Standort ist unbrauchbar."}), 400
    now = int(time.time())
    conn = db()
    raeume = [r["room_id"] for r in conn.execute(
        "SELECT room_id FROM live_orte WHERE user_id=? AND bis_at>?",
        (uid, now)).fetchall()]
    if not raeume:
        return jsonify({"ok": True, "aktiv": 0})
    conn.execute(
        "UPDATE live_orte SET lat=?, lon=?, genauigkeit=?, updated_at=?"
        " WHERE user_id=? AND bis_at>?",
        (punkt[0], punkt[1], _genauigkeit(data), now, uid, now))
    conn.commit()
    for room_id in raeume:
        socketio.emit("live_geaendert", {"room_id": room_id}, to=f"room:{room_id}")
    return jsonify({"ok": True, "aktiv": len(raeume)})


@app.delete("/api/live")
@login_required
def api_live_beenden():
    """Freigabe beenden - eine bestimmte oder alle auf einmal."""
    uid = session["uid"]
    data = request.get_json(silent=True) or {}
    conn = db()
    roh = data.get("room_id")
    if roh is None:
        raeume = [r["room_id"] for r in conn.execute(
            "SELECT room_id FROM live_orte WHERE user_id=?", (uid,)).fetchall()]
        conn.execute("DELETE FROM live_orte WHERE user_id=?", (uid,))
    else:
        try:
            raeume = [int(roh)]
        except (TypeError, ValueError):
            return jsonify({"error": "Unbekannte Unterhaltung."}), 400
        conn.execute("DELETE FROM live_orte WHERE user_id=? AND room_id=?",
                     (uid, raeume[0]))
    conn.commit()
    for rid in raeume:
        socketio.emit("live_geaendert", {"room_id": rid}, to=f"room:{rid}")
    return jsonify({"ok": True, "beendet": len(raeume)})


# --------------------------------------------------------------------------
# Stimmung
# --------------------------------------------------------------------------
STIMMUNG_MAX_STUNDEN = 24


@app.get("/api/stimmung")
@login_required
def api_stimmung_lesen():
    return jsonify(stimmungen_sichtbar(session["uid"]))


@app.post("/api/stimmung")
@login_required
def api_stimmung_setzen():
    """Worauf ich gerade Lust haette. Ersetzt meine vorige Meldung."""
    uid = session["uid"]
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Schreib kurz, worauf du Lust hast."}), 400
    try:
        stunden = int(data.get("stunden") or 4)
    except (TypeError, ValueError):
        stunden = 4
    stunden = max(1, min(STIMMUNG_MAX_STUNDEN, stunden))
    punkt = _koordinaten(data) if data.get("lat") is not None else None

    now = int(time.time())
    conn = db()
    # Immer nur eine gueltige Meldung je Person - sonst steht die Pinnwand
    # nach einer Woche voll mit alten Launen.
    conn.execute("DELETE FROM stimmung_mit WHERE stimmung_id IN"
                 " (SELECT id FROM stimmungen WHERE user_id=?)", (uid,))
    conn.execute("DELETE FROM stimmungen WHERE user_id=?", (uid,))
    cur = conn.execute(
        "INSERT INTO stimmungen (user_id, emoji, text, lat, lon, bis_at,"
        " created_at) VALUES (?,?,?,?,?,?,?)",
        (uid, (data.get("emoji") or "")[:8], text[:280],
         punkt[0] if punkt else None, punkt[1] if punkt else None,
         now + stunden * 3600, now))
    conn.commit()
    stimmung_mitteilen(uid, conn)
    row = conn.execute(
        "SELECT s.*, u.display_name, u.avatar FROM stimmungen s"
        " JOIN users u ON u.id=s.user_id WHERE s.id=?",
        (cur.lastrowid,)).fetchone()
    return jsonify(stimmung_payload(row, uid, conn))


@app.post("/api/stimmung/<int:stimmung_id>/mit")
@login_required
def api_stimmung_mitmachen(stimmung_id):
    """Ich mache mit - noch einmal tippen nimmt es zurueck."""
    uid = session["uid"]
    conn = db()
    row = conn.execute(
        "SELECT s.*, u.display_name, u.avatar FROM stimmungen s"
        " JOIN users u ON u.id=s.user_id WHERE s.id=?",
        (stimmung_id,)).fetchone()
    if row is None or row["bis_at"] <= int(time.time()):
        return jsonify({"error": "Diese Meldung gilt nicht mehr."}), 404
    if row["user_id"] != uid and row["user_id"] not in mein_kreis(uid, conn):
        abort(403)
    hatte = conn.execute(
        "SELECT 1 FROM stimmung_mit WHERE stimmung_id=? AND user_id=?",
        (stimmung_id, uid)).fetchone()
    if hatte:
        conn.execute("DELETE FROM stimmung_mit WHERE stimmung_id=? AND user_id=?",
                     (stimmung_id, uid))
    else:
        conn.execute(
            "INSERT INTO stimmung_mit (stimmung_id, user_id, created_at)"
            " VALUES (?,?,?)", (stimmung_id, uid, int(time.time())))
    conn.commit()
    # Auch die Person selbst anstossen, falls sie nicht in meinem Kreis liegt
    socketio.emit("stimmung_geaendert", {}, to=f"user:{row['user_id']}")
    stimmung_mitteilen(uid, conn)
    return jsonify(stimmung_payload(row, uid, conn))


@app.delete("/api/stimmung/<int:stimmung_id>")
@login_required
def api_stimmung_loeschen(stimmung_id):
    uid = session["uid"]
    conn = db()
    row = conn.execute("SELECT user_id FROM stimmungen WHERE id=?",
                       (stimmung_id,)).fetchone()
    if row is None:
        return jsonify({"ok": True})
    if row["user_id"] != uid and not current_user()["is_admin"]:
        abort(403)
    conn.execute("DELETE FROM stimmung_mit WHERE stimmung_id=?", (stimmung_id,))
    conn.execute("DELETE FROM stimmungen WHERE id=?", (stimmung_id,))
    conn.commit()
    stimmung_mitteilen(uid, conn)
    return jsonify({"ok": True})


@app.delete("/api/rooms/<int:room_id>/avatar")
@login_required
def api_clear_room_avatar(room_id):
    room = db().execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if room is None or not is_member(room_id, session["uid"]):
        abort(403)
    db().execute("UPDATE rooms SET avatar=NULL WHERE id=?", (room_id,))
    db().commit()
    avatar_entfernen(room["avatar"])
    socketio.emit("avatar_changed", {"kind": "r", "id": room_id, "avatar": None},
                  to=f"room:{room_id}")
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Galerie
# --------------------------------------------------------------------------
# Bilder und Filme, die jemand ueber die Unterhaltung hinaus zeigen will -
# entweder den Freunden oder allen. Herzen zaehlt jeder; Kommentare lesen nur
# zwei: die Person, der das Bild gehoert, und die, die geschrieben hat.
GALERIE_ARTEN = ("freunde", "alle")
GALERIE_MIMES = ("image", "video")


def galerie_sichtbar(eintrag, uid, conn=None):
    """Darf ich diesen Eintrag sehen?"""
    if eintrag["user_id"] == uid:
        return True
    if eintrag["art"] == "alle":
        return True
    if eintrag["art"] == "freunde":
        return uid in meine_freunde(eintrag["user_id"], conn or db())
    return False


def galerie_eintrag_loeschen(conn, file_id):
    """Freigabe, Herzen und Kommentare zu einer Datei entfernen."""
    for g in conn.execute("SELECT id FROM galerie WHERE file_id=?",
                          (file_id,)).fetchall():
        conn.execute("DELETE FROM galerie_herzen WHERE galerie_id=?", (g["id"],))
        conn.execute("DELETE FROM galerie_worte WHERE galerie_id=?", (g["id"],))
    conn.execute("DELETE FROM galerie WHERE file_id=?", (file_id,))


def galerie_payload(eintrag, uid, conn=None):
    """Ein Eintrag mit Herzen und der Zahl der Kommentare, die ich sehe."""
    conn = conn or db()
    herzen = conn.execute(
        "SELECT COUNT(*) c FROM galerie_herzen WHERE galerie_id=?",
        (eintrag["id"],)).fetchone()["c"]
    meins = bool(conn.execute(
        "SELECT 1 FROM galerie_herzen WHERE galerie_id=? AND user_id=?",
        (eintrag["id"], uid)).fetchone())
    # Wie viele Kommentare ich sehe: als Besitzer alle, sonst nur den eigenen
    # Faden. Die Gesamtzahl waere schon eine Auskunft darueber, wer sonst
    # noch geschrieben hat.
    if eintrag["user_id"] == uid:
        worte = conn.execute(
            "SELECT COUNT(*) c FROM galerie_worte WHERE galerie_id=?",
            (eintrag["id"],)).fetchone()["c"]
    else:
        worte = conn.execute(
            "SELECT COUNT(*) c FROM galerie_worte WHERE galerie_id=? AND mit_id=?",
            (eintrag["id"], uid)).fetchone()["c"]
    return {
        "id": eintrag["id"],
        "file_id": eintrag["file_id"],
        "user_id": eintrag["user_id"],
        "art": eintrag["art"],
        "titel": eintrag["titel"] or "",
        "mime": eintrag["mime"],
        "name": eintrag["orig_name"],
        "at": eintrag["created_at"],
        "herzen": herzen,
        "mein_herz": meins,
        "worte": worte,
        "meins": eintrag["user_id"] == uid,
    }


GALERIE_QUERY = ("SELECT g.*, f.orig_name, f.mime FROM galerie g"
                 " JOIN files f ON f.id=g.file_id")


@app.get("/api/galerie/<int:user_id>")
@login_required
def api_galerie(user_id):
    """Was diese Person freigegeben hat - soweit ich es sehen darf."""
    uid = session["uid"]
    conn = db()
    person = conn.execute("SELECT display_name, avatar FROM users WHERE id=?",
                          (user_id,)).fetchone()
    if person is None:
        abort(404)
    rows = conn.execute(GALERIE_QUERY + " WHERE g.user_id=?"
                        " ORDER BY g.created_at DESC LIMIT 300",
                        (user_id,)).fetchall()
    sichtbar = [r for r in rows if galerie_sichtbar(r, uid, conn)]
    return jsonify({
        "person": {"id": user_id, "name": person["display_name"],
                   "avatar": person["avatar"]},
        "meine": user_id == uid,
        "eintraege": [galerie_payload(r, uid, conn) for r in sichtbar],
    })


@app.post("/api/galerie")
@login_required
def api_galerie_freigeben():
    """Eine eigene Datei freigeben - oder die Freigabe aendern."""
    uid = session["uid"]
    data = request.get_json(force=True)
    try:
        file_id = int(data.get("file_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Welche Datei denn?"}), 400
    art = (data.get("art") or "").strip().lower()
    if art not in GALERIE_ARTEN:
        return jsonify(
            {"error": "Freunde oder alle - etwas anderes gibt es nicht."}), 400
    conn = db()
    datei = conn.execute("SELECT * FROM files WHERE id=? AND user_id=?",
                         (file_id, uid)).fetchone()
    if datei is None:
        return jsonify({"error": "Freigeben kannst du nur, was von dir ist."}), 403
    # Nicht "art" nennen: so hiess schon die Freigabeart aus der Anfrage, und
    # der Eintrag bekaeme dann "image" statt "freunde" - sichtbar waere er
    # danach fuer niemanden mehr.
    dateiart = (datei["mime"] or "").split("/")[0]
    if dateiart not in GALERIE_MIMES:
        # Was der Chat nicht kennt, liegt als "application/octet-stream" da -
        # dann sieht es aus wie eine beliebige Datei, auch wenn es ein Foto
        # ist. Das soll die Meldung sagen, statt "nur Bilder und Filme".
        bekannt = ", ".join(sorted(
            m.split("/")[1].upper() for m in IMAGE_MIMES))
        return jsonify({"error": "Dieses Format kennt der Chat nicht, deshalb"
                        " liegt die Datei als gewöhnlicher Anhang da."
                        f" Bilder gehen als {bekannt}."}), 400
    titel = (data.get("titel") or "").strip()[:200]
    now = int(time.time())
    vorher = conn.execute("SELECT id FROM galerie WHERE file_id=?",
                          (file_id,)).fetchone()
    if vorher:
        conn.execute("UPDATE galerie SET art=?, titel=? WHERE id=?",
                     (art, titel, vorher["id"]))
        eintrag_id = vorher["id"]
    else:
        eintrag_id = conn.execute(
            "INSERT INTO galerie (file_id, user_id, art, titel, created_at)"
            " VALUES (?,?,?,?,?)", (file_id, uid, art, titel, now)).lastrowid
    conn.commit()
    row = conn.execute(GALERIE_QUERY + " WHERE g.id=?", (eintrag_id,)).fetchone()
    socketio.emit("galerie_geaendert", {"user_id": uid})
    return jsonify(galerie_payload(row, uid, conn))


@app.delete("/api/galerie/<int:eintrag_id>")
@login_required
def api_galerie_zuruecknehmen(eintrag_id):
    """Die Freigabe zuruecknehmen. Die Datei selbst bleibt, wo sie ist."""
    uid = session["uid"]
    conn = db()
    row = conn.execute("SELECT * FROM galerie WHERE id=?",
                       (eintrag_id,)).fetchone()
    if row is None:
        abort(404)
    if row["user_id"] != uid:
        return jsonify({"error": "Das ist nicht deins."}), 403
    conn.execute("DELETE FROM galerie_herzen WHERE galerie_id=?", (eintrag_id,))
    conn.execute("DELETE FROM galerie_worte WHERE galerie_id=?", (eintrag_id,))
    conn.execute("DELETE FROM galerie WHERE id=?", (eintrag_id,))
    conn.commit()
    # Ein Bild, das gleich hier hineingelegt wurde, haengt an keiner Nachricht.
    # Ohne die Freigabe haelt es nichts mehr fest - dann sollen auch die Bytes
    # nicht in /data liegen bleiben. Kam es aus einer Unterhaltung, bleibt es.
    datei_aufraeumen(conn, row["file_id"])
    socketio.emit("galerie_geaendert", {"user_id": uid})
    return jsonify({"ok": True})


@app.post("/api/galerie/<int:eintrag_id>/herz")
@login_required
def api_galerie_herz(eintrag_id):
    """Herz setzen oder wieder wegnehmen. Die Zahl sieht jeder."""
    uid = session["uid"]
    conn = db()
    row = conn.execute(GALERIE_QUERY + " WHERE g.id=?", (eintrag_id,)).fetchone()
    if row is None or not galerie_sichtbar(row, uid, conn):
        abort(403)
    da = conn.execute(
        "SELECT 1 FROM galerie_herzen WHERE galerie_id=? AND user_id=?",
        (eintrag_id, uid)).fetchone()
    if da:
        conn.execute("DELETE FROM galerie_herzen WHERE galerie_id=? AND user_id=?",
                     (eintrag_id, uid))
    else:
        conn.execute(
            "INSERT INTO galerie_herzen (galerie_id, user_id, created_at)"
            " VALUES (?,?,?)", (eintrag_id, uid, int(time.time())))
    conn.commit()
    socketio.emit("galerie_geaendert", {"user_id": row["user_id"]})
    return jsonify(galerie_payload(row, uid, conn))


@app.get("/api/galerie/<int:eintrag_id>/worte")
@login_required
def api_galerie_worte(eintrag_id):
    """Die Kommentare, die ich lesen darf.

    Als Besucher ist das mein eigener Faden mit der Person. Als Besitzer ein
    bestimmter Faden (mit=...) oder die Uebersicht, wer geschrieben hat.
    """
    uid = session["uid"]
    conn = db()
    row = conn.execute(GALERIE_QUERY + " WHERE g.id=?", (eintrag_id,)).fetchone()
    if row is None or not galerie_sichtbar(row, uid, conn):
        abort(403)
    mit = request.args.get("mit", type=int)
    if row["user_id"] != uid:
        mit = uid              # Besucher sehen immer nur ihren eigenen Faden
    if mit is None:
        faeden = conn.execute(
            "SELECT w.mit_id, u.display_name, u.avatar, COUNT(*) c,"
            " MAX(w.created_at) letzte FROM galerie_worte w"
            " JOIN users u ON u.id=w.mit_id WHERE w.galerie_id=?"
            " GROUP BY w.mit_id ORDER BY letzte DESC", (eintrag_id,)).fetchall()
        return jsonify({"faeden": [
            {"mit_id": f["mit_id"], "name": f["display_name"],
             "avatar": f["avatar"], "anzahl": f["c"], "letzte": f["letzte"]}
            for f in faeden], "worte": []})
    worte = conn.execute(
        "SELECT w.*, u.display_name, u.avatar FROM galerie_worte w"
        " JOIN users u ON u.id=w.user_id WHERE w.galerie_id=? AND w.mit_id=?"
        " ORDER BY w.created_at", (eintrag_id, mit)).fetchall()
    return jsonify({"mit_id": mit, "faeden": [], "worte": [
        {"id": w["id"], "user_id": w["user_id"], "name": w["display_name"],
         "avatar": w["avatar"], "text": w["text"], "at": w["created_at"],
         "meins": w["user_id"] == uid} for w in worte]})


@app.post("/api/galerie/<int:eintrag_id>/worte")
@login_required
def api_galerie_wort_schreiben(eintrag_id):
    """Einen Kommentar hinterlassen - oder als Besitzer antworten."""
    uid = session["uid"]
    conn = db()
    row = conn.execute(GALERIE_QUERY + " WHERE g.id=?", (eintrag_id,)).fetchone()
    if row is None or not galerie_sichtbar(row, uid, conn):
        abort(403)
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Da steht nichts."}), 400
    if row["user_id"] == uid:
        # Der Besitzer antwortet in einem bestimmten Faden
        try:
            mit = int(data.get("mit_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Wem denn?"}), 400
        if mit == uid or not conn.execute(
                "SELECT 1 FROM galerie_worte WHERE galerie_id=? AND mit_id=?",
                (eintrag_id, mit)).fetchone():
            return jsonify({"error": "Diesen Faden gibt es nicht."}), 400
    else:
        mit = uid
    now = int(time.time())
    conn.execute(
        "INSERT INTO galerie_worte (galerie_id, user_id, mit_id, text,"
        " created_at) VALUES (?,?,?,?,?)",
        (eintrag_id, uid, mit, text[:2000], now))
    conn.commit()
    # Nur die beiden Beteiligten erfahren davon - alle anderen geht der
    # Faden nichts an.
    gegen = row["user_id"] if uid != row["user_id"] else mit
    socketio.emit("galerie_wort", {"galerie_id": eintrag_id, "mit_id": mit},
                  to=f"user:{gegen}")
    return jsonify({"ok": True})


@app.delete("/api/galerie/worte/<int:wort_id>")
@login_required
def api_galerie_wort_loeschen(wort_id):
    """Den eigenen Kommentar zuruecknehmen."""
    uid = session["uid"]
    conn = db()
    row = conn.execute("SELECT * FROM galerie_worte WHERE id=?",
                       (wort_id,)).fetchone()
    if row is None:
        abort(404)
    if row["user_id"] != uid:
        return jsonify({"error": "Das hast du nicht geschrieben."}), 403
    conn.execute("DELETE FROM galerie_worte WHERE id=?", (wort_id,))
    conn.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Medien
# --------------------------------------------------------------------------
def datei_aufraeumen(conn, file_id):
    """Datensatz und Blob entfernen, sofern keine Nachricht mehr daran haengt."""
    noch_benutzt = conn.execute(
        "SELECT 1 FROM messages WHERE file_id=?", (file_id,)).fetchone()
    if noch_benutzt:
        return False
    # Auch das Bild einer Einladung haelt die Datei fest, obwohl keine
    # Nachricht daran haengt.
    if conn.execute("SELECT 1 FROM events WHERE file_id=?",
                    (file_id,)).fetchone():
        return False
    if conn.execute("SELECT 1 FROM tipps WHERE file_id=?",
                    (file_id,)).fetchone():
        return False
    # Eine Freigabe in der Galerie haelt die Datei ebenfalls fest. Sonst waere
    # ein Bild aus der Sammlung verschwunden, nur weil jemand die Nachricht
    # geloescht hat, mit der es einmal gekommen ist - oder weil die Frist fuer
    # alte Nachrichten abgelaufen ist. Wer es wirklich weghaben will, loescht
    # es unter "Medien"; das nimmt die Freigabe vorher heraus.
    if conn.execute("SELECT 1 FROM galerie WHERE file_id=?",
                    (file_id,)).fetchone():
        return False
    row = conn.execute("SELECT stored_name FROM files WHERE id=?",
                       (file_id,)).fetchone()
    if row is None:
        return False
    conn.execute("DELETE FROM files WHERE id=?", (file_id,))
    conn.commit()
    pfad = os.path.join(UPLOAD_DIR, row["stored_name"])
    try:
        os.remove(pfad)
    except FileNotFoundError:
        pass
    except OSError as exc:  # noqa: BLE001
        log.warning("Datei %s liess sich nicht entfernen: %s", pfad, exc)
    return True


MEDIA_QUERY = (
    "SELECT f.id, f.orig_name, f.mime, f.size, f.user_id,"
    " m.id AS msg_id, m.room_id, m.created_at AS at,"
    " u.display_name AS author"
    " FROM files f"
    " JOIN messages m ON m.file_id=f.id"
    " JOIN room_members rm ON rm.room_id=m.room_id AND rm.user_id=?"
    " JOIN users u ON u.id=m.user_id"
    " WHERE m.deleted=0")


@app.get("/api/media")
@login_required
def api_media():
    """Alle Dateien aus den Unterhaltungen, in denen ich Mitglied bin.

    Der Raumname kommt nicht mit - den kennt die Oberflaeche bereits aus
    /api/state, und fuer Direktchats haengt er ohnehin davon ab, wer fragt.
    """
    me = current_user()
    raum = request.args.get("room", type=int)
    grenze = min(request.args.get("limit", 300, type=int), 1000)
    args = [me["id"]]
    sql = MEDIA_QUERY
    if raum:
        sql += " AND m.room_id=?"
        args.append(raum)
    sql += " ORDER BY m.id DESC LIMIT ?"
    args.append(grenze)
    rows = db().execute(sql, args).fetchall()
    # Was ich selbst freigegeben habe, steht gleich mit dabei - sonst braeuchte
    # die Uebersicht je Kachel eine eigene Anfrage.
    frei = {g["file_id"]: g for g in db().execute(
        "SELECT file_id, id, art, titel FROM galerie WHERE user_id=?",
        (me["id"],)).fetchall()}
    return jsonify([{
        "id": r["id"],
        "galerie": (frei[r["id"]]["art"] if r["id"] in frei else None),
        "galerie_id": (frei[r["id"]]["id"] if r["id"] in frei else None),
        "galerie_titel": (frei[r["id"]]["titel"] if r["id"] in frei else ""),
        "name": r["orig_name"],
        "mime": r["mime"],
        "size": r["size"],
        "room_id": r["room_id"],
        "message_id": r["msg_id"],
        "at": r["at"],
        "author": r["author"],
        "mine": r["user_id"] == me["id"],
        "can_delete": bool(r["user_id"] == me["id"] or me["is_admin"]),
    } for r in rows])


def medium_loeschen(conn, me, file_id):
    """Eine Datei entfernen. Gibt (erfolg, grund, betroffene_nachrichten)."""
    row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if row is None:
        return False, "gibt es nicht", []
    nachrichten = conn.execute(
        "SELECT m.id, m.room_id FROM messages m"
        " JOIN room_members rm ON rm.room_id=m.room_id AND rm.user_id=?"
        " WHERE m.file_id=?", (me["id"], file_id)).fetchall()
    if not nachrichten and row["user_id"] != me["id"]:
        return False, "gibt es nicht", []
    if row["user_id"] != me["id"] and not me["is_admin"]:
        return False, "gehoert jemand anderem", []
    conn.execute("UPDATE messages SET deleted=1, body='', file_id=NULL"
                 " WHERE file_id=?", (file_id,))
    # Wer eine Datei loescht, will sie los sein - auch aus der Galerie, samt
    # Herzen und Kommentaren.
    galerie_eintrag_loeschen(conn, file_id)
    conn.commit()
    datei_aufraeumen(conn, file_id)
    return True, None, [dict(n) for n in nachrichten]


@app.post("/api/media/delete")
@login_required
def api_delete_media_mehrere():
    """Mehrere Dateien auf einmal entfernen - einzeln waere zu umstaendlich."""
    ids = request.get_json(force=True).get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "Es wurde nichts ausgewaehlt."}), 400
    if len(ids) > 500:
        return jsonify({"error": "Bitte nicht mehr als 500 auf einmal."}), 400
    me = current_user()
    conn = db()
    geloescht, abgelehnt = 0, 0
    raeume = {}
    for roh in ids:
        try:
            file_id = int(roh)
        except (TypeError, ValueError):
            abgelehnt += 1
            continue
        erfolg, _grund, nachrichten = medium_loeschen(conn, me, file_id)
        if erfolg:
            geloescht += 1
            for n in nachrichten:
                raeume.setdefault(n["room_id"], []).append(n["id"])
        else:
            abgelehnt += 1

    for room_id, msg_ids in raeume.items():
        for msg_id in msg_ids:
            socketio.emit("message_deleted", {"id": msg_id, "room_id": room_id},
                          to=f"room:{room_id}")
    log.info("%d Medien geloescht, %d abgelehnt", geloescht, abgelehnt)
    return jsonify({"geloescht": geloescht, "abgelehnt": abgelehnt})


@app.delete("/api/media/<int:file_id>")
@login_required
def api_delete_media(file_id):
    """Datei entfernen - aus dem Verlauf und von der Platte."""
    erfolg, grund, nachrichten = medium_loeschen(db(), current_user(), file_id)
    if not erfolg:
        if grund == "gibt es nicht":
            return jsonify({"error": "Diese Datei gibt es nicht."}), 404
        return jsonify({"error": "Fremde Dateien darf nur ein Administrator "
                                 "loeschen."}), 403
    for n in nachrichten:
        socketio.emit("message_deleted", {"id": n["id"], "room_id": n["room_id"]},
                      to=f"room:{n['room_id']}")
    return jsonify({"ok": True})


# Ein Geraet, eine Anmeldung. Mehr als das sind alte Eintraege, die niemand
# mehr abholt - der Browser wechselt die Adresse, wenn er die Erlaubnis neu
# vergibt. Ohne Deckel wuechse die Tabelle still vor sich hin.
PUSH_JE_KONTO_MAX = 20


@app.post("/api/push/subscribe")
@login_required
def api_push_subscribe():
    sub = request.get_json(force=True)
    keys = sub.get("keys", {})
    try:
        uid = session["uid"]
        conn = db()
        # Dieselbe Adresse kann vorher jemand anderem gehoert haben - etwa
        # wenn zwei sich einen Browser teilen. Das ist erlaubt, soll aber im
        # Protokoll stehen: von aussen ist es nicht zu unterscheiden von
        # jemandem, der eine fremde Adresse an sich zieht.
        vorher = conn.execute("SELECT user_id FROM push_subs WHERE endpoint=?",
                              (sub["endpoint"],)).fetchone()
        if vorher and vorher["user_id"] != uid:
            log.info("Push-Adresse wechselt von Nutzer %s zu %s",
                     vorher["user_id"], uid)
        conn.execute(
            "INSERT OR REPLACE INTO push_subs (user_id, endpoint, p256dh, auth, created_at)"
            " VALUES (?,?,?,?,?)",
            (uid, sub["endpoint"], keys["p256dh"], keys["auth"],
             int(time.time())))
        # Die aeltesten ueber der Grenze fallen weg
        conn.execute(
            "DELETE FROM push_subs WHERE user_id=? AND id NOT IN"
            " (SELECT id FROM push_subs WHERE user_id=?"
            "  ORDER BY created_at DESC LIMIT ?)",
            (uid, uid, PUSH_JE_KONTO_MAX))
        db().commit()
    except (KeyError, TypeError, AttributeError, sqlite3.Error) as exc:
        # Der Wortlaut bleibt im Protokoll - nach draussen gehoert er nicht,
        # er verriete Tabellennamen und Spalten.
        log.warning("Push-Anmeldung abgelehnt: %s", exc)
        return jsonify({"error": "Die Anmeldung war unvollstaendig."}), 400
    return jsonify({"ok": True})


@app.post("/api/messages/<int:msg_id>/weiterleiten")
@login_required
def api_weiterleiten(msg_id):
    """Eine Nachricht in eine andere Unterhaltung schicken.

    Warum ein eigener Weg und nicht einfach neu senden: der Anhang gehoert
    dem urspruenglichen Absender. Beim normalen Senden weist der Server eine
    fremde Datei ab - und das soll er auch. Hier wird stattdessen geprueft,
    dass ich die Nachricht ueberhaupt sehen darf, und die Datei danach
    unveraendert mitgenommen.
    """
    uid = session["uid"]
    conn = db()
    quelle = conn.execute(
        "SELECT m.*, u.display_name FROM messages m"
        " JOIN users u ON u.id=m.user_id WHERE m.id=?", (msg_id,)).fetchone()
    if quelle is None or not is_member(quelle["room_id"], uid):
        abort(403)
    if quelle["deleted"]:
        return jsonify({"error": "Diese Nachricht wurde geloescht."}), 400
    if quelle["poll_id"] or quelle["event_id"]:
        return jsonify({"error": "Abstimmungen und Einladungen lassen sich"
                                 " nicht weiterleiten."}), 400

    try:
        ziel = int(request.get_json(force=True).get("room_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Es fehlt die Unterhaltung."}), 400
    if not is_member(ziel, uid):
        abort(403)
    if ziel == quelle["room_id"]:
        return jsonify({"error": "Die Nachricht steht dort schon."}), 400

    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO messages (room_id, user_id, body, file_id, lat, lon,"
        " sprachdauer, weitergeleitet, created_at) VALUES (?,?,?,?,?,?,?,1,?)",
        (ziel, uid, quelle["body"], quelle["file_id"], quelle["lat"],
         quelle["lon"], quelle["sprachdauer"], now))
    neue_id = cur.lastrowid
    conn.execute("UPDATE room_members SET last_read=? WHERE room_id=? AND user_id=?",
                 (neue_id, ziel, uid))
    conn.commit()

    row = conn.execute(MSG_QUERY + " WHERE m.id=?", (neue_id,)).fetchone()
    nutzlast = msg_payload(row)
    socketio.emit("message", nutzlast, to=f"room:{ziel}")
    mitglieder = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=?", (ziel,)).fetchall()]
    with ONLINE_LOCK:
        abwesend = [m for m in mitglieder if m != uid and m not in ONLINE]
    url = f"{EXTERNAL_URL}/?room={ziel}" if EXTERNAL_URL else f"?room={ziel}"
    push_to_users(abwesend, "Weitergeleitet",
                  (quelle["body"] or "Datei")[:180], url)
    log.info("Nutzer %s hat Nachricht %s nach Raum %s weitergeleitet",
             uid, msg_id, ziel)
    return jsonify({"ok": True, "id": neue_id})


@app.delete("/api/messages/<int:msg_id>")
@login_required
def api_delete_message(msg_id):
    me = current_user()
    row = db().execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    if not row:
        abort(404)
    if row["user_id"] != me["id"] and not me["is_admin"]:
        return jsonify({"error": "Du kannst nur eigene Nachrichten loeschen."}), 403
    db().execute("UPDATE messages SET deleted=1, body='', file_id=NULL WHERE id=?",
                 (msg_id,))
    db().commit()
    # Haengt an der Nachricht eine Datei und nutzt sie sonst niemand mehr,
    # verschwindet sie mit - sonst blieben die Bytes fuer immer in /data liegen.
    if row["file_id"]:
        datei_aufraeumen(db(), row["file_id"])
    socketio.emit("message_deleted", {"id": msg_id, "room_id": row["room_id"]},
                  to=f"room:{row['room_id']}")
    return jsonify({"ok": True})


@app.post("/api/notify")
def api_notify():
    """Nachrichten aus Home Assistant (rest_command / Automation).

    Header: Authorization: Bearer <api_token>
    Body:   {"room": "Familie", "message": "Waschmaschine ist fertig"}
    """
    # "Bearer <token>" ist die uebliche Form, aber wer in secrets.yaml nur das
    # nackte Token hinterlegt, soll nicht ratlos vor einem 401 stehen - beides
    # wird angenommen.
    #
    # In der Adresse (?token=...) geht es bewusst nicht mehr: der
    # Zugriffsprotokollant schreibt die ganze Anfragezeile mit, das Token
    # stuende damit im Klartext im Add-on-Log - und Logs werden weitergereicht.
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    else:
        token = auth
    if not token and request.args.get("token"):
        log.warning("Nachricht aus Home Assistant abgelehnt: das Token stand in"
                    " der Adresse. Es gehoert in den Kopf Authorization,"
                    " sonst landet es im Protokoll.")
        return jsonify({"error": "Das Token gehoert in den Kopf"
                                 " 'Authorization', nicht in die Adresse."}), 401
    if not token or not secrets.compare_digest(token, API_TOKEN):
        # Home Assistant meldet einen rest_command auch dann als erfolgreich,
        # wenn wir ablehnen - deshalb steht der Grund hier im Protokoll.
        log.warning("Nachricht aus Home Assistant abgelehnt: %s",
                    "kein Token mitgeschickt" if not token
                    else "das Token stimmt nicht")
        return jsonify({"error": "Token ungueltig."}), 401

    data = request.get_json(force=True, silent=True) or request.form
    target = (data.get("room") or "").strip()
    text = (data.get("message") or "").strip()
    # Aus einer rest_command-Vorlage kommt oft der Text "true" statt eines
    # echten Wahrheitswerts.
    immer = str(data.get("always", "")).strip().lower() in ("1", "true", "ja",
                                                            "yes", "on")
    if not target or not text:
        log.warning("Nachricht aus Home Assistant abgelehnt: %s",
                    "'room' fehlt" if not target else "'message' fehlt")
        return jsonify({"error": "room und message werden gebraucht."}), 400

    conn = db()
    bot = conn.execute("SELECT * FROM users WHERE username=?", (BOT_USERNAME,)).fetchone()
    room = conn.execute("SELECT * FROM rooms WHERE name=? AND is_group=1",
                        (target,)).fetchone()
    now = int(time.time())

    if room is None:
        user = conn.execute(
            "SELECT * FROM users WHERE (lower(username)=? OR display_name=?)"
            " AND active=1", (target.lower(), target)).fetchone()
        if user is None:
            vorhanden = [r["name"] for r in conn.execute(
                "SELECT name FROM rooms WHERE is_group=1 AND name IS NOT NULL"
                " ORDER BY name").fetchall()]
            log.warning("Nachricht aus Home Assistant abgelehnt: weder Gruppe "
                        "noch Person mit dem Namen '%s'. Vorhandene Gruppen: %s",
                        target, ", ".join(vorhanden) or "(keine)")
            return jsonify({"error": f"Weder Gruppe noch Person mit dem Namen "
                                     f"'{target}' gefunden.",
                            "gruppen": vorhanden}), 404
        room = conn.execute(
            "SELECT r.* FROM rooms r"
            " JOIN room_members a ON a.room_id=r.id AND a.user_id=?"
            " JOIN room_members b ON b.room_id=r.id AND b.user_id=?"
            " WHERE r.is_group=0", (bot["id"], user["id"])).fetchone()
        if room is None:
            cur = conn.execute(
                "INSERT INTO rooms (name, is_group, created_by, created_at)"
                " VALUES (NULL,0,?,?)", (bot["id"], now))
            rid = cur.lastrowid
            conn.executemany(
                "INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)",
                [(rid, bot["id"]), (rid, user["id"])])
            conn.commit()
            room = conn.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            join_user_sockets(user["id"], rid)
            socketio.emit("room_added", room_payload(room, user["id"], conn),
                          to=f"user:{user['id']}")
    else:
        conn.execute("INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?,?)",
                     (room["id"], bot["id"]))
        conn.commit()

    cur = conn.execute(
        "INSERT INTO messages (room_id, user_id, body, created_at) VALUES (?,?,?,?)",
        (room["id"], bot["id"], text[:8000], now))
    conn.commit()
    row = conn.execute(MSG_QUERY + " WHERE m.id=?", (cur.lastrowid,)).fetchone()
    payload = msg_payload(row)
    socketio.emit("message", payload, to=f"room:{room['id']}")

    members = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=?", (room["id"],)).fetchall()]
    # Normalerweise nur an alle, die gerade nicht zusehen. Mit "always" geht
    # die Meldung auch an offene Sitzungen - fuer Alarme, die niemand
    # verpassen soll.
    with ONLINE_LOCK:
        empfaenger = [m for m in members if m != bot["id"]
                      and (immer or m not in ONLINE)]
    # Ohne external_url relativ lassen: der Service Worker loest das gegen
    # seine eigene Adresse auf und trifft damit auch unter Ingress den Chat.
    url = f"{EXTERNAL_URL}/?room={room['id']}" if EXTERNAL_URL else f"?room={room['id']}"
    push_to_users(empfaenger, "Home Assistant", text[:180], url)
    log.info("Nachricht aus Home Assistant an '%s' zugestellt, %d benachrichtigt",
             target, len(empfaenger))
    return jsonify({"ok": True, "room_id": room["id"],
                    "message_id": payload["id"], "pushed": len(empfaenger)})


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": f"Die Datei ist groesser als {MAX_UPLOAD_MB} MB."}), 413


# --------------------------------------------------------------------------
# Socket.IO
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Anrufe
# --------------------------------------------------------------------------
# Der Server vermittelt nur: er sagt, wer mitmacht, und reicht die
# Aushandlungsdaten weiter. Bild und Ton laufen direkt zwischen den Geraeten,
# nie ueber den Pi - das haelt ihn frei und die Gespraeche unter uns.
#
# Jeder spricht mit jedem einzeln (Mesh). Fuer eine Familienrunde ist das
# genau richtig und braucht keinen Medienserver; ab etwa fuenf Leuten wird
# die eigene Leitung dabei allerdings eng, deshalb die Obergrenze.
ANRUF_MAX = 6
ANRUFE = {}
ANRUF_LOCK = threading.Lock()


def anruf_stand(room_id):
    """Wer gerade in diesem Raum telefoniert - oder None."""
    with ANRUF_LOCK:
        anruf = ANRUFE.get(room_id)
        if not anruf or not anruf["wer"]:
            return None
        return {"room_id": room_id, "art": anruf["art"],
                "seit": anruf["seit"], "wer": sorted(anruf["wer"])}


def anruf_melden(room_id):
    stand = anruf_stand(room_id)
    socketio.emit("anruf_stand", stand or {"room_id": room_id, "wer": []},
                  to=f"room:{room_id}")


def anruf_verlassen(room_id, uid, grund="verlassen"):
    with ANRUF_LOCK:
        anruf = ANRUFE.get(room_id)
        if not anruf or uid not in anruf["wer"]:
            return False
        anruf["wer"].discard(uid)
        if not anruf["wer"]:
            ANRUFE.pop(room_id, None)
    socketio.emit("anruf_weg", {"room_id": room_id, "user_id": uid,
                                "grund": grund}, to=f"room:{room_id}")
    anruf_melden(room_id)
    log.info("Nutzer %s hat den Anruf in Raum %s verlassen (%s)",
             uid, room_id, grund)
    return True


@app.get("/api/anruf/server")
@login_required
def api_ice_server():
    """Welche Vermittlungsserver der Browser fuer Anrufe nutzen soll.

    Im Heimnetz braucht es keinen: die Geraete finden sich direkt. Von
    unterwegs kennt ein Geraet seine oeffentliche Adresse nicht - dafuer ist
    ein STUN-Server da. Er sieht nur diese Adresse, nie Bild oder Ton.
    """
    server = []
    if STUN_SERVER:
        server.append({"urls": STUN_SERVER})
    if TURN_SERVER:
        eintrag = {"urls": TURN_SERVER}
        if TURN_BENUTZER:
            eintrag["username"] = TURN_BENUTZER
            eintrag["credential"] = TURN_PASSWORT
        server.append(eintrag)
    return jsonify({"iceServers": server, "max": ANRUF_MAX,
                    "stun": bool(STUN_SERVER), "turn": bool(TURN_SERVER)})


def _anruf_raum_pruefen(room_id, uid):
    conn = raw_db()
    treffer = conn.execute(
        "SELECT 1 FROM room_members m JOIN users u ON u.id=m.user_id"
        " WHERE m.room_id=? AND m.user_id=? AND u.active=1",
        (room_id, uid)).fetchone()
    conn.close()
    return treffer is not None


def _anruf_klingeln(room_id, uid):
    """Wer gerade nicht zusieht, bekommt eine Benachrichtigung."""
    conn = raw_db()
    mitglieder = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=?", (room_id,)).fetchall()]
    rufer = conn.execute("SELECT display_name FROM users WHERE id=?",
                         (uid,)).fetchone()
    conn.close()
    with ONLINE_LOCK:
        abwesend = [m for m in mitglieder if m != uid and m not in ONLINE]
    ziel = f"{EXTERNAL_URL}/?room={room_id}" if EXTERNAL_URL else f"?room={room_id}"
    push_to_users(abwesend, "Anruf",
                  f"{rufer['display_name'] if rufer else 'Jemand'} ruft an", ziel)


@socketio.on("anruf_beitreten")
def on_anruf_beitreten(data):
    """Anruf beginnen oder einem laufenden beitreten."""
    uid = session.get("uid")
    if not uid:
        return {"ok": False, "error": "Du bist nicht mehr angemeldet."}
    try:
        room_id = int(data.get("room_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Unbekannte Unterhaltung."}
    if not _anruf_raum_pruefen(room_id, uid):
        return {"ok": False, "error": "Du gehoerst nicht zu dieser Unterhaltung."}
    art = "video" if data.get("art") == "video" else "audio"

    with ANRUF_LOCK:
        anruf = ANRUFE.get(room_id)
        neu = anruf is None
        if neu:
            anruf = {"art": art, "seit": int(time.time()), "wer": set()}
            ANRUFE[room_id] = anruf
        elif art == "video":
            # Schaltet jemand die Kamera zu, wird aus dem Telefonat ein
            # Videoanruf - fuer alle sichtbar.
            anruf["art"] = "video"
        if uid in anruf["wer"]:
            return {"ok": True, "art": anruf["art"],
                    "bestehende": sorted(anruf["wer"] - {uid})}
        if len(anruf["wer"]) >= ANRUF_MAX:
            if neu:
                ANRUFE.pop(room_id, None)
            return {"ok": False,
                    "error": f"An einem Anruf koennen hoechstens {ANRUF_MAX}"
                             " Personen teilnehmen."}
        bestehende = sorted(anruf["wer"])
        anruf["wer"].add(uid)
        laufende_art = anruf["art"]

    # Die schon Anwesenden bauen die Verbindung zum Neuen auf. So ruft immer
    # genau eine Seite an, und beide kommen sich nicht ins Gehege.
    for anderer in bestehende:
        socketio.emit("anruf_neuer", {"room_id": room_id, "user_id": uid},
                      to=f"user:{anderer}")
    anruf_melden(room_id)
    if neu:
        log.info("Nutzer %s startet einen %s-Anruf in Raum %s", uid, art, room_id)
        _anruf_klingeln(room_id, uid)
    return {"ok": True, "art": laufende_art, "bestehende": bestehende}


@socketio.on("anruf_verlassen")
def on_anruf_verlassen(data):
    uid = session.get("uid")
    if not uid:
        return {"ok": False}
    try:
        room_id = int(data.get("room_id"))
    except (TypeError, ValueError):
        return {"ok": False}
    anruf_verlassen(room_id, uid)
    return {"ok": True}


@socketio.on("anruf_ablehnen")
def on_anruf_ablehnen(data):
    """Nicht abnehmen - die anderen sollen es trotzdem erfahren."""
    uid = session.get("uid")
    if not uid:
        return {"ok": False}
    try:
        room_id = int(data.get("room_id"))
    except (TypeError, ValueError):
        return {"ok": False}
    if _anruf_raum_pruefen(room_id, uid):
        socketio.emit("anruf_abgelehnt", {"room_id": room_id, "user_id": uid},
                      to=f"room:{room_id}")
    return {"ok": True}


@socketio.on("anruf_signal")
def on_anruf_signal(data):
    """Angebot, Antwort und Wegbeschreibungen weiterreichen.

    Der Inhalt wird nicht angefasst - der Server ist hier nur Briefkasten.
    Geprueft wird aber, dass beide im selben Anruf sitzen; sonst koennte
    jemand Fremden Datenpakete zuschicken.
    """
    uid = session.get("uid")
    if not uid:
        return {"ok": False}
    try:
        room_id = int(data.get("room_id"))
        an = int(data.get("an"))
    except (TypeError, ValueError):
        return {"ok": False}
    with ANRUF_LOCK:
        anruf = ANRUFE.get(room_id)
        drin = bool(anruf) and uid in anruf["wer"] and an in anruf["wer"]
    if not drin:
        return {"ok": False, "error": "Ihr seid nicht im selben Anruf."}
    socketio.emit("anruf_signal", {"room_id": room_id, "von": uid,
                                   "art": data.get("art"),
                                   "daten": data.get("daten")},
                  to=f"user:{an}")
    return {"ok": True}


def _gleiche_herkunft():
    """Kommt die Verbindung von der eigenen Seite?

    cors_allowed_origins steht auf "*", weil die Oberflaeche unter zwei
    Adressen zugleich erreichbar ist - ueber den Ingress von Home Assistant
    und ueber die externe Adresse - und keine davon hier bekannt ist. Damit
    fehlt aber die Bremse, die sonst fremde Seiten abhaelt. SameSite=Lax
    haelt das Cookie zwar schon zurueck; dies ist der zweite Riegel, falls
    ein Browser das einmal anders sieht.

    Ohne Origin (etwa aus einem Skript ohne Browser) wird nicht abgewiesen -
    dort schuetzt ohnehin das Cookie, das eine fremde Seite nicht kennt.
    """
    herkunft = request.headers.get("Origin")
    if not herkunft:
        return True
    gastgeber = request.headers.get("Host", "")
    try:
        from urllib.parse import urlsplit
        return urlsplit(herkunft).netloc.lower() == gastgeber.lower()
    except ValueError:
        return False


@socketio.on("connect")
def on_connect():
    uid = session.get("uid")
    if not uid:
        return False
    if not _gleiche_herkunft():
        log.warning("Datenstrom abgewiesen: Anfrage von %r, wir sind %r",
                    request.headers.get("Origin"), request.headers.get("Host"))
        return False
    conn = raw_db()
    # Gesperrte Konten und veraltete Sitzungen kommen auch mit gueltigem
    # Cookie nicht mehr an den Datenstrom.
    me = conn.execute("SELECT active, pw_version FROM users WHERE id=?",
                      (uid,)).fetchone()
    if me is None or not me["active"] or session.get("pwv", 0) != me["pw_version"]:
        conn.close()
        return False
    with ONLINE_LOCK:
        ONLINE[uid] = ONLINE.get(uid, 0) + 1
        first = ONLINE[uid] == 1
    join_room(f"user:{uid}")
    for row in conn.execute("SELECT room_id FROM room_members WHERE user_id=?",
                            (uid,)).fetchall():
        join_room(f"room:{row['room_id']}")
    conn.close()
    if first:
        socketio.emit("presence", {"user_id": uid, "online": True})
    return None


@socketio.on("disconnect")
def on_disconnect():
    uid = session.get("uid")
    if not uid:
        return
    with ONLINE_LOCK:
        ONLINE[uid] = ONLINE.get(uid, 1) - 1
        gone = ONLINE[uid] <= 0
        if gone:
            ONLINE.pop(uid, None)
    if gone:
        # Wer die Seite schliesst, soll nicht als stumme Kachel stehen bleiben
        with ANRUF_LOCK:
            raeume = [r for r, a in ANRUFE.items() if uid in a["wer"]]
        for room_id in raeume:
            anruf_verlassen(room_id, uid, "Verbindung verloren")
        socketio.emit("presence", {"user_id": uid, "online": False})


@socketio.on("typing")
def on_typing(data):
    """"Schreibt gerade" - nur in Unterhaltungen, in denen ich auch bin.

    Vorher ging der Hinweis in jede beliebige Unterhaltung, und der Name kam
    aus der Anfrage. Damit liess sich ein fremder Name in einen fremden Raum
    schreiben. Beides kommt jetzt vom Server.
    """
    uid = session.get("uid")
    if not uid:
        return
    try:
        room_id = int(data.get("room_id", 0))
    except (TypeError, ValueError):
        return
    if not is_member(room_id, uid):
        return
    me = session_user()
    if me is None:
        return
    emit("typing", {"room_id": room_id, "user_id": uid,
                    "name": me["display_name"]},
         to=f"room:{room_id}", include_self=False)


@socketio.on("send")
def on_send(data):
    uid = session.get("uid")
    if not uid:
        return {"ok": False, "error": "Du bist nicht mehr angemeldet."}
    room_id = int(data.get("room_id", 0))
    body = (data.get("body") or "").strip()
    file_id = data.get("file_id")
    reply_to = data.get("reply_to")
    # Mehrere Bilder auf einmal tragen dieselbe Kennung und erscheinen dann
    # als ein Album statt als lauter Einzelnachrichten.
    album = (str(data.get("album") or "").strip() or None)
    if album and (len(album) > 40 or not album.replace("-", "").isalnum()):
        album = None
    # Standort: nur plausible Werte uebernehmen
    lat = lon = None
    ort = data.get("ort")
    if isinstance(ort, dict):
        try:
            lat, lon = float(ort.get("lat")), float(ort.get("lon"))
        except (TypeError, ValueError):
            lat = lon = None
        if lat is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            lat = lon = None
    # Sprachnachricht: die Laenge in Sekunden. Sie steht schon in der Blase,
    # bevor der Ton geladen ist - sonst waere dort erst ein leerer Balken.
    sprachdauer = None
    try:
        roh = data.get("sprachdauer")
        if roh is not None:
            sprachdauer = max(1, min(3600, int(float(roh))))
    except (TypeError, ValueError):
        sprachdauer = None
    if sprachdauer is not None and file_id is None:
        sprachdauer = None
    if not body and not file_id and lat is None:
        return {"ok": False, "error": "Die Nachricht ist leer."}

    conn = raw_db()
    member = conn.execute(
        "SELECT 1 FROM room_members m JOIN users u ON u.id=m.user_id"
        " WHERE m.room_id=? AND m.user_id=? AND u.active=1",
        (room_id, uid)).fetchone()
    if not member:
        conn.close()
        return {"ok": False, "error": "Du gehoerst nicht zu dieser Unterhaltung."}
    if file_id is not None:
        # Datei-IDs sind fortlaufend. Ohne diese Pruefung koennte man eine
        # fremde Datei an eine eigene Nachricht haengen und sie damit fuer den
        # eigenen Raum freischalten - api_file leitet die Berechtigung genau
        # aus dieser Verknuepfung ab.
        try:
            file_id = int(file_id)
        except (TypeError, ValueError):
            conn.close()
            return {"ok": False, "error": "Die Datei wurde nicht erkannt."}
        owner = conn.execute("SELECT user_id FROM files WHERE id=?",
                             (file_id,)).fetchone()
        if owner is None or owner["user_id"] != uid:
            log.warning("Nutzer %s wollte fremde Datei %s anhaengen", uid, file_id)
            conn.close()
            return {"ok": False, "error": "Diese Datei gehoert dir nicht."}
    if reply_to:
        parent = conn.execute("SELECT room_id FROM messages WHERE id=?",
                              (reply_to,)).fetchone()
        if not parent or parent["room_id"] != room_id:
            reply_to = None
    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO messages (room_id, user_id, body, file_id, reply_to, album,"
        " lat, lon, sprachdauer, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (room_id, uid, body[:8000], file_id, reply_to, album, lat, lon,
         sprachdauer, now))
    msg_id = cur.lastrowid
    conn.execute("UPDATE room_members SET last_read=? WHERE room_id=? AND user_id=?",
                 (msg_id, room_id, uid))
    conn.commit()

    row = conn.execute(MSG_QUERY + " WHERE m.id=?", (msg_id,)).fetchone()
    payload = msg_payload(row)
    room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    members = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=?", (room_id,)).fetchall()]
    # Wer die Unterhaltung stummgeschaltet hat, bekommt keine Meldung. Das
    # muss hier stehen, solange die Verbindung noch offen ist.
    stumme = {r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=? AND stumm_bis IS NOT NULL"
        " AND (stumm_bis=0 OR stumm_bis>?)", (room_id, now)).fetchall()}
    conn.close()

    socketio.emit("message", payload, to=f"room:{room_id}")

    with ONLINE_LOCK:
        offline = [m for m in members if m != uid and m not in ONLINE]
    offline = [m for m in offline if m not in stumme]
    title = room["name"] if room["is_group"] else payload["author"]
    if room["is_group"]:
        text = f"{payload['author']}: {body or 'Datei'}"
    else:
        text = body or "Datei gesendet"
    url = f"{EXTERNAL_URL}/?room={room_id}" if EXTERNAL_URL else f"?room={room_id}"
    push_to_users(offline, title, text[:180], url)
    # Rueckmeldung an den Absender: ohne sie verschwindet eine abgelehnte
    # Nachricht spurlos, und niemand weiss warum.
    return {"ok": True, "id": msg_id}


if AUFBEWAHRUNG_TAGE > 0:
    log.info("Nachrichten und Anhaenge werden nach %s Tagen entfernt",
             AUFBEWAHRUNG_TAGE)
    threading.Thread(target=aufraeum_schleife, daemon=True).start()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8099, allow_unsafe_werkzeug=True)
