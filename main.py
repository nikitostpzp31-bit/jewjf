"""Entry point"""
import asyncio
import logging

from logger import setup_logger
setup_logger()

import db
db.init_db()

from bot import get_bot, get_dispatcher

async def main():
    bot = get_bot()
    dp  = get_dispatcher()

    logging.getLogger("apple_bot").info("Bot starting...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
