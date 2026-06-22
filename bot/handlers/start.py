from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.services.subscription import get_required_channels
from bot.services.stats import get_welcome_message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    custom = get_welcome_message()
    if custom:
        base = custom
    else:
        base = (
            "👋 <b>Привет! Я SaveMediaBot 🤖</b>\n\n"
            "📥 <b>Просто отправь ссылку</b> — я скачаю видео или аудио.\n\n"
            "🌐 <b>Поддерживаемые платформы:</b>\n"
            "▫️ YouTube (включая Shorts)\n"
            "▫️ Instagram\n"
            "▫️ TikTok\n"
            "▫️ VK\n"
            "▫️ Twitter / X\n"
            "▫️ и 1000+ других\n\n"
            "🎯 <b>Возможности:</b>\n"
            "▫️ Выбор качества: 360p → 1080p\n"
            "▫️ Аудио MP3 (192kbps)\n"
            "▫️ Пакетная загрузка (до 10 ссылок)\n"
            "▫️ Автосжатие видео >50MB\n\n"
            "⚡️ <b>Попробуй прямо сейчас:</b>\n"
            "Отправь ссылку на любое видео!"
        )
    text = base

    channels = get_required_channels()
    if channels:
        kb = InlineKeyboardBuilder()
        for ch in channels:
            kb.button(text=f"📢 @{ch}", url=f"https://t.me/{ch}")
        kb.adjust(1)
        text += "\n\n🔒 <b>Для использования подпишись:</b>\n"
        text += "\n".join(f"▫️ @{ch}" for ch in channels)
        await message.answer(text, reply_markup=kb.as_markup())
    else:
        await message.answer(text)


@router.message(Command("id"))
async def cmd_id(message: types.Message) -> None:
    await message.answer(
        f"🆔 <b>Твой Telegram ID:</b>\n"
        f"<code>{message.from_user.id}</code>\n\n"
        f"📌 <b>Username:</b> @{message.from_user.username or 'не задан'}\n"
        f"📌 <b>Имя:</b> {message.from_user.full_name}"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    text = (
        "ℹ️ <b>Помощь по SaveMediaBot</b>\n\n"
        "📥 <b>Как скачать:</b>\n"
        "1. Отправь ссылку на видео\n"
        "2. Выбери формат: 🎬 Видео или 🎵 Аудио\n"
        "3. (для видео) Выбери качество\n"
        "4. Файл придёт в чат ✅\n\n"
        "📎 <b>Пакетная загрузка:</b>\n"
        "Отправь несколько ссылок в одном сообщении\n\n"
        "📦 <b>Сжатие:</b>\n"
        "Видео >50MB сжимается автоматически (нужен ffmpeg)\n\n"
        "🔒 <b>Подписка:</b>\n"
        "Некоторые каналы могут быть обязательны для использования"
    )
    await message.answer(text)
