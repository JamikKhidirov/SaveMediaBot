import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot.handlers import start, download, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"), exist_ok=True)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_routers(start.router, download.router, admin.router)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical("❌ Ошибка: %s", e)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
