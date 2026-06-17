import os
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.utils import extract_urls, is_shorts, short_label, SHORTS_HEIGHT
from bot.services.downloader import (
    download,
    compress_video,
    cleanup,
    get_info,
    _get_available_heights,
    MAX_SIZE,
)
from bot.services.subscription import check_subscriptions

router = Router()
logger = logging.getLogger(__name__)

_link_store: dict[int, dict] = {}
_pending_store: dict[int, str] = {}


async def _ensure_subscribed(message: types.Message) -> bool:
    user_id = message.from_user.id
    unsubscribed = await check_subscriptions(message.bot, user_id)
    if not unsubscribed:
        return True

    kb = InlineKeyboardBuilder()
    for ch in unsubscribed:
        kb.button(text=f"📢 @{ch}", url=f"https://t.me/{ch}")
    kb.button(text="✅ Я подписался", callback_data="check_sub")
    kb.adjust(1)

    await message.answer(
        "🔒 <b>Для использования бота подпишись на каналы:</b>\n\n"
        + "\n".join(f"• @{ch}" for ch in unsubscribed),
        reply_markup=kb.as_markup(),
    )
    return False


@router.callback_query(F.data == "check_sub")
async def cb_check_subscription(callback: types.CallbackQuery) -> None:
    user_id = callback.from_user.id
    text = _pending_store.get(user_id)
    if not text:
        await callback.answer("Нет ожидающих ссылок", show_alert=True)
        return

    unsubscribed = await check_subscriptions(callback.bot, user_id)
    if unsubscribed:
        await callback.answer("❌ Ты ещё не подписался на все каналы", show_alert=True)
        return

    del _pending_store[user_id]
    await callback.message.delete()

    urls = extract_urls(text)
    if not urls:
        return
    if len(urls) == 1:
        await _handle_single(callback.message, urls[0])
    else:
        await _handle_batch(callback.message, urls)


@router.message(F.text)
async def handle_link(message: types.Message) -> None:
    urls = extract_urls(message.text)
    if not urls:
        return

    if not await _ensure_subscribed(message):
        _pending_store[message.from_user.id] = message.text
        return

    if len(urls) == 1:
        await _handle_single(message, urls[0])
    else:
        await _handle_batch(message, urls)


async def _handle_single(message: types.Message, url: str) -> None:
    msg = await message.answer("📥 <b>Выбери формат:</b>")
    mid = msg.message_id
    _link_store[mid] = {"urls": [url]}
    await msg.edit_text(
        "📥 <b>Выбери формат:</b>",
        reply_markup=(
            InlineKeyboardBuilder()
            .button(text=short_label(url), callback_data=f"fmt:video:{mid}")
            .button(text="🎵 Аудио (MP3)", callback_data=f"fmt:audio:{mid}")
            .adjust(2)
            .as_markup()
        ),
    )


async def _handle_batch(message: types.Message, urls: list[str]) -> None:
    msg = await message.answer(f"📥 <b>Найдено {len(urls)} ссылок.</b>\n\nКак скачать?")
    mid = msg.message_id
    _link_store[mid] = {"urls": urls}
    await msg.edit_text(
        f"📥 <b>Найдено {len(urls)} ссылок.</b>\n\nКак скачать?",
        reply_markup=(
            InlineKeyboardBuilder()
            .button(text="🎬 Все видео", callback_data=f"batch:video:{mid}")
            .button(text="🎵 Все аудио", callback_data=f"batch:audio:{mid}")
            .adjust(2)
            .as_markup()
        ),
    )


@router.callback_query(F.data.startswith("fmt:video:"))
async def cb_format_video(callback: types.CallbackQuery) -> None:
    msg_id = int(callback.data.split(":")[2])
    entry = _link_store.get(msg_id)
    if not entry:
        await callback.answer("Ссылка устарела, отправь снова", show_alert=True)
        return

    url = entry["urls"][0]
    await callback.message.edit_text("⏳ <b>Получаю информацию о видео...</b>")

    try:
        info = await asyncio.to_thread(get_info, url)
        heights = _get_available_heights(info)
    except Exception as e:
        await callback.message.edit_text(f"❌ <b>Ошибка:</b> {e}")
        return

    if is_shorts(url):
        heights = [h for h in heights if h <= SHORTS_HEIGHT] or heights[:1]

    kb = InlineKeyboardBuilder()
    for h in heights:
        kb.button(text=f"{h}p", callback_data=f"q:{h}:{msg_id}")
    kb.button(text="🏆 Лучшее", callback_data=f"q:best:{msg_id}")
    kb.button(text="⬅ Назад", callback_data=f"back:{msg_id}")
    kb.adjust(3)

    await callback.message.edit_text(
        "🎬 <b>Выбери качество:</b>",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("fmt:audio:"))
async def cb_format_audio(callback: types.CallbackQuery) -> None:
    msg_id = int(callback.data.split(":")[2])
    entry = _link_store.get(msg_id)
    if not entry:
        await callback.answer("Ссылка устарела, отправь снова", show_alert=True)
        return

    url = entry["urls"][0]
    await _process_download(callback, url, audio_only=True, msg_id=msg_id)


