"""Local bootstrap store: single owner, hashed sessions and runtime configuration."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
COOKIE = "merasys_session"
SESSION_SECONDS = 12 * 3600


@contextmanager
def database():
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    path = STATE_DIR / "control.sqlite3"
    connection = sqlite3.connect(path, timeout=15)
    os.chmod(path, 0o600)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    with database() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS owner (
          id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS configuration (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_failures (address TEXT PRIMARY KEY, count INTEGER NOT NULL, since REAL NOT NULL);
        """)


def registered():
    with database() as connection:
        return connection.execute("SELECT 1 FROM owner WHERE id=1").fetchone() is not None


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=5, maxmem=64*1024*1024).hex()
    return f"scrypt${salt}${digest}"


def matches_password(password, encoded):
    try:
        algorithm, salt, _ = encoded.split("$")
        return algorithm == "scrypt" and hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def register(username, password):
    encoded = hash_password(password)
    with database() as connection:
        # CHECK(id=1) + PK is authoritative even when two requests race.
        connection.execute("INSERT INTO owner VALUES (1, ?, ?)", (username, encoded))


def check_login(username, password):
    with database() as connection:
        owner = connection.execute("SELECT * FROM owner WHERE id=1").fetchone()
    if owner is None:
        return False
    valid = matches_password(password, owner["password_hash"])
    return valid and hmac.compare_digest(username.casefold().encode(), owner["username"].casefold().encode())


def allow_login_attempt(address):
    stamp = time.time()
    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM login_failures WHERE since < ?", (stamp - 900,))
        row = connection.execute("SELECT * FROM login_failures WHERE address=?", (address,)).fetchone()
        if row and row["count"] >= 5:
            return False
        connection.execute("INSERT INTO login_failures VALUES (?, 1, ?) ON CONFLICT(address) DO UPDATE SET count=count+1", (address, stamp))
    return True


def login_result(address, success):
    stamp = time.time()
    with database() as connection:
        connection.execute("DELETE FROM login_failures WHERE since < ?", (stamp - 900,))
        if success:
            connection.execute("DELETE FROM login_failures WHERE address=?", (address,))


def new_session():
    token = secrets.token_urlsafe(48)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with database() as connection:
        connection.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        connection.execute("INSERT INTO sessions VALUES (?, ?)", (digest, time.time() + SESSION_SECONDS))
        connection.execute("DELETE FROM sessions WHERE digest NOT IN (SELECT digest FROM sessions ORDER BY expires DESC LIMIT 10)")
    return token


def authenticated(token):
    if not token or len(token) > 200:
        return False
    with database() as connection:
        row = connection.execute("SELECT expires FROM sessions WHERE digest=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    return bool(row and row["expires"] > time.time())


def logout(token):
    with database() as connection:
        connection.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256(token.encode()).hexdigest(),))


def configuration():
    with database() as connection:
        row = connection.execute("SELECT data FROM configuration WHERE id=1").fetchone()
    return json.loads(row["data"]) if row else {}


def save_configuration(values, expected):
    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT data FROM configuration WHERE id=1").fetchone()
        current = json.loads(row["data"]) if row else {}
        if current != expected:
            raise ValueError("Cấu hình vừa được thay đổi ở thao tác khác; tải lại cấu hình rồi lưu lại")
        connection.execute("INSERT INTO configuration VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (json.dumps(values, ensure_ascii=False),))


def assign_agent_token(host, token, replace):
    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT data FROM configuration WHERE id=1").fetchone()
        config = json.loads(row["data"]) if row else {}
        tokens = dict(config.get("agent_tokens", {}))
        if host in tokens and not replace:
            raise ValueError("IP đã có token; cần xác nhận thay token")
        if host not in tokens and len(tokens) >= 1000:
            raise ValueError("Chỉ cho phép tối đa 1000 token agent")
        tokens[host] = token
        config["agent_tokens"] = tokens
        connection.execute("INSERT INTO configuration VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (json.dumps(config, ensure_ascii=False),))


def change_password(current, new):
    with database() as connection:
        owner = connection.execute("SELECT password_hash FROM owner WHERE id=1").fetchone()
    if not owner or not matches_password(current, owner["password_hash"]):
        return False
    with database() as connection:
        connection.execute("UPDATE owner SET password_hash=? WHERE id=1", (hash_password(new),))
        connection.execute("DELETE FROM sessions")
    return True


def reset_password(new):
    with database() as connection:
        if not connection.execute("SELECT 1 FROM owner WHERE id=1").fetchone():
            raise ValueError("Chưa có tài khoản; mở web để đăng ký")
        connection.execute("UPDATE owner SET password_hash=? WHERE id=1", (hash_password(new),))
        connection.execute("DELETE FROM sessions")
        connection.execute("DELETE FROM login_failures")
