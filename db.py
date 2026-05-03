"""
Работа с SQLite. Единая схема для всего проекта.
Пароли хранятся зашифрованными (Fernet).
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from config import DB_PATH, FERNET_KEY
from logger import get_logger

logger = get_logger()

# ---------------------------------------------------------------------------
# Шифрование
# ---------------------------------------------------------------------------

def _get_fernet() -> Optional[Fernet]:
    if not FERNET_KEY:
        return None
    try:
        return Fernet(FERNET_KEY.encode())
    except Exception:
        return None

def _encrypt(value: str) -> str:
    f = _get_fernet()
    if f is None:
        return value
    return f.encrypt(value.encode()).decode()

def _decrypt(value: str) -> str:
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        return value

# ---------------------------------------------------------------------------
# Соединение
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Инициализация схемы
# ---------------------------------------------------------------------------

def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                birthdate TEXT,
                last_login TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS secret_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                answer TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                device_id TEXT,
                name TEXT,
                model TEXT,
                version TEXT,
                imei TEXT,
                status TEXT,
                battery INTEGER,
                is_lost INTEGER DEFAULT 0,
                location TEXT,
                last_seen TEXT,
                extra TEXT
            );

            CREATE TABLE IF NOT EXISTS mails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                uid TEXT,
                date TEXT,
                sender TEXT,
                subject TEXT,
                body TEXT,
                is_apple_event INTEGER DEFAULT 0,
                is_2fa_alert INTEGER DEFAULT 0,
                fetched_at TEXT DEFAULT (datetime('now')),
                UNIQUE(account_id, uid)
            );

            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                result TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS known_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                model TEXT,
                imei TEXT,
                first_seen TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now')),
                UNIQUE(account_id, name)
            );
        """)
    logger.info("БД инициализирована")

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def add_account(email: str, password: str, birthdate: str = "") -> int:
    enc_pwd = _encrypt(password)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO accounts (email, password, birthdate) VALUES (?, ?, ?)",
            (email.lower(), enc_pwd, birthdate),
        )
        return cur.lastrowid

def get_all_accounts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["password"] = _decrypt(d["password"])
            result.append(d)
        return result

def get_account_by_id(acc_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id=?", (acc_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["password"] = _decrypt(d["password"])
        return d

def update_account_password(acc_id: int, new_password: str) -> None:
    enc = _encrypt(new_password)
    with get_conn() as conn:
        conn.execute("UPDATE accounts SET password=? WHERE id=?", (enc, acc_id))

def update_last_login(acc_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE accounts SET last_login=? WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), acc_id),
        )

