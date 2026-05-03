"""
Логгер на базе loguru. Пишет в файл и stdout.
"""
import sys
from pathlib import Path

from loguru import logger as _logger

from config import LOG_PATH, LOG_LEVEL, LOG_FORMAT, LOG_MAX_SIZE, LOG_BACKUP_COUNT

_configured = False

def _configure() -> None:
    global _configured
    if _configured:
        return
    _logger.remove()
    _logger.add(sys.stdout, colorize=True, format=LOG_FORMAT, level=LOG_LEVEL)
    _logger.add(
        LOG_PATH,
        rotation=f"{LOG_MAX_SIZE} bytes",
        retention=LOG_BACKUP_COUNT,
        encoding="utf-8",
        format=LOG_FORMAT,
        level=LOG_LEVEL,
    )
    _configured = True

def get_logger():
    _configure()
    return _logger

def get_log_tail(n: int = 50) -> str:
    """Возвращает последние n строк лог-файла."""
    p = Path(LOG_PATH)
    if not p.exists():
        return "(лог пуст)"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])
