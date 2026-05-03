"""
Резервное копирование БД.
Локальный бэкап всегда доступен.
Dropbox и Google Drive — опционально (нужны токены в .env).
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import Tuple

from config import DB_PATH, DROPBOX_TOKEN, GDRIVE_CREDS_JSON, GDRIVE_FOLDER_ID
from logger import get_logger

logger = get_logger()

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

def local_backup() -> str:
    """Копирует БД в папку backups/ с меткой времени. Возвращает путь."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"icloud_monitor_{ts}.db"
    shutil.copy2(DB_PATH, dest)
    logger.info(f"Локальный бэкап: {dest}")
    return str(dest)

def backup_to_dropbox() -> Tuple[bool, str]:
    """Загружает БД в Dropbox. Возвращает (успех, сообщение)."""
    if not DROPBOX_TOKEN:
        return False, "DROPBOX_TOKEN не задан в .env"
    try:
        import dropbox
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
        remote_path = (
            f"/icloud-monitor/icloud_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        )
        with open(DB_PATH, "rb") as f:
            dbx.files_upload(
                f.read(), remote_path, mode=dropbox.files.WriteMode.overwrite
            )
        logger.info(f"Dropbox бэкап: {remote_path}")
        return True, f"Загружено в Dropbox: {remote_path}"
    except ImportError:
        return False, "Установите пакет dropbox: pip install dropbox"
    except Exception as e:
        logger.error(f"Dropbox ошибка: {e}")
        return False, str(e)

def backup_to_gdrive() -> Tuple[bool, str]:
    """Загружает БД в Google Drive. Возвращает (успех, сообщение)."""
    if not GDRIVE_FOLDER_ID:
        return False, "GDRIVE_FOLDER_ID не задан в .env"
    if not Path(GDRIVE_CREDS_JSON).exists():
        return False, f"Файл {GDRIVE_CREDS_JSON} не найден"
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            GDRIVE_CREDS_JSON,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)
        fname = f"icloud_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        meta = {"name": fname, "parents": [GDRIVE_FOLDER_ID]}
        media = MediaFileUpload(DB_PATH, mimetype="application/octet-stream", resumable=True)
        result = service.files().create(body=meta, media_body=media, fields="id").execute()
        logger.info(f"Google Drive бэкап: file_id={result['id']}")
        return True, f"Загружено в Google Drive (ID: {result['id']})"
    except ImportError:
        return False, "Установите: pip install google-api-python-client google-auth"
    except Exception as e:
        logger.error(f"Google Drive ошибка: {e}")
        return False, str(e)