def delete_account(acc_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM accounts WHERE id=?", (acc_id,))

# ---------------------------------------------------------------------------
# Secret questions
# ---------------------------------------------------------------------------

def set_secret_questions(acc_id: int, questions: list[tuple[str, str]]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM secret_questions WHERE account_id=?", (acc_id,))
        conn.executemany(
            "INSERT INTO secret_questions (account_id, question, answer) VALUES (?, ?, ?)",
            [(acc_id, q, a) for q, a in questions],
        )

def get_secret_questions(acc_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM secret_questions WHERE account_id=?", (acc_id,)
        ).fetchall()
        return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def upsert_device(acc_id: int, device: dict) -> None:
    device_id = device.get("device_id") or device.get("id", "")
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM devices WHERE account_id=? AND device_id=?",
            (acc_id, device_id),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE devices SET name=?, model=?, version=?, imei=?,
                    status=?, battery=?, location=?, last_seen=?, extra=?
                    WHERE account_id=? AND device_id=?""",
                (
                    device.get("name"), device.get("model"), device.get("version"),
                    device.get("imei"), device.get("status"), device.get("battery"),
                    device.get("location"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    device.get("extra"), acc_id, device_id,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO devices
                    (account_id, device_id, name, model, version, imei, status, battery, location, last_seen, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    acc_id, device_id, device.get("name"), device.get("model"),
                    device.get("version"), device.get("imei"), device.get("status"),
                    device.get("battery"), device.get("location"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), device.get("extra"),
                ),
            )

def get_devices(acc_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM devices WHERE account_id=? ORDER BY id", (acc_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_all_devices() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
        return [dict(r) for r in rows]

def set_device_lost(device_id: str, is_lost: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE devices SET is_lost=? WHERE device_id=?", (is_lost, device_id)
        )

# ---------------------------------------------------------------------------
# Mails
# ---------------------------------------------------------------------------

_APPLE_SENDERS = ("apple.com", "id.apple.com", "appleid.apple.com")
_APPLE_SUBJECTS = ("apple id", "icloud", "find my", "your apple", "sign in", "verification")

def is_apple_event(sender: str, subject: str) -> bool:
    return _is_apple_event(sender, subject)

def _is_apple_event(sender: str, subject: str) -> bool:
    s = (sender or "").lower()
    sub = (subject or "").lower()
    return any(d in s for d in _APPLE_SENDERS) or any(k in sub for k in _APPLE_SUBJECTS)

def save_mail(acc_id: int, uid: str, date: str, sender: str, subject: str, body: str,
              is_2fa: bool = False) -> bool:
    """Сохраняет письмо. Возвращает True если новое."""
    apple = 1 if _is_apple_event(sender, subject) else 0
    tfa = 1 if is_2fa else 0
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM mails WHERE account_id=? AND uid=?", (acc_id, uid)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            """INSERT INTO mails (account_id, uid, date, sender, subject, body, is_apple_event, is_2fa_alert)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (acc_id, uid, date, sender, subject, body, apple, tfa),
        )
        return True

def get_mails(acc_id: int, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mails WHERE account_id=? ORDER BY date DESC LIMIT ?",
            (acc_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

def get_all_mails(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mails ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------

def log_action(acc_id: Optional[int], action: str, details: str = "", result: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO action_log (account_id, action, details, result) VALUES (?, ?, ?, ?)",
            (acc_id, action, details, result),
        )

def get_actions(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    with get_conn() as conn:
        accounts = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        lost = conn.execute("SELECT COUNT(*) FROM devices WHERE is_lost=1").fetchone()[0]
        mails = conn.execute("SELECT COUNT(*) FROM mails").fetchone()[0]
        apple_events = conn.execute(
            "SELECT COUNT(*) FROM mails WHERE is_apple_event=1"
        ).fetchone()[0]
        tfa_alerts = conn.execute(
            "SELECT COUNT(*) FROM mails WHERE is_2fa_alert=1"
        ).fetchone()[0]
        return {
            "accounts": accounts,
            "devices": devices,
            "lost_devices": lost,
            "mails": mails,
            "apple_events": apple_events,
            "tfa_alerts": tfa_alerts,
        }

def get_last_check_time() -> Optional[str]:
    """Возвращает время последней проверки почты."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(fetched_at) FROM mails"
        ).fetchone()
        return row[0] if row else None

# ---------------------------------------------------------------------------
# Bot config (setup: email, password, security questions, flags)
# ---------------------------------------------------------------------------

def set_config(key: str, value: str) -> None:
    enc = _encrypt(value)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO bot_config(key,value,updated_at) VALUES(?,?,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, enc),
        )

def get_config(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM bot_config WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        return _decrypt(row[0])

def get_setup() -> dict:
    """Возвращает полный setup-конфиг бота."""
    return {
        "email": get_config("email"),
        "password": get_config("password"),
        "q1_text": get_config("q1_text"),
        "q1_answer": get_config("q1_answer"),
        "q2_text": get_config("q2_text"),
        "q2_answer": get_config("q2_answer"),
        "q3_text": get_config("q3_text"),
        "q3_answer": get_config("q3_answer"),
        "autoprotect": get_config("autoprotect", "off"),
        "monitor": get_config("monitor", "off"),
    }

def is_setup_complete() -> bool:
    s = get_setup()
    return bool(s["email"] and s["password"])

# ---------------------------------------------------------------------------
# Known devices (для обнаружения новых)
# ---------------------------------------------------------------------------

def get_known_devices(acc_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM known_devices WHERE account_id=? ORDER BY first_seen",
            (acc_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def save_known_device(acc_id: int, name: str, model: str = "", imei: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO known_devices(account_id,name,model,imei,last_seen) VALUES(?,?,?,?,datetime('now')) "
            "ON CONFLICT(account_id,name) DO UPDATE SET last_seen=datetime('now'), "
            "model=COALESCE(NULLIF(excluded.model,''),model), "
            "imei=COALESCE(NULLIF(excluded.imei,''),imei)",
            (acc_id, name, model, imei),
        )

def clear_known_devices(acc_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM known_devices WHERE account_id=?", (acc_id,))

def find_new_devices(acc_id: int, current_devices: list[dict]) -> list[dict]:
    """Сравнивает текущий список с известными. Возвращает новые устройства."""
    known = {d["name"].lower() for d in get_known_devices(acc_id)}
    new_devs = []
    for dev in current_devices:
        name = (dev.get("name") or "").strip()
        if name and name.lower() not in known:
            new_devs.append(dev)
    return new_devs
