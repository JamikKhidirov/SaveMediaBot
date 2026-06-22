import asyncio
import logging
import os
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot.handlers import start, download, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"), exist_ok=True)

    import aiohttp
    from aiohttp.resolver import ThreadedResolver
    connector = aiohttp.TCPConnector(
        family=socket.AF_INET,
        resolver=ThreadedResolver(),
        enable_cleanup_closed=True,
    )
    session = AiohttpSession(connector=connector)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
    dp = Dispatcher()
    dp.include_routers(start.router, download.router, admin.router)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical("❌ Бот не может подключиться к Telegram.\nОшибка: %s", e)
        logger.critical(
            "💡 Диагностика:\n"
            "  1. Открой cmd и введи: ping api.telegram.org\n"
            "  2. Если 'Не удается найти узел' — VPN не работает для системы\n"
            "  3. Нужен системный VPN (WireGuard/OpenVPN/Zapret), а не браузерный"
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
