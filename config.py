"""
Конфигурация из переменных окружения (.env) и config.yaml.
"""
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# Загружаем config.yaml
CONFIG_PATH = Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    RAW_CONFIG = yaml.safe_load(f)

# Функция для подстановки переменных окружения
def substitute_env_vars(value):
    """Подставляет переменные окружения в строках (${VAR_NAME})."""
    if isinstance(value, str):
        pattern = r'\$\{([^}]+)\}'
        return re.sub(pattern, lambda m: os.getenv(m.group(1), m.group(0)), value)
    return value

# Bot configuration
BOT_CONFIG = RAW_CONFIG.get("bot", {})
TELEGRAM_TOKEN: str = substitute_env_vars(BOT_CONFIG.get("token", os.getenv("BOT_TOKEN", "")))
OWNER_TELEGRAM_ID: int = int(substitute_env_vars(str(BOT_CONFIG.get("admin_id", os.getenv("ADMIN_ID", "0")))))
SECRET_PHRASE: str = substitute_env_vars(BOT_CONFIG.get("secret_phrase", os.getenv("SECRET_PHRASE", "")))

# Security configuration
SECURITY_CONFIG = RAW_CONFIG.get("security", {})
FERNET_KEY: str = substitute_env_vars(SECURITY_CONFIG.get("fernet_key", os.getenv("FERNET_KEY", "")))
ENCRYPTION_ENABLED: bool = SECURITY_CONFIG.get("encryption_enabled", True)
MAX_LOGIN_ATTEMPTS: int = SECURITY_CONFIG.get("max_login_attempts", 5)
SESSION_TIMEOUT: int = SECURITY_CONFIG.get("session_timeout", 3600)

# Database configuration
DB_CONFIG = RAW_CONFIG.get("database", {})
DB_PATH: str = DB_CONFIG.get("path", "data/bot.db")
BACKUP_ENABLED: bool = DB_CONFIG.get("backup_enabled", True)
BACKUP_INTERVAL: int = DB_CONFIG.get("backup_interval", 86400)

# Scheduler configuration
SCHEDULER_CONFIG = RAW_CONFIG.get("scheduler", {})
CHECK_INTERVAL: int = SCHEDULER_CONFIG.get("check_interval", 300)
NOTIFICATION_ENABLED: bool = SCHEDULER_CONFIG.get("notification_enabled", True)
RETRY_ATTEMPTS: int = SCHEDULER_CONFIG.get("retry_attempts", 3)
RETRY_DELAY: int = SCHEDULER_CONFIG.get("retry_delay", 60)

# iCloud configuration
ICLOUD_CONFIG = RAW_CONFIG.get("icloud", {})
ICLOUD_ENABLED: bool = ICLOUD_CONFIG.get("enabled", True)
USE_PLAYWRIGHT: bool = ICLOUD_CONFIG.get("use_playwright", True)
FALLBACK_SELENIUM: bool = ICLOUD_CONFIG.get("fallback_selenium", True)
HEADLESS: bool = ICLOUD_CONFIG.get("headless", True)
TIMEOUT: int = ICLOUD_CONFIG.get("timeout", 30000)
USER_AGENT: str = ICLOUD_CONFIG.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

# Backup configuration
BACKUP_CONFIG = RAW_CONFIG.get("backup", {})
DROPBOX_TOKEN: str = os.getenv("DROPBOX_TOKEN", "")
GDRIVE_CREDS_JSON: str = os.getenv("GDRIVE_CREDS_JSON", "service_account.json")
GDRIVE_FOLDER_ID: str = os.getenv("GDRIVE_FOLDER_ID", "")
LOCAL_BACKUP_PATH: str = BACKUP_CONFIG.get("local_path", "backups/")
MAX_BACKUPS: int = BACKUP_CONFIG.get("max_backups", 10)

# Analytics configuration
ANALYTICS_CONFIG = RAW_CONFIG.get("analytics", {})
ANALYTICS_ENABLED: bool = ANALYTICS_CONFIG.get("enabled", True)
TRACK_COMMANDS: bool = ANALYTICS_CONFIG.get("track_commands", True)
TRACK_ERRORS: bool = ANALYTICS_CONFIG.get("track_errors", True)
REPORT_INTERVAL: int = ANALYTICS_CONFIG.get("report_interval", 604800)

# Logging configuration
LOGGING_CONFIG = RAW_CONFIG.get("logging", {})
LOG_LEVEL: str = LOGGING_CONFIG.get("level", "INFO")
LOG_PATH: str = LOGGING_CONFIG.get("file", "logs/bot.log")
LOG_MAX_SIZE: int = LOGGING_CONFIG.get("max_size", 10485760)
LOG_BACKUP_COUNT: int = LOGGING_CONFIG.get("backup_count", 5)
LOG_FORMAT: str = LOGGING_CONFIG.get("format", "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# Messages configuration
MESSAGES_CONFIG = RAW_CONFIG.get("messages", {})
MSG_WELCOME: str = MESSAGES_CONFIG.get("welcome", "Добро пожаловать!")
MSG_UNAUTHORIZED: str = MESSAGES_CONFIG.get("unauthorized", "Доступ запрещен.")
MSG_VERIFIED: str = MESSAGES_CONFIG.get("verified", "Верификация успешна!")
MSG_ERROR: str = MESSAGES_CONFIG.get("error", "Произошла ошибка.")

# Features configuration
FEATURES_CONFIG = RAW_CONFIG.get("features", {})
FEATURE_FIND_MY_IPHONE: bool = FEATURES_CONFIG.get("find_my_iphone", True)
FEATURE_DEVICE_TRACKING: bool = FEATURES_CONFIG.get("device_tracking", True)
FEATURE_LOCATION_HISTORY: bool = FEATURES_CONFIG.get("location_history", True)
FEATURE_NOTIFICATIONS: bool = FEATURES_CONFIG.get("notifications", True)
FEATURE_AUTO_BACKUP: bool = FEATURES_CONFIG.get("auto_backup", True)
