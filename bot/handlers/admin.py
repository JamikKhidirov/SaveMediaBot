from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import ADMIN_IDS
from bot.services.subscription import (
    get_required_channels,
    add_channel,
    remove_channel,
)
from bot.services.stats import (
    get_stats,
    get_all_users,
    get_additional_admins,
    add_admin as stats_add_admin,
    remove_admin as stats_remove_admin,
    get_welcome_message,
    set_welcome_message,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    return user_id in get_additional_admins()


@router.message(Command("add_channel"))
async def cmd_add_channel(
    message: types.Message,
    command: CommandObject,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    channel = command.args
    if not channel:
        await message.answer("❌ Укажи канал: /add_channel @channel")
        return

    channel = channel.strip().lstrip("@")
    if add_channel(channel):
        await message.answer(f"✅ Канал @{channel} добавлен в рекламу")
    else:
        await message.answer(f"⚠️ Канал @{channel} уже в списке")


@router.message(Command("remove_channel"))
async def cmd_remove_channel(
    message: types.Message,
    command: CommandObject,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    channel = command.args
    if not channel:
        await message.answer("❌ Укажи канал: /remove_channel @channel")
        return

    channel = channel.strip().lstrip("@")
    if remove_channel(channel):
        await message.answer(f"✅ Канал @{channel} удалён из рекламы")
    else:
        await message.answer(f"⚠️ Канал @{channel} не найден в списке")


@router.message(Command("remove_all_channels"))
async def cmd_remove_all_channels(message: types.Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить всё", callback_data="confirm_remove_all")
    kb.button(text="❌ Нет", callback_data="cancel_remove_all")
    kb.adjust(2)

    await message.answer(
        "⚠️ <b>Точно удалить все каналы из рекламы?</b>",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "confirm_remove_all")
async def cb_confirm_remove_all(callback: types.CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    from bot.services.subscription import save_required_channels
    save_required_channels([])
    await callback.message.edit_text("✅ Все каналы удалены из рекламы")


@router.callback_query(F.data == "cancel_remove_all")
async def cb_cancel_remove_all(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text("❌ Отменено")


@router.message(Command("list_channels"))
async def cmd_list_channels(message: types.Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    channels = get_required_channels()
    if not channels:
        await message.answer("📋 Список каналов пуст")
        return

    lines = [f"{i+1}. @{ch}" for i, ch in enumerate(channels)]
    await message.answer(
        "📋 <b>Каналы для подписки:</b>\n" + "\n".join(lines)
    )


@router.message(Command("add_admin"))
async def cmd_add_admin(
    message: types.Message,
    command: CommandObject,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    arg = command.args
    if not arg:
        await message.answer("❌ Укажи ID пользователя: /add_admin 123456789")
        return

    try:
        uid = int(arg.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    if uid in ADMIN_IDS:
        await message.answer("⚠️ Этот пользователь уже админ (в .env)")
        return

    if stats_add_admin(uid):
        await message.answer(f"✅ Админ {uid} добавлен")
    else:
        await message.answer(f"⚠️ Админ {uid} уже в списке")


@router.message(Command("remove_admin"))
async def cmd_remove_admin(
    message: types.Message,
    command: CommandObject,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    arg = command.args
    if not arg:
        await message.answer("❌ Укажи ID пользователя: /remove_admin 123456789")
        return

    try:
        uid = int(arg.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    if uid in ADMIN_IDS:
        await message.answer("⚠️ Нельзя удалить админа из .env. Удали его вручную")
        return

    if stats_remove_admin(uid):
        await message.answer(f"✅ Админ {uid} удалён")
    else:
        await message.answer(f"⚠️ Админ {uid} не найден")


@router.message(Command("list_admins"))
async def cmd_list_admins(message: types.Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    lines = [f"👑 <b>Главные админы (.env):</b>"]
    for uid in ADMIN_IDS:
        lines.append(f"  • <code>{uid}</code>")
    additional = get_additional_admins()
    if additional:
        lines.append(f"\n👤 <b>Дополнительные админы:</b>")
        for uid in additional:
            lines.append(f"  • <code>{uid}</code>")

    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    stats = get_stats()
    await message.answer(
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"📥 Всего скачиваний: <b>{stats['total_downloads']}</b>\n"
        f"🕐 Последнее скачивание: <code>{stats['last_download']}</code>"
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(
    message: types.Message,
    command: CommandObject,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    text = command.args
    if not text:
        await message.answer(
            "❌ Напиши текст: /broadcast Привет всем!"
        )
        return

    users = get_all_users()
    sent = 0
    failed = 0

    status_msg = await message.answer(f"📤 Рассылка начата. Всего: {len(users)}")
    for uid in users:
        try:
            await message.bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"🏁 <b>Рассылка завершена</b>\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )


@router.message(Command("set_welcome"))
async def cmd_set_welcome(
    message: types.Message,
    command: CommandObject,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    text = command.args
    if not text:
        await message.answer(
            "❌ Напиши текст: /set_welcome Привет! Это мой бот..."
        )
        return

    set_welcome_message(text)
    await message.answer("✅ Приветствие сохранено")


@router.message(Command("help_admin"))
async def cmd_help_admin(message: types.Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    await message.answer(
        "🔧 <b>Команды админа</b>\n\n"
        "📢 <b>Реклама / каналы:</b>\n"
        "/add_channel @channel — добавить канал\n"
        "/remove_channel @channel — удалить канал\n"
        "/remove_all_channels — удалить всё\n"
        "/list_channels — список каналов\n\n"
        "👤 <b>Админы:</b>\n"
        "/add_admin &lt;id&gt; — добавить админа\n"
        "/remove_admin &lt;id&gt; — удалить админа\n"
        "/list_admins — список админов\n\n"
        "📊 <b>Прочее:</b>\n"
        "/stats — статистика бота\n"
        "/broadcast &lt;text&gt; — рассылка всем\n"
        "/set_welcome &lt;text&gt; — приветствие"
    )
