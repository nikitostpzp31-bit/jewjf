import sqlite3
import os
import base64

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
_KEY = b"apple_bot_key_2026"

def _xor(data: str) -> str:
    enc = [c ^ _KEY[i % len(_KEY)] for i, c in enumerate(data.encode())]
    return base64.b64encode(bytes(enc)).decode()

def _dxor(data: str) -> str:
    try:
        raw = base64.b64decode(data.encode())
        return bytes(c ^ _KEY[i % len(_KEY)] for i, c in enumerate(raw)).decode()
    except:
        return data

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS known_devices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier  TEXT UNIQUE NOT NULL,
            model       TEXT,
            imei        TEXT,
            first_seen  TEXT DEFAULT (datetime('now')),
            last_seen   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS device_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            event     TEXT NOT NULL,
            details   TEXT,
            ts        TEXT DEFAULT (datetime('now'))
        );
        """)
        conn.commit()
    print("[db] initialized", flush=True)

def set_config(key: str, value: str, encrypt: bool = False):
    v = _xor(value) if encrypt else value
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, v))
        conn.commit()

def get_config(key: str, decrypt: bool = False):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        if row:
            return _dxor(row["value"]) if decrypt else row["value"]
    return None

def is_setup_complete() -> bool:
    required = ["email", "password", "q1_text", "q1_answer", "q2_text", "q2_answer"]
    for k in required:
        if not get_config(k):
            return False
    return True

def get_all_config() -> dict:
    return {
        "email": get_config("email"),
        "password": get_config("password", decrypt=True),
        "q1_text": get_config("q1_text"),
        "q1_answer": get_config("q1_answer"),
        "q2_text": get_config("q2_text"),
        "q2_answer": get_config("q2_answer"),
        "q3_text": get_config("q3_text") or "",
        "q3_answer": get_config("q3_answer") or "",
    }

def save_known_devices(devices: list):
    with get_conn() as conn:
        for d in devices:
            ident = d.get("imei") or d.get("model", "") + d.get("description", "")
            if not ident:
                continue
            conn.execute("""
                INSERT INTO known_devices (identifier, model, imei)
                VALUES (?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    last_seen = datetime('now'),
                    model = excluded.model
            """, (ident, d.get("model", ""), d.get("imei", "")))
        conn.commit()

def get_known_device_ids() -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT identifier FROM known_devices").fetchall()
        return {r["identifier"] for r in rows}

def find_new_devices(devices: list) -> list:
    known = get_known_device_ids()
    new_ones = []
    for d in devices:
        ident = d.get("imei") or d.get("model", "") + d.get("description", "")
        if ident and ident not in known:
            new_ones.append(d)
    return new_ones

def log_event(event: str, details: str = ""):
    with get_conn() as conn:
        conn.execute("INSERT INTO device_log (event, details) VALUES (?, ?)", (event, details))
        conn.commit()
