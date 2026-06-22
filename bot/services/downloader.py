import os
import shutil
import tempfile
import asyncio
import subprocess
import logging
from typing import Any
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from yt_dlp.networking.exceptions import TransportError

from . import dns  # noqa: F401

MAX_SIZE = 50 * 1024 * 1024
logger = logging.getLogger(__name__)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


_CLIENTS = [
    {"youtube": {"player_client": ["web"], "player_skip": ["webpage", "configs", "js"]}},
    {"youtube": {"player_client": ["android"], "player_skip": ["webpage"]}},
    {"youtube": {"player_client": ["ios"]}},
    {"youtube": {"player_client": ["tv"]}},
    {"youtube": {"player_client": ["web_embedded"]}},
    {"youtube": {"player_client": ["tv_embedded"]}},
]

_NETWORK_ERRORS = ("10061", "11001", "11002", "getaddrinfo", "connection refused", "dns", "timeout", "connectionerror", "connection reset", "unreachable")


def _try_attempt(url: str, opts: dict, *, download: bool) -> dict | None:
    try:
        ydl = YoutubeDL(opts)
        return ydl.extract_info(url, download=download)
    except TransportError as e:
        # сетевые ошибки — пробуем следующий клиент
        return None
    except DownloadError as e:
        msg = str(e).lower()
        if "requested format" in msg:
            raise ValueError(f"❌ Формат не найден для этого видео") from e
        # все остальные ошибки YouTube — пробуем другой клиент
        return None


def _extract(url: str, *, download: bool = False) -> dict:
    for client in _CLIENTS:
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
        if download:
            opts["outtmpl"] = os.path.join(tempfile.gettempdir(), "%(title)s.%(ext)s")

        info = _try_attempt(url, opts, download=download)
        if info is not None:
            return info
        cname = list(client["youtube"]["player_client"])[0]
        logger.info("Клиент %s — не ответил", cname)

    raise ConnectionError(
        "❌ Не удалось подключиться к YouTube.\n"
        "1. Проверь что VPN включён\n"
        "2. Если VPN браузерный — нужен системный (WireGuard/OpenVPN)\n"
        "3. Попробуй перезапустить бота"
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
    ext = "mp3" if (audio_only and _has_ffmpeg()) else (info.get("ext", "m4a") if audio_only else "mp4")
    path = os.path.join(tmp, f"{safe}.{ext}")
    if os.path.exists(path):
        return path
    for f in os.listdir(tmp):
        if title in f:
            return os.path.join(tmp, f)
    return path


def _download(url: str, *, audio_only: bool = False, format_height: int | None = None) -> str:
    has_ff = _has_ffmpeg()
    tmp = tempfile.gettempdir()
    outtmpl = os.path.join(tmp, "%(title)s.%(ext)s")

    for client in _CLIENTS:
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
        if audio_only:
            opts["format"] = "ba/b"
            if has_ff:
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ]
        elif format_height:
            opts["format"] = f"bv*[height<={format_height}]+ba/b" if has_ff else f"b[height<={format_height}]"
            if has_ff:
                opts["merge_output_format"] = "mp4"
        else:
            opts["format"] = "bv*+ba/b" if has_ff else "b"
            if has_ff:
                opts["merge_output_format"] = "mp4"

        try:
            info = _try_attempt(url, opts, download=True)
        except ValueError:
            logger.info("Формат не доступен для клиента %s, пробую другой формат", list(client["youtube"]["player_client"])[0])
            continue
        if info is not None:
            return _get_filename(info, audio_only=audio_only)
        cname = list(client["youtube"]["player_client"])[0]
        logger.info("Клиент %s — не ответил", cname)

    raise ConnectionError(
        "❌ Не удалось подключиться к YouTube.\n"
        "1. Проверь что VPN включён\n"
        "2. Если VPN браузерный — нужен системный (WireGuard/OpenVPN)\n"
        "3. Попробуй перезапустить бота"
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
