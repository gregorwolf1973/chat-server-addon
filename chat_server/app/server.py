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
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY,
    name TEXT,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS room_members (
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    last_read INTEGER NOT NULL DEFAULT 0,
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


def migrate(conn):
    """Fehlende Spalten aelterer Installationen nachziehen."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
    if "reply_to" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN reply_to INTEGER")
    if "deleted" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def load_api_token():
    """Token fuer die Home-Assistant-Schnittstelle - aus Option oder /data."""
    configured = _opt("API_TOKEN")
    if configured:
        return configured
    if os.path.exists(TOKEN_PATH):
        return open(TOKEN_PATH).read().strip()
    token = secrets.token_urlsafe(32)
    with open(TOKEN_PATH, "w") as fh:
        fh.write(token)
    os.chmod(TOKEN_PATH, 0o600)
    return token


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
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
log.info("Token fuer die Home-Assistant-Schnittstelle: %s", API_TOKEN)

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
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "nicht angemeldet"}), 401
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper


def is_member(room_id, user_id):
    return db().execute(
        "SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",
        (room_id, user_id)).fetchone() is not None


def room_payload(room, uid, conn=None):
    conn = conn or db()
    members = conn.execute(
        "SELECT u.id, u.display_name FROM room_members m"
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
    last_read = conn.execute(
        "SELECT last_read FROM room_members WHERE room_id=? AND user_id=?",
        (room["id"], uid)).fetchone()
    unread = conn.execute(
        "SELECT COUNT(*) c FROM messages WHERE room_id=? AND id>? AND user_id<>?",
        (room["id"], last_read["last_read"] if last_read else 0, uid)).fetchone()["c"]
    with ONLINE_LOCK:
        online = [m["id"] for m in members if m["id"] in ONLINE]
    return {
        "id": room["id"],
        "name": name,
        "is_group": bool(room["is_group"]),
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
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        row = db().execute("SELECT * FROM users WHERE username=?",
                           (username,)).fetchone()
        if row and check_password_hash(row["pw_hash"], password):
            session.permanent = True
            session["uid"] = row["id"]
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
    conn = db()
    rooms = conn.execute(
        "SELECT r.* FROM rooms r JOIN room_members m ON m.room_id=r.id"
        " WHERE m.user_id=?", (uid,)).fetchall()
    users = conn.execute(
        "SELECT id, username, display_name, is_admin FROM users ORDER BY display_name"
    ).fetchall()
    with ONLINE_LOCK:
        online = list(ONLINE.keys())
    payload = [room_payload(r, uid, conn) for r in rooms]
    payload.sort(key=lambda r: (r["last"]["at"] if r["last"] else 0), reverse=True)
    return jsonify({
        "me": {"id": uid, "name": current_user()["display_name"],
               "is_admin": bool(current_user()["is_admin"])},
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


@app.post("/api/users")
@login_required
def api_create_user():
    me = current_user()
    if not me["is_admin"]:
        return jsonify({"error": "Nur Administratoren legen Konten an."}), 403
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    display = (data.get("display_name") or username).strip()
    password = data.get("password") or ""
    if not username or len(password) < 6:
        return jsonify({"error": "Benutzername fehlt oder Passwort ist zu kurz (min. 6 Zeichen)."}), 400
    try:
        db().execute(
            "INSERT INTO users (username, display_name, pw_hash, is_admin, created_at)"
            " VALUES (?,?,?,?,?)",
            (username, display, generate_password_hash(password),
             1 if data.get("is_admin") else 0, int(time.time())))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Diesen Benutzernamen gibt es schon."}), 400
    return jsonify({"ok": True})


@app.post("/api/me/password")
@login_required
def api_change_password():
    data = request.get_json(force=True)
    new = data.get("new") or ""
    me = current_user()
    if not check_password_hash(me["pw_hash"], data.get("old") or ""):
        return jsonify({"error": "Das aktuelle Passwort stimmt nicht."}), 400
    if len(new) < 6:
        return jsonify({"error": "Das neue Passwort braucht mindestens 6 Zeichen."}), 400
    db().execute("UPDATE users SET pw_hash=? WHERE id=?",
                 (generate_password_hash(new), me["id"]))
    db().commit()
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
    cur = db().execute(
        "INSERT INTO files (stored_name, orig_name, mime, size, user_id, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (stored, secure_filename(file.filename), file.mimetype, size,
         session["uid"], int(time.time())))
    db().commit()
    return jsonify({"id": cur.lastrowid, "name": file.filename,
                    "mime": file.mimetype, "size": size})


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
    return send_file(os.path.join(UPLOAD_DIR, row["stored_name"]),
                     mimetype=row["mime"] or "application/octet-stream",
                     download_name=row["orig_name"],
                     as_attachment=request.args.get("dl") == "1")


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
    if not target or not text:
        return jsonify({"error": "room und message werden gebraucht."}), 400

    conn = db()
    bot = conn.execute("SELECT * FROM users WHERE username=?", (BOT_USERNAME,)).fetchone()
    room = conn.execute("SELECT * FROM rooms WHERE name=? AND is_group=1",
                        (target,)).fetchone()
    now = int(time.time())

    if room is None:
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR display_name=?",
            (target.lower(), target)).fetchone()
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
    with ONLINE_LOCK:
        offline = [m for m in members if m != bot["id"] and m not in ONLINE]
    url = f"{EXTERNAL_URL}/?room={room['id']}" if EXTERNAL_URL else "/"
    push_to_users(offline, "Home Assistant", text[:180], url)
    return jsonify({"ok": True, "room_id": room["id"], "message_id": payload["id"]})


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
    with ONLINE_LOCK:
        ONLINE[uid] = ONLINE.get(uid, 0) + 1
        first = ONLINE[uid] == 1
    join_room(f"user:{uid}")
    conn = raw_db()
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
        return
    room_id = int(data.get("room_id", 0))
    body = (data.get("body") or "").strip()
    file_id = data.get("file_id")
    reply_to = data.get("reply_to")
    if not body and not file_id:
        return

    conn = raw_db()
    member = conn.execute("SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",
                          (room_id, uid)).fetchone()
    if not member:
        conn.close()
        return
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
    url = f"{EXTERNAL_URL}/?room={room_id}" if EXTERNAL_URL else "/"
    push_to_users(offline, title, text[:180], url)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8099, allow_unsafe_werkzeug=True)
