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
from bot.config import PROXY

MAX_SIZE = 50 * 1024 * 1024
_PROXY_OVERRIDE: str | None = None
logger = logging.getLogger(__name__)


def set_proxy(proxy: str | None) -> None:
    global _PROXY_OVERRIDE
    _PROXY_OVERRIDE = proxy


def get_proxy() -> str | None:
    return _PROXY_OVERRIDE


def _proxy_from_env() -> str | None:
    if _PROXY_OVERRIDE:
        return _PROXY_OVERRIDE
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.getenv(var)
        if val:
            return val
    return PROXY


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _is_network_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(kw in msg for kw in (
        "10061", "connection refused", "connectionerror", "connection reset",
        "11001", "getaddrinfo", "dns", "unreachable", "timeout", "timed out",
    ))


_CLIENTS = [
    {"youtube": {"player_client": ["web"]}},
    {"youtube": {"player_client": ["android"]}},
    {"youtube": {"player_client": ["ios"]}},
]


def _base_opts() -> dict:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 60,
        "retries": 10,
        "fragment_retries": 10,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "force_ipv4": True,
        "extractor_args": _CLIENTS[0],
    }
    proxy = _proxy_from_env()
    if proxy:
        opts["proxy"] = proxy
    return opts


def _extract_with_opts(url: str, opts: dict, *, download: bool = False) -> tuple[dict, YoutubeDL]:
    errors = []
    for client_idx in range(len(_CLIENTS)):
        trial_opts = {**opts, "extractor_args": _CLIENTS[client_idx]}
        try:
            ydl = YoutubeDL(trial_opts)
            info = ydl.extract_info(url, download=download)
            if not info:
                raise ConnectionError(
                    "Не удалось подключиться к серверу.\n"
                    "Проверь VPN или укажи PROXY в файле .env"
                )
            return info, ydl
        except (TransportError, DownloadError) as e:
            if _is_network_error(e):
                logger.warning("Attempt %d failed (%s): %s", client_idx + 1, list(_CLIENTS[client_idx]["youtube"]["player_client"])[0], e)
                errors.append(e)
                if client_idx < len(_CLIENTS) - 1:
                    continue
            raise ConnectionError(
                "Не удалось подключиться к YouTube.\n"
                "Возможные решения:\n"
                "1. Введи /proxy http://ip:port — рабочий прокси\n"
                "2. Включи системный VPN (не браузерный)\n"
                "3. Удали PROXY из .env если используешь VPN"
            ) from e

    if errors and opts.get("proxy"):
        logger.warning("All clients failed with proxy, retrying without proxy")
        for client_idx in range(len(_CLIENTS)):
            trial_opts = {**opts, "proxy": None, "extractor_args": _CLIENTS[client_idx]}
            try:
                ydl = YoutubeDL(trial_opts)
                info = ydl.extract_info(url, download=download)
                if not info:
                    raise ConnectionError(
                        "Не удалось подключиться к серверу.\n"
                        "Проверь VPN или укажи PROXY в файле .env"
                    )
                return info, ydl
            except (TransportError, DownloadError) as e:
                if _is_network_error(e):
                    logger.warning("No-proxy attempt %d failed (%s): %s", client_idx + 1, list(_CLIENTS[client_idx]["youtube"]["player_client"])[0], e)
                    if client_idx < len(_CLIENTS) - 1:
                        continue
                raise ConnectionError(
                    "Не удалось подключиться к YouTube.\n"
                    "Возможные решения:\n"
                    "1. Введи /proxy http://ip:port — рабочий прокси\n"
                    "2. Включи системный VPN (не браузерный)\n"
                    "3. Удали PROXY из .env если используешь VPN"
                ) from e

    raise ConnectionError(
        "Не удалось подключиться к YouTube.\n"
        "Возможные решения:\n"
        "1. Введи /proxy http://ip:port — рабочий прокси\n"
        "2. Включи системный VPN (не браузерный)\n"
        "3. Удали PROXY из .env если используешь VPN"
    )


def get_info(url: str) -> dict:
    opts = _base_opts()
    opts["extract_flat"] = False
    opts["ignoreerrors"] = False
    info, _ = _extract_with_opts(url, opts, download=False)
    return info


def _get_available_heights(info: dict) -> list[int]:
    heights: set[int] = set()
    for fmt in info.get("formats") or []:
        h = fmt.get("height")
        if h and fmt.get("vcodec") != "none":
            heights.add(h)
    return sorted(heights, reverse=True)


def _prepare_download_opts(*, audio_only: bool, format_height: int | None) -> dict:
    has_ff = _has_ffmpeg()
    tmp = tempfile.gettempdir()
    outtmpl = os.path.join(tmp, "%(title)s.%(ext)s")
    opts = _base_opts()
    opts["outtmpl"] = outtmpl

    if audio_only:
        opts["format"] = "bestaudio/best"
        if has_ff:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            logger.info("ffmpeg not found, downloading best audio as-is")
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
    return opts


def _resolve_filename(info: dict, ydl: YoutubeDL, *, audio_only: bool) -> str:
    has_ff = _has_ffmpeg()
    tmp = tempfile.gettempdir()
    filename = ydl.prepare_filename(info)

    if audio_only and has_ff:
        filename = filename.rsplit(".", 1)[0] + ".mp3"
    elif audio_only and not has_ff:
        ext = info.get("ext", "m4a")
        filename = filename.rsplit(".", 1)[0] + f".{ext}"
    elif not filename.endswith(".mp4"):
        filename = filename.rsplit(".", 1)[0] + ".mp4"

    if not os.path.exists(filename):
        for f in os.listdir(tmp):
            if info.get("title") and info["title"] in f:
                filename = os.path.join(tmp, f)
                break

    return filename


def _download(
    url: str,
    *,
    audio_only: bool = False,
    format_height: int | None = None,
) -> str:
    opts = _prepare_download_opts(audio_only=audio_only, format_height=format_height)
    info, ydl = _extract_with_opts(url, opts, download=True)
    return _resolve_filename(info, ydl, audio_only=audio_only)


def _compress(filepath: str) -> str:
    size = os.path.getsize(filepath)
    if size <= MAX_SIZE:
        return filepath

    base, ext = os.path.splitext(filepath)
    outpath = f"{base}_compressed{ext}"

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", filepath,
                "-crf", "28",
                "-preset", "fast",
                "-y", outpath,
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        if os.path.getsize(outpath) < size:
            _cleanup(filepath)
            return outpath
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.warning("ffmpeg not available or compression failed")

    return filepath


async def download(
    url: str,
    *,
    audio_only: bool = False,
    format_height: int | None = None,
) -> str:
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
