"""
Логгер на базе loguru. Пишет в файл и stdout.
"""
import sys
from pathlib import Path

from loguru import logger as _logger

from config import LOG_PATH

_configured = False

def _configure() -> None:
    global _configured
    if _configured:
        return
    _logger.remove()
    _logger.add(sys.stdout, colorize=True, format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}")
    _logger.add(
        LOG_PATH,
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
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
