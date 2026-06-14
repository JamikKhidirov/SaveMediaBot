from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from bot.config import ADMIN_IDS
from bot.services.subscription import (
    get_required_channels,
    add_channel,
    remove_channel,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("add_channel"))
async def cmd_add_channel(
    message: types.Message,
    command: CommandObject,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    channel = command.args
    if not channel:
        await message.answer("❌ Укажи канал: /add_channel @channel или -100xxx")
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
