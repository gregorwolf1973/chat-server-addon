#!/usr/bin/env python3
"""Chat Server - Home Assistant Add-on.

Flask + Socket.IO, SQLite unter /data, Web-Push fuer Benachrichtigungen.
"""
import base64
import json
import logging
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
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 90

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


def migrate(conn):
    """Fehlende Spalten aelterer Installationen nachziehen."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
    if "reply_to" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN reply_to INTEGER")
    if "deleted" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "pw_version" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pw_version INTEGER NOT NULL DEFAULT 0")
    if "pending" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pending INTEGER NOT NULL DEFAULT 0")
    for spalte in ("email", "phone", "note", "avatar"):
        if spalte not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {spalte} TEXT")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(rooms)")}
    if "avatar" not in cols:
        conn.execute("ALTER TABLE rooms ADD COLUMN avatar TEXT")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(room_members)")}
    if "color" not in cols:
        conn.execute("ALTER TABLE room_members ADD COLUMN color TEXT")
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
IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}
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


@app.context_processor
def vorlagen_werte():
    """Steht allen Vorlagen zur Verfuegung - etwa fuer den Link zur Anmeldung."""
    return {"registration_open": ALLOW_REGISTRATION, "statisch": statisch}


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


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
        "SELECT last_read, color FROM room_members WHERE room_id=? AND user_id=?",
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
        "color": eigenes["color"] if eigenes else None,
        "members": [dict(m) for m in members],
        "online": online,
        "unread": unread,
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


def zu_viele_antraege(adresse):
    jetzt = time.time()
    with ANTRAEGE_LOCK:
        frisch = [t for t in ANTRAEGE.get(adresse, []) if jetzt - t < 3600]
        # Nebenbei aufraeumen, damit die Tabelle nicht unbegrenzt waechst
        for schluessel in [k for k, v in ANTRAEGE.items()
                           if all(jetzt - t >= 3600 for t in v)]:
            ANTRAEGE.pop(schluessel, None)
        if len(frisch) >= ANTRAEGE_PRO_STUNDE:
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
    if zu_viele_antraege(request.headers.get("X-Forwarded-For",
                                             request.remote_addr or "?")):
        return zurueck("Es sind schon mehrere Antraege von dir eingegangen. "
                       "Bitte warte eine Stunde.")

    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, pw_hash, is_admin, active,"
            " pending, email, phone, note, created_at)"
            " VALUES (?,?,?,0,0,1,?,?,?,?)",
            (formular["username"], formular["display_name"],
             generate_password_hash(passwort), formular["email"][:200],
             formular["phone"][:60], formular["note"][:1000], int(time.time())))
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


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
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
            session.permanent = True
            session["uid"] = row["id"]
            session["pwv"] = row["pw_version"]
            return redirect(url_for("index"))
        return render_template("login.html", error="Benutzername oder Passwort stimmt nicht.")
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
        "name": "Chat",
        "short_name": "Chat",
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
               "is_admin": bool(me["is_admin"]), "avatar": me["avatar"]},
        "rooms": payload,
        "users": [dict(u) for u in users],
        "online": online,
    })


@app.get("/api/rooms/<int:room_id>/messages")
@login_required
def api_messages(room_id):
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    before = request.args.get("before", type=int)
    limit = min(request.args.get("limit", 50, type=int), 200)
    if before:
        rows = db().execute(MSG_QUERY + " WHERE m.room_id=? AND m.id<?"
                            " ORDER BY m.id DESC LIMIT ?",
                            (room_id, before, limit)).fetchall()
    else:
        rows = db().execute(MSG_QUERY + " WHERE m.room_id=?"
                            " ORDER BY m.id DESC LIMIT ?",
                            (room_id, limit)).fetchall()
    return jsonify([msg_payload(r) for r in reversed(rows)])


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


# Die Farbe gilt nur fuer den, der sie setzt - jeder mag andere Toene, und
# niemand soll sie den anderen aufdraengen.
FARBEN = {"#1f4a48", "#3b4a6b", "#4a3b5c", "#5c4030", "#2f5136", "#5c3040",
          "#334a5c", "#4a4a2f"}


@app.post("/api/rooms/<int:room_id>/color")
@login_required
def api_set_room_color(room_id):
    uid = session["uid"]
    if not is_member(room_id, uid):
        abort(403)
    farbe = (request.get_json(force=True).get("color") or "").strip().lower()
    if farbe and farbe not in FARBEN:
        return jsonify({"error": "Diese Farbe steht nicht zur Auswahl."}), 400
    db().execute("UPDATE room_members SET color=? WHERE room_id=? AND user_id=?",
                 (farbe or None, room_id, uid))
    db().commit()
    return jsonify({"color": farbe or None})


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
# Medien
# --------------------------------------------------------------------------
def datei_aufraeumen(conn, file_id):
    """Datensatz und Blob entfernen, sofern keine Nachricht mehr daran haengt."""
    noch_benutzt = conn.execute(
        "SELECT 1 FROM messages WHERE file_id=?", (file_id,)).fetchone()
    if noch_benutzt:
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
    return jsonify([{
        "id": r["id"],
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


@app.delete("/api/media/<int:file_id>")
@login_required
def api_delete_media(file_id):
    """Datei entfernen - aus dem Verlauf und von der Platte.

    Die zugehoerige Nachricht wird wie beim Loeschen einer Nachricht als
    geloescht markiert, damit im Verlauf kein leerer Platz entsteht.
    """
    me = current_user()
    conn = db()
    row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Diese Datei gibt es nicht."}), 404

    nachrichten = conn.execute(
        "SELECT m.id, m.room_id FROM messages m"
        " JOIN room_members rm ON rm.room_id=m.room_id AND rm.user_id=?"
        " WHERE m.file_id=?", (me["id"], file_id)).fetchall()
    if not nachrichten and row["user_id"] != me["id"]:
        return jsonify({"error": "Diese Datei gibt es nicht."}), 404
    if row["user_id"] != me["id"] and not me["is_admin"]:
        return jsonify({"error": "Fremde Dateien darf nur ein Administrator "
                                 "loeschen."}), 403

    conn.execute("UPDATE messages SET deleted=1, body='', file_id=NULL"
                 " WHERE file_id=?", (file_id,))
    conn.commit()
    datei_aufraeumen(conn, file_id)

    for n in nachrichten:
        socketio.emit("message_deleted", {"id": n["id"], "room_id": n["room_id"]},
                      to=f"room:{n['room_id']}")
    return jsonify({"ok": True})


@app.post("/api/push/subscribe")
@login_required
def api_push_subscribe():
    sub = request.get_json(force=True)
    keys = sub.get("keys", {})
    try:
        db().execute(
            "INSERT OR REPLACE INTO push_subs (user_id, endpoint, p256dh, auth, created_at)"
            " VALUES (?,?,?,?,?)",
            (session["uid"], sub["endpoint"], keys["p256dh"], keys["auth"],
             int(time.time())))
        db().commit()
    except (KeyError, sqlite3.Error) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


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
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else request.args.get("token", "")
    if not token or not secrets.compare_digest(token, API_TOKEN):
        return jsonify({"error": "Token ungueltig."}), 401

    data = request.get_json(force=True, silent=True) or request.form
    target = (data.get("room") or "").strip()
    text = (data.get("message") or "").strip()
    # Aus einer rest_command-Vorlage kommt oft der Text "true" statt eines
    # echten Wahrheitswerts.
    immer = str(data.get("always", "")).strip().lower() in ("1", "true", "ja",
                                                            "yes", "on")
    if not target or not text:
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
            return jsonify({"error": f"Weder Gruppe noch Person mit dem Namen "
                                     f"'{target}' gefunden."}), 404
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
    return jsonify({"ok": True, "room_id": room["id"],
                    "message_id": payload["id"], "pushed": len(empfaenger)})


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": f"Die Datei ist groesser als {MAX_UPLOAD_MB} MB."}), 413


# --------------------------------------------------------------------------
# Socket.IO
# --------------------------------------------------------------------------
@socketio.on("connect")
def on_connect():
    uid = session.get("uid")
    if not uid:
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
        socketio.emit("presence", {"user_id": uid, "online": False})


@socketio.on("typing")
def on_typing(data):
    uid = session.get("uid")
    if not uid:
        return
    room_id = int(data.get("room_id", 0))
    emit("typing", {"room_id": room_id, "user_id": uid,
                    "name": data.get("name", "")},
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
    if not body and not file_id:
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
        "INSERT INTO messages (room_id, user_id, body, file_id, reply_to, created_at)"
        " VALUES (?,?,?,?,?,?)", (room_id, uid, body[:8000], file_id, reply_to, now))
    msg_id = cur.lastrowid
    conn.execute("UPDATE room_members SET last_read=? WHERE room_id=? AND user_id=?",
                 (msg_id, room_id, uid))
    conn.commit()

    row = conn.execute(MSG_QUERY + " WHERE m.id=?", (msg_id,)).fetchone()
    payload = msg_payload(row)
    room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    members = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM room_members WHERE room_id=?", (room_id,)).fetchall()]
    conn.close()

    socketio.emit("message", payload, to=f"room:{room_id}")

    with ONLINE_LOCK:
        offline = [m for m in members if m != uid and m not in ONLINE]
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


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8099, allow_unsafe_werkzeug=True)
