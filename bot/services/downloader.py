import os
import json
import shutil
import tempfile
import asyncio
import subprocess
import logging
from typing import Any
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from yt_dlp.networking.exceptions import TransportError
from bot.config import PROXY

MAX_SIZE = 50 * 1024 * 1024
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
PROXY_FILE = os.path.join(DATA_DIR, "proxy.json")


def _load_proxy() -> str | None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(PROXY_FILE):
            with open(PROXY_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("proxy") or None
    except Exception:
        pass
    return None


def _save_proxy(proxy: str | None) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PROXY_FILE, "w", encoding="utf-8") as f:
            json.dump({"proxy": proxy}, f)
    except Exception:
        pass


_PROXY_OVERRIDE: str | None = _load_proxy()


def set_proxy(proxy: str | None) -> None:
    global _PROXY_OVERRIDE
    _PROXY_OVERRIDE = proxy
    _save_proxy(proxy)


def get_proxy() -> str | None:
    return _PROXY_OVERRIDE


def _proxy_candidate() -> str | None:
    if _PROXY_OVERRIDE:
        return _PROXY_OVERRIDE
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.getenv(var)
        if val:
            return val
    return PROXY


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


_CLIENTS = [
    {"youtube": {"player_client": ["web"]}},
    {"youtube": {"player_client": ["android"]}},
    {"youtube": {"player_client": ["ios"]}},
]


def _make_attempt(url: str, opts: dict, *, download: bool) -> dict | None:
    try:
        ydl = YoutubeDL(opts)
        return ydl.extract_info(url, download=download)
    except (TransportError, DownloadError) as e:
        msg = str(e).lower()
        if any(kw in msg for kw in ("10061", "11001", "getaddrinfo", "connection refused", "dns", "timeout", "connectionerror", "connection reset", "unreachable")):
            return None
        raise ConnectionError(
            "❌ <b>Не удалось подключиться к YouTube.</b>\n\n"
            "Возможные решения:\n"
            "1️⃣ <b>/proxy http://ip:port</b> — установи рабочий прокси\n"
            "2️⃣ Включи <b>системный VPN</b> (не браузерный)\n"
            "3️⃣ Удали <b>PROXY</b> из <code>.env</code> если используешь VPN\n"
            "4️⃣ Проверь что прокси-сервер запущен"
        ) from e


def _extract(url: str, *, download: bool = False) -> dict:
    proxy = _proxy_candidate()

    combos = []
    if proxy:
        for c in _CLIENTS:
            combos.append(("с прокси", proxy, c))
    for c in _CLIENTS:
        combos.append(("без прокси", None, c))

    for label, p, client in combos:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 60,
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 5,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "force_ipv4": True,
            "extractor_args": client,
        }
        if p:
            opts["proxy"] = p
        if download:
            opts["outtmpl"] = os.path.join(tempfile.gettempdir(), "%(title)s.%(ext)s")

        info = _make_attempt(url, opts, download=download)
        if info is not None:
            if not info:
                raise ConnectionError("Сервер вернул пустой ответ")
            return info
        cname = list(client["youtube"]["player_client"])[0]
        logger.info("%s (%s) — не ответил", label, cname)

    raise ConnectionError(
        "❌ <b>Не удалось подключиться к YouTube.</b>\n\n"
        "Возможные решения:\n"
        "1️⃣ <b>/proxy http://ip:port</b> — установи рабочий прокси\n"
        "2️⃣ Включи <b>системный VPN</b> (не браузерный)\n"
        "3️⃣ Удали <b>PROXY</b> из <code>.env</code> если используешь VPN\n"
        "4️⃣ Проверь что прокси-сервер запущен"
    )


def get_info(url: str) -> dict:
    return _extract(url, download=False)


def _get_available_heights(info: dict) -> list[int]:
    heights: set[int] = set()
    for fmt in info.get("formats") or []:
        h = fmt.get("height")
        if h and fmt.get("vcodec") != "none":
            heights.add(h)
    return sorted(heights, reverse=True)


def _get_filename(info: dict, audio_only: bool) -> str:
    tmp = tempfile.gettempdir()
    title = info.get("title", "unknown")
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in title)

    if audio_only and _has_ffmpeg():
        ext = "mp3"
    elif audio_only:
        ext = info.get("ext", "m4a")
    else:
        ext = "mp4"

    path = os.path.join(tmp, f"{safe}.{ext}")
    if os.path.exists(path):
        return path

    for f in os.listdir(tmp):
        if title in f:
            return os.path.join(tmp, f)
    return path


def _download(
    url: str,
    *,
    audio_only: bool = False,
    format_height: int | None = None,
) -> str:
    has_ff = _has_ffmpeg()

    proxy = _proxy_candidate()
    tmp = tempfile.gettempdir()
    outtmpl = os.path.join(tmp, "%(title)s.%(ext)s")

    combos = []
    if proxy:
        for c in _CLIENTS:
            combos.append(("с прокси", proxy, c))
    for c in _CLIENTS:
        combos.append(("без прокси", None, c))

    for label, p, client in combos:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 60,
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 5,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "force_ipv4": True,
            "extractor_args": client,
            "outtmpl": outtmpl,
        }
        if p:
            opts["proxy"] = p
        if audio_only:
            opts["format"] = "bestaudio/best"
            if has_ff:
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ]
        elif format_height:
            if has_ff:
                opts["format"] = f"bestvideo[height<={format_height}]+bestaudio/best[height<={format_height}]"
                opts["merge_output_format"] = "mp4"
            else:
                opts["format"] = f"best[height<={format_height}]"
        else:
            if has_ff:
                opts["format"] = "bestvideo+bestaudio/best"
                opts["merge_output_format"] = "mp4"
            else:
                opts["format"] = "best"

        info = _make_attempt(url, opts, download=True)
        if info is not None:
            return _get_filename(info, audio_only=audio_only)
        cname = list(client["youtube"]["player_client"])[0]
        logger.info("Скачивание %s (%s) — не ответил", label, cname)

    raise ConnectionError(
        "❌ <b>Не удалось подключиться к YouTube.</b>\n\n"
        "Возможные решения:\n"
        "1️⃣ <b>/proxy http://ip:port</b> — установи рабочий прокси\n"
        "2️⃣ Включи <b>системный VPN</b> (не браузерный)\n"
        "3️⃣ Удали <b>PROXY</b> из <code>.env</code> если используешь VPN\n"
        "4️⃣ Проверь что прокси-сервер запущен"
    )


def _compress(filepath: str) -> str:
    size = os.path.getsize(filepath)
    if size <= MAX_SIZE:
        return filepath

    base, ext = os.path.splitext(filepath)
    outpath = f"{base}_compressed{ext}"

    try:
        subprocess.run(
            ["ffmpeg", "-i", filepath, "-crf", "28", "-preset", "fast", "-y", outpath],
            check=True, capture_output=True, timeout=300,
        )
        if os.path.getsize(outpath) < size:
            _cleanup(filepath)
            return outpath
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.warning("ffmpeg not available or compression failed")

    return filepath


async def download(url: str, *, audio_only: bool = False, format_height: int | None = None) -> str:
    return await asyncio.to_thread(_download, url, audio_only=audio_only, format_height=format_height)


async def compress_video(filepath: str) -> str:
    return await asyncio.to_thread(_compress, filepath)


def _cleanup(filepath: str) -> None:
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass


async def cleanup(filepath: str) -> None:
    await asyncio.to_thread(_cleanup, filepath)
