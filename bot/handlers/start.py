from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.services.subscription import get_required_channels

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    text = (
        "👋 <b>Привет! Я бот для скачивания медиа.</b>\n\n"
        "📥 <b>Поддерживаемые платформы:</b>\n"
        "• YouTube (включая Shorts)\n• Instagram\n• TikTok\n• VK\n"
        "• Twitter / X\n• и другие\n\n"
        "📌 <b>Как пользоваться:</b>\n"
        "Просто отправь ссылку на видео/аудио — "
        "я предложу варианты загрузки.\n\n"
        "🎬 Выбор качества (360p — 1080p)\n"
        "📦 Автосжатие при >50MB"
    )

    channels = get_required_channels()
    if channels:
        kb = InlineKeyboardBuilder()
        for ch in channels:
            kb.button(text=f"📢 @{ch}", url=f"https://t.me/{ch}")
        kb.adjust(1)
        text += "\n\n🔒 <b>Не забудь подписаться на каналы:</b>\n"
        text += "\n".join(f"• @{ch}" for ch in channels)
        await message.answer(text, reply_markup=kb.as_markup())
    else:
        await message.answer(text)
