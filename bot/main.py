import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN, TELEGRAM_PROXY
from bot.handlers import start, download, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _try_poll(bot: Bot) -> None:
    dp = Dispatcher()
    dp.include_routers(start.router, download.router, admin.router)
    await dp.start_polling(bot)


async def main() -> None:
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"), exist_ok=True)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await _try_poll(bot)
    except Exception:
        if TELEGRAM_PROXY:
            logger.info("Прямое подключение не вышло, пробую через прокси %s", TELEGRAM_PROXY)
            await bot.session.close()
            bot = Bot(
                token=BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                session=AiohttpSession(proxy=TELEGRAM_PROXY),
            )
            try:
                await _try_poll(bot)
                return
            except Exception as e2:
                logger.critical(
                    "❌ Бот не может подключиться к Telegram.\n"
                    "BOT_TOKEN правильный? TELEGRAM_PROXY в .env работает?\n"
                    "Ошибка: %s", e2
                )
        else:
            logger.critical(
                "❌ Бот не может подключиться к Telegram.\n"
                "1. Проверь BOT_TOKEN в .env\n"
                "2. Включи системный VPN (не браузерный)\n"
                "3. Если нужно — добавь TELEGRAM_PROXY в .env\n"
            )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
