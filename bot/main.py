import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommandScopeAllPrivateChats, FSInputFile

from bot.config import BOT_TOKEN, BOT_PHOTO_PATH, TELEGRAM_PROXY
from bot.handlers import start, download, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMMANDS = [
    ("start", "🚀 Запустить бота"),
    ("id", "🆔 Узнать свой Telegram ID"),
    ("help", "ℹ️ Помощь и список команд"),
    ("stats", "📊 Статистика бота"),
    ("broadcast", "📤 Рассылка всем пользователям"),
    ("add_channel", "➕ Добавить канал в рекламу"),
    ("remove_channel", "➖ Удалить канал из рекламы"),
    ("remove_all_channels", "🗑 Удалить все каналы"),
    ("list_channels", "📋 Список каналов"),
    ("add_admin", "👤 Добавить админа"),
    ("remove_admin", "👤 Удалить админа"),
    ("list_admins", "👥 Список админов"),
    ("set_welcome", "✏️ Установить приветствие"),
    ("help_admin", "🔧 Все команды админа"),
]


async def setup_bot_meta(bot: Bot) -> None:
    await bot.set_my_commands(
        [{"command": c[0], "description": c[1]} for c in COMMANDS],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_description(
        "🤖 SaveMediaBot — скачивай видео и аудио с YouTube, Instagram, TikTok, VK и других платформ.\n"
        "📥 Просто отправь ссылку и выбери формат.\n"
        "🎬 Выбор качества • 📦 Автосжатие • 📎 Пакетная загрузка"
    )
    await bot.set_my_short_description("📥 Скачивай видео/аудио с YouTube, Instagram, TikTok, VK")


async def set_bot_photo(bot: Bot, photo_path: str | None) -> None:
    if not photo_path or not os.path.exists(photo_path):
        return
    try:
        await bot.set_chat_photo(chat_id=bot.id, photo=FSInputFile(photo_path))
    except Exception:
        pass


async def main() -> None:
    session = AiohttpSession(proxy=TELEGRAM_PROXY) if TELEGRAM_PROXY else None
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()

    try:
        await setup_bot_meta(bot)
        await set_bot_photo(bot, BOT_PHOTO_PATH)
    except Exception as e:
        logger.warning("Не удалось настроить мету бота: %s", e)

    dp.include_routers(start.router, download.router, admin.router)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
