import json
import os
import logging
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
WELCOME_FILE = os.path.join(DATA_DIR, "welcome.json")

logger = logging.getLogger(__name__)


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path: str) -> dict:
    _ensure_data_dir()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        pass
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
    except Exception:
        pass
    return {}


def _save_json(path: str, data: dict) -> None:
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def track_user(user_id: int) -> None:
    users = _load_json(USERS_FILE)
    users[str(user_id)] = users.get(str(user_id), 0) + 1
    _save_json(USERS_FILE, users)


def track_download(user_id: int) -> None:
    data = _load_json(STATS_FILE)
    data["total_downloads"] = data.get("total_downloads", 0) + 1
    data["last_download"] = datetime.now().isoformat()
    user_key = f"user_{user_id}_downloads"
    data[user_key] = data.get(user_key, 0) + 1
    _save_json(STATS_FILE, data)


def get_stats() -> dict:
    users = _load_json(USERS_FILE)
    data = _load_json(STATS_FILE)
    return {
        "total_users": len(users),
        "total_downloads": data.get("total_downloads", 0),
        "last_download": data.get("last_download", "N/A"),
    }


def get_all_users() -> list[int]:
    users = _load_json(USERS_FILE)
    return [int(uid) for uid in users]


def get_additional_admins() -> list[int]:
    data = _load_json(ADMINS_FILE)
    return data.get("admins", [])


def add_admin(user_id: int) -> bool:
    admins = get_additional_admins()
    if user_id in admins:
        return False
    admins.append(user_id)
    _save_json(ADMINS_FILE, {"admins": admins})
    return True


def remove_admin(user_id: int) -> bool:
    admins = get_additional_admins()
    if user_id not in admins:
        return False
    admins.remove(user_id)
    _save_json(ADMINS_FILE, {"admins": admins})
    return True


def get_welcome_message() -> str | None:
    data = _load_json(WELCOME_FILE)
    return data.get("text")


def set_welcome_message(text: str) -> None:
    _save_json(WELCOME_FILE, {"text": text})
