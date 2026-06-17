import os
import tempfile
import asyncio
import subprocess
import logging
from yt_dlp import YoutubeDL
from bot.config import PROXY

MAX_SIZE = 50 * 1024 * 1024
logger = logging.getLogger(__name__)


def _base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }
    if PROXY:
        opts["proxy"] = PROXY
    return opts


def get_info(url: str) -> dict:
    opts = _base_opts()
    opts["extract_flat"] = False
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _get_available_heights(info: dict) -> list[int]:
    heights: set[int] = set()
    for fmt in info.get("formats") or []:
        h = fmt.get("height")
        if h and fmt.get("vcodec") != "none":
            heights.add(h)
    return sorted(heights, reverse=True)


def _download(
    url: str,
    *,
    audio_only: bool = False,
    format_height: int | None = None,
) -> str:
    tmp = tempfile.gettempdir()
    outtmpl = os.path.join(tmp, "%(title)s.%(ext)s")

    opts = _base_opts()
    opts["outtmpl"] = outtmpl

    if audio_only:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    elif format_height:
        opts["format"] = (
            f"bestvideo[height<={format_height}]+bestaudio/"
            f"best[height<={format_height}]"
        )
    else:
        opts["format"] = "bestvideo+bestaudio/best"

    opts["merge_output_format"] = "mp4"

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        if audio_only:
            filename = filename.rsplit(".", 1)[0] + ".mp3"
        elif not filename.endswith(".mp4"):
            filename = filename.rsplit(".", 1)[0] + ".mp4"

        if not os.path.exists(filename):
            for f in os.listdir(tmp):
                if info.get("title") and info["title"] in f:
                    filename = os.path.join(tmp, f)
                    break

        return filename


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
