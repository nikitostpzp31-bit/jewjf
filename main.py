"""
Точка входа. Запуск: python main.py
"""
import asyncio

import db
from bot import create_bot_and_dispatcher, notify_owner
from config import FERNET_KEY, TELEGRAM_TOKEN
from logger import get_logger
from scheduler import start_scheduler

logger = get_logger()

def _ensure_fernet_key() -> None:
    """Генерирует FERNET_KEY если не задан и выводит его для .env."""
    if not FERNET_KEY:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        logger.warning(
            f"FERNET_KEY не задан в .env. Сгенерирован временный ключ:\n"
            f"FERNET_KEY={key}\n"
            f"Добавьте его в .env для постоянного шифрования."
        )

async def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не задан в .env. Выход.")
        return

    _ensure_fernet_key()

    logger.info("Запуск приложения")
    db.init_db()

    bot, dp = create_bot_and_dispatcher()

    # Сбрасываем webhook и агрессивно вытесняем конкурирующий polling
    logger.info("Сброс webhook и вытеснение старых сессий...")
    await bot.delete_webhook(drop_pending_updates=True)
    # Повторяем getUpdates(timeout=0) пока не получим успешный ответ без конфликта
    for attempt in range(30):
        try:
            await bot.get_updates(offset=-1, timeout=0)
            logger.info(f"Сессия захвачена (попытка {attempt+1})")
            break
        except Exception as e:
            if "Conflict" in str(e):
                logger.warning(f"Конфликт сессии, попытка {attempt+1}/30...")
                await asyncio.sleep(2)
            else:
                break

    start_scheduler(notify_fn=notify_owner)

    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
