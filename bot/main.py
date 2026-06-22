import asyncio
import logging
import os
import socket
from functools import partial
import json

import aiohttp
from aiohttp.resolver import ThreadedResolver

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot.handlers import start, download, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class _Session(AiohttpSession):
    def __init__(self):
        super().__init__()
        self._custom_connector = aiohttp.TCPConnector(
            family=socket.AF_INET,
            resolver=ThreadedResolver(),
            enable_cleanup_closed=True,
        )

    async def _setup_session(self, bot: Bot) -> None:
        if self._session is not None:
            return
        self._session = aiohttp.ClientSession(
            json_serialize=partial(json.dumps, ensure_ascii=False, indent=2),
            connector=self._custom_connector,
        )


async def main() -> None:
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"), exist_ok=True)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=_Session())
    dp = Dispatcher()
    dp.include_routers(start.router, download.router, admin.router)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical("❌ Бот не может подключиться к Telegram.\nОшибка: %s", e)
        logger.critical(
            "💡 Открой cmd и введи: ping api.telegram.org\n"
            "Если 'Не удается найти узел' — VPN не работает для системы."
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
