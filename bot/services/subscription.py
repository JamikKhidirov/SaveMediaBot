import json
import os
import logging
from aiogram import Bot
from aiogram.enums import ChatMemberStatus

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
CHANNELS_FILE = os.path.join(DATA_DIR, "channels.json")

logger = logging.getLogger(__name__)


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def get_required_channels() -> list[str]:
    _ensure_data_dir()
    if not os.path.exists(CHANNELS_FILE):
        return []
    with open(CHANNELS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_required_channels(channels: list[str]) -> None:
    _ensure_data_dir()
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


def add_channel(channel: str) -> bool:
    channels = get_required_channels()
    if channel in channels:
        return False
    channels.append(channel)
    save_required_channels(channels)
    return True


def remove_channel(channel: str) -> bool:
    channels = get_required_channels()
    if channel not in channels:
        return False
    channels.remove(channel)
    save_required_channels(channels)
    return True


async def is_subscribed(bot: Bot, user_id: int, channel: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )
    except Exception:
        return False


async def check_subscriptions(bot: Bot, user_id: int) -> list[str]:
    unsubscribed = []
    for channel in get_required_channels():
        if not await is_subscribed(bot, user_id, channel):
            unsubscribed.append(channel)
    return unsubscribed