@router.callback_query(F.data.startswith("q:"))
async def cb_quality(callback: types.CallbackQuery) -> None:
    parts = callback.data.split(":")
    height_str, msg_id = parts[1], int(parts[2])
    entry = _link_store.get(msg_id)
    if not entry:
        await callback.answer("Ссылка устарела, отправь снова", show_alert=True)
        return

    url = entry["urls"][0]
    format_height = None if height_str == "best" else int(height_str)
    await _process_download(callback, url, audio_only=False, format_height=format_height, msg_id=msg_id)


@router.callback_query(F.data.startswith("batch:video:"))
async def cb_batch_video(callback: types.CallbackQuery) -> None:
    msg_id = int(callback.data.split(":")[2])
    entry = _link_store.get(msg_id)
    if not entry:
        await callback.answer("Ссылка устарела, отправь снова", show_alert=True)
        return
    await _process_batch(callback, entry["urls"], audio_only=False, msg_id=msg_id)


@router.callback_query(F.data.startswith("batch:audio:"))
async def cb_batch_audio(callback: types.CallbackQuery) -> None:
    msg_id = int(callback.data.split(":")[2])
    entry = _link_store.get(msg_id)
    if not entry:
        await callback.answer("Ссылка устарела, отправь снова", show_alert=True)
        return
    await _process_batch(callback, entry["urls"], audio_only=True, msg_id=msg_id)


@router.callback_query(F.data.startswith("back:"))
async def cb_back(callback: types.CallbackQuery) -> None:
    msg_id = int(callback.data.split(":")[1])
    entry = _link_store.get(msg_id)
    if not entry:
        await callback.answer("Ссылка устарела, отправь снова")
        return

    url = entry["urls"][0]
    await callback.message.edit_text(
        "📥 <b>Выбери формат:</b>",
        reply_markup=(
            InlineKeyboardBuilder()
            .button(text=short_label(url), callback_data=f"fmt:video:{msg_id}")
            .button(text="🎵 Аудио (MP3)", callback_data=f"fmt:audio:{msg_id}")
            .adjust(2)
            .as_markup()
        ),
    )


async def _process_download(
    callback: types.CallbackQuery,
    url: str,
    *,
    audio_only: bool,
    format_height: int | None = None,
    msg_id: int | None = None,
) -> None:
    await callback.message.edit_text("⏳ <b>Скачиваю...</b>")

    filepath = None
    try:
        filepath = await download(url, audio_only=audio_only, format_height=format_height)

        if not filepath or not os.path.exists(filepath):
            await callback.message.edit_text("❌ <b>Не удалось загрузить файл.</b>\nПроверь ссылку или попробуй позже.")
            return

        if not audio_only:
            await callback.message.edit_text("📦 <b>Проверяю размер...</b>")
            filepath = await compress_video(filepath)

        if not audio_only and os.path.getsize(filepath) > MAX_SIZE:
            await callback.message.edit_text(
                "⚠️ <b>Файл больше 50MB.</b>\nffmpeg не найден — не могу сжать.\nОтправляю как есть."
            )

        caption = "✅ <b>Готово!</b>"
        if audio_only:
            await callback.message.answer_audio(types.FSInputFile(filepath), caption=caption)
        else:
            await callback.message.answer_video(types.FSInputFile(filepath), caption=caption, supports_streaming=True)

        await callback.message.delete()

    except Exception as e:
        logger.exception("Download failed")
        await callback.message.edit_text(f"❌ <b>Ошибка:</b> {e}")
    finally:
        if filepath:
            await cleanup(filepath)
        if msg_id and msg_id in _link_store:
            del _link_store[msg_id]


async def _process_batch(
    callback: types.CallbackQuery,
    urls: list[str],
    *,
    audio_only: bool,
    msg_id: int,
) -> None:
    total = len(urls)
    success = 0
    failed = 0

    await callback.message.edit_text(f"⏳ <b>Начинаю загрузку {total} файлов...</b>")

    for i, url in enumerate(urls, 1):
        status_msg = await callback.message.answer(f"📥 <b>[{i}/{total}]</b> Скачиваю...")
        filepath = None
        try:
            filepath = await download(url, audio_only=audio_only)
            if not filepath or not os.path.exists(filepath):
                failed += 1
                await status_msg.edit_text(f"❌ <b>[{i}/{total}]</b> Ошибка загрузки")
                continue

            if not audio_only:
                filepath = await compress_video(filepath)

            kwargs = {"caption": f"✅ <b>[{i}/{total}]</b>"}
            if audio_only:
                await callback.message.answer_audio(types.FSInputFile(filepath), **kwargs)
            else:
                await callback.message.answer_video(types.FSInputFile(filepath), **kwargs, supports_streaming=True)

            success += 1
            await status_msg.delete()

        except Exception as e:
            logger.exception("Batch download failed")
            failed += 1
            await status_msg.edit_text(f"❌ <b>[{i}/{total}]</b> {e}")
        finally:
            if filepath:
                await cleanup(filepath)

    await callback.message.edit_text(f"🏁 <b>Готово!</b>\n✅ Успешно: {success}\n❌ Ошибок: {failed}")

    if msg_id in _link_store:
        del _link_store[msg_id]
