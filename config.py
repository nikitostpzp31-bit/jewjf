"""
Конфигурация из переменных окружения (.env).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
OWNER_TELEGRAM_ID: int = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
SECRET_PHRASE: str = os.getenv("SECRET_PHRASE", "change_this_to_your_secret")
FERNET_KEY: str = os.getenv("FERNET_KEY", "")

DB_PATH: str = os.getenv("DB_PATH", "icloud_monitor.db")
LOG_PATH: str = os.getenv("LOG_PATH", "icloud_monitor.log")

DROPBOX_TOKEN: str = os.getenv("DROPBOX_TOKEN", "")
GDRIVE_CREDS_JSON: str = os.getenv("GDRIVE_CREDS_JSON", "service_account.json")
GDRIVE_FOLDER_ID: str = os.getenv("GDRIVE_FOLDER_ID", "")
