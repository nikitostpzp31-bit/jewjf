"""
Аналитика и экспорт данных. Работает с единой схемой db.py.
"""
from pathlib import Path

import db
from logger import get_logger

logger = get_logger()

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

def summary_report() -> list[tuple[str, int]]:
    """Возвращает список (модель_устройства, количество)."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT COALESCE(model, 'Unknown'), COUNT(*) FROM devices GROUP BY model"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

def plot_devices_pie(output: str = "exports/devices_pie.png") -> str | None:
    """Строит круговую диаграмму устройств. Возвращает путь к файлу или None."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # без GUI
        import matplotlib.pyplot as plt

        stat = summary_report()
        if not stat:
            return None

        labels, sizes = zip(*stat)
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140)
        ax.set_title("Распределение устройств по моделям")
        fig.tight_layout()
        fig.savefig(output, dpi=100)
        plt.close(fig)
        logger.info(f"График сохранён: {output}")
        return output
    except Exception as e:
        logger.error(f"Ошибка построения графика: {e}")
        return None

def export_csv(filename: str = "exports/devices.csv") -> str:
    """Экспортирует все устройства в CSV. Возвращает путь к файлу."""
    try:
        import pandas as pd

        devices = db.get_all_devices()
        if not devices:
            df = pd.DataFrame(
                columns=["id", "account_id", "name", "model", "status", "battery", "last_seen"]
            )
        else:
            df = pd.DataFrame(devices)
            df = df.drop(columns=["location", "extra"], errors="ignore")

        df.to_csv(filename, index=False, encoding="utf-8-sig")
        logger.info(f"CSV экспортирован: {filename}")
        return filename
    except Exception as e:
        logger.error(f"Ошибка экспорта CSV: {e}")
        return filename

def export_mails_csv(filename: str = "exports/mails.csv") -> str:
    """Экспортирует письма в CSV (без тел писем)."""
    try:
        import pandas as pd

        mails = db.get_all_mails(limit=1000)
        rows = [
            {
                "id": m["id"],
                "account_id": m["account_id"],
                "date": m["date"],
                "sender": m["sender"],
                "subject": m["subject"],
                "is_apple_event": m["is_apple_event"],
                "is_2fa_alert": m.get("is_2fa_alert", 0),
            }
            for m in mails
        ]
        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        logger.info(f"Письма экспортированы: {filename}")
        return filename
    except Exception as e:
        logger.error(f"Ошибка экспорта писем: {e}")
        return filename
