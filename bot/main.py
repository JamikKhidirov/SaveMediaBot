import asyncio
import logging
import os
import socket
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommand,
    FSInputFile,
)

from bot.config import BOT_TOKEN, BOT_PHOTO_PATH, TELEGRAM_PROXY, ADMIN_IDS
from bot.handlers import start, download, admin
from bot.services.stats import get_additional_admins

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="🚀 Запустить бота"),
    BotCommand(command="id", description="🆔 Мой Telegram ID"),
    BotCommand(command="help", description="ℹ️ Помощь"),
]

ADMIN_COMMANDS = [
    BotCommand(command="stats", description="📊 Статистика"),
    BotCommand(command="broadcast", description="📤 Рассылка"),
    BotCommand(command="add_channel", description="➕ Добавить канал"),
    BotCommand(command="remove_channel", description="➖ Удалить канал"),
    BotCommand(command="remove_all_channels", description="🗑 Удалить все каналы"),
    BotCommand(command="list_channels", description="📋 Список каналов"),
    BotCommand(command="add_admin", description="👤 Добавить админа"),
    BotCommand(command="remove_admin", description="👤 Удалить админа"),
    BotCommand(command="list_admins", description="👥 Список админов"),
    BotCommand(command="proxy", description="🔌 Прокси"),
    BotCommand(command="set_welcome", description="✏️ Приветствие"),
    BotCommand(command="help_admin", description="🔧 Команды админа"),
]


async def setup_bot_meta(bot: Bot) -> None:
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    admin_ids = set(ADMIN_IDS) | set(get_additional_admins())
    for uid in admin_ids:
        try:
            combined = USER_COMMANDS + ADMIN_COMMANDS
            await bot.set_my_commands(combined, scope=BotCommandScopeChat(chat_id=uid))
        except Exception:
            logger.warning("Не удалось установить команды для админа %s", uid)
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


def _make_session() -> AiohttpSession | None:
    kwargs: dict = {}
    if TELEGRAM_PROXY:
        kwargs["proxy"] = TELEGRAM_PROXY
    try:
        import aiohttp
        from aiohttp.resolver import AsyncResolver
        resolver = AsyncResolver(nameservers=["8.8.8.8", "1.1.1.1", "208.67.222.222"])
        kwargs["connector"] = aiohttp.TCPConnector(
            resolver=resolver,
            family=socket.AF_INET,
            enable_cleanup_closed=True,
        )
        return AiohttpSession(**kwargs)
    except Exception:
        pass
    return AiohttpSession(**kwargs) if kwargs else None


async def main() -> None:
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"), exist_ok=True)

    session = _make_session()
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
    except Exception as e:
        logger.critical(
            "❌ Бот не может подключиться к Telegram.\n\n"
            "Твой VPN не маршрутизирует системный трафик.\n"
            "Попробуй:\n"
            "  1. Открой .env и удали TELEGRAM_PROXY (если есть)\n"
            "  2. Установи aiodns: pip install aiodns\n"
            "  3. Используй системный VPN (WireGuard/OpenVPN), не браузерный\n"
            "  4. Или укажи рабочий TELEGRAM_PROXY=http://ip:port\n\n"
            "Ошибка: %s", e
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
