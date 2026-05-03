"""
Планировщик фоновых задач:
    - проверка почты каждые 15 минут (IMAP)
    - обновление устройств через Selenium каждые 30 минут
    - мониторинг 2FA-событий с немедленным алертом

IMAP-хосты:
    @icloud.com / @me.com / @mac.com → imap.mail.me.com:993
    @gmail.com → imap.gmail.com:993 (нужен App Password)
    остальные → imap.<domain>:993
"""
import asyncio
import imaplib
import email as email_lib
from email.header import decode_header
from typing import Callable, Optional

import db
from logger import get_logger

logger = get_logger()

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

_ICLOUD_DOMAINS = {"icloud.com", "me.com", "mac.com"}
_IMAP_PORT = 993

# Ключевые слова для немедленного 2FA-алерта
_2FA_KEYWORDS = [
    "two-factor authentication enabled",
    "двухфакторная аутентификация включена",
    "2-factor authentication",
    "sign-in to your apple account",
    "new sign-in to your apple",
    "your apple id was used to sign in",
    "apple id sign in requested",
]

# Флаг паузы мониторинга (управляется через mon_start/mon_stop)
_monitoring_active: bool = True

def set_monitoring(active: bool) -> None:
    global _monitoring_active
    _monitoring_active = active
    logger.info(f"[scheduler] мониторинг {'включён' if active else 'выключен'}")

def is_monitoring_active() -> bool:
    return _monitoring_active

# ---------------------------------------------------------------------------
# Retry-декоратор
# ---------------------------------------------------------------------------

def _retry(n: int = 3, delay: float = 2.0):
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, n + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < n:
                        logger.warning(f"Retry {attempt}/{n} [{fn.__name__}]: {e}")
                        await asyncio.sleep(delay * attempt)
            raise last_exc
        return wrapper
    return decorator

# ---------------------------------------------------------------------------
# Определение IMAP-хоста по email
# ---------------------------------------------------------------------------

def _imap_host(email_addr: str) -> str:
    """Возвращает IMAP-хост для данного email."""
    domain = email_addr.split("@")[-1].lower()
    if domain in _ICLOUD_DOMAINS:
        return "imap.mail.me.com"
    if domain == "gmail.com":
        return "imap.gmail.com"
    return f"imap.{domain}"

# ---------------------------------------------------------------------------
# Декодирование заголовков
# ---------------------------------------------------------------------------

def _decode_str(s) -> str:
    if s is None:
        return ""
    parts = decode_header(s)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)

def _get_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            pass
    return body[:2000]

def _is_2fa_alert(subject: str, body: str) -> bool:
    """Проверяет, является ли письмо уведомлением о включении 2FA."""
    text = (subject + " " + body).lower()
    return any(kw in text for kw in _2FA_KEYWORDS)

# ---------------------------------------------------------------------------
# IMAP: получение писем
# ---------------------------------------------------------------------------

@_retry(3, 2.0)
async def fetch_icloud_mail(acc_id: int, email_addr: str, password: str) -> list[dict]:
    """
    Забирает новые письма через IMAP.
    Для @icloud.com/@me.com/@mac.com использует imap.mail.me.com.
    Возвращает список новых писем.
    """
    host = _imap_host(email_addr)
    logger.info(f"[imap] {email_addr} → {host}")
    loop = asyncio.get_running_loop()

    def _fetch():
        new_mails = []
        imap = imaplib.IMAP4_SSL(host, _IMAP_PORT)
        imap.login(email_addr, password)
        imap.select("INBOX")

        _, data = imap.search(None, "UNSEEN")
        uids = data[0].split()

        for uid in uids[-30:]:  # последние 30 непрочитанных
            try:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                subject = _decode_str(msg.get("Subject", ""))
                sender = _decode_str(msg.get("From", ""))
                date = msg.get("Date", "")
                body = _get_body(msg)
                uid_str = uid.decode()

                is_new = db.save_mail(acc_id, uid_str, date, sender, subject, body)
                if is_new:
                    new_mails.append({
                        "subject": subject,
                        "sender": sender,
                        "date": date,
                        "body": body,
                        "is_2fa": _is_2fa_alert(subject, body),
                    })
            except Exception as e:
                logger.warning(f"[imap] uid={uid} error: {e}")
                continue

        imap.logout()
        return new_mails

    return await loop.run_in_executor(None, _fetch)

async def check_mail_all() -> list[dict]:
    """
    Проверяет почту для всех аккаунтов.
    Возвращает список новых Apple-событий (включая 2FA-алерты).
    """
    accounts = db.get_all_accounts()
    alerts = []
    for acc in accounts:
        try:
            new = await fetch_icloud_mail(acc["id"], acc["email"], acc["password"])
            for m in new:
                if db.is_apple_event(m["sender"], m["subject"]) or m.get("is_2fa"):
                    alerts.append({**m, "email": acc["email"]})
        except Exception as e:
            logger.error(f"[scheduler/mail] {acc['email']}: {e}")
    return alerts

# ---------------------------------------------------------------------------
# Фоновые циклы
# ---------------------------------------------------------------------------

async def _mail_loop(notify_fn: Optional[Callable], interval: int = 900) -> None:
    """Проверяет почту каждые interval секунд. Шлёт алерт при 2FA."""
    while True:
        await asyncio.sleep(interval)
        if not _monitoring_active:
            continue
        try:
            alerts = await check_mail_all()
            if not alerts or not notify_fn:
                continue

            tfa_alerts = [a for a in alerts if a.get("is_2fa")]
            if tfa_alerts:
                for a in tfa_alerts:
                    await notify_fn(
                        f"🚨 <b>ВНИМАНИЕ! Включена 2FA!</b>\n"
                        f"Аккаунт: {a['email']}\n"
                        f"Тема: {a['subject']}\n"
                        f"Дата: {a['date']}"
                    )

            other = [a for a in alerts if not a.get("is_2fa")]
            if other:
                lines = "\n".join(f"🍎 {a['subject']}" for a in other[:5])
                await notify_fn(
                    f"📬 Новых Apple-событий: {len(other)}\n{lines}"
                )
        except Exception as e:
            logger.error(f"[mail_loop] {e}")

async def _devices_loop(notify_fn: Optional[Callable], interval: int = 1800) -> None:
    """
    Обновляет устройства через Selenium каждые interval секунд.
    Уведомляет если появилось новое устройство.
    """
    while True:
        await asyncio.sleep(interval)
        if not _monitoring_active:
            continue
        try:
            accounts = db.get_all_accounts()
            for acc in accounts:
                loop = asyncio.get_running_loop()

                def _do(a=acc):
                    from icloud import apple_login, fetch_devices_findmy
                    driver = apple_login(a["email"], a["password"], a["id"])
                    if not driver:
                        return []
                    devs = fetch_devices_findmy(driver, a["id"])
                    driver.quit()
                    return devs

                try:
                    old_count = len(db.get_devices(acc["id"]))
                    devs = await asyncio.wait_for(
                        loop.run_in_executor(None, _do), timeout=180
                    )
                    new_count = len(devs)
                    if new_count > old_count and notify_fn:
                        await notify_fn(
                            f"📱 <b>Новое устройство!</b>\n"
                            f"Аккаунт: {acc['email']}\n"
                            f"Устройств стало: {new_count} (было {old_count})"
                        )
                    logger.info(f"[devices_loop] {acc['email']}: {new_count} устройств")
                except asyncio.TimeoutError:
                    logger.warning(f"[devices_loop] timeout for {acc['email']}")
                except Exception as e:
                    logger.error(f"[devices_loop] {acc['email']}: {e}")

        except Exception as e:
            logger.error(f"[devices_loop] outer: {e}")

def start_scheduler(notify_fn: Optional[Callable] = None) -> None:
    """Запускает фоновые задачи планировщика."""
    logger.info("Scheduler: почта/15мин, устройства/30мин")
    loop = asyncio.get_running_loop()
    loop.create_task(_mail_loop(notify_fn, interval=900))
    loop.create_task(_devices_loop(notify_fn, interval=1800))
