import re

URL_PATTERN = re.compile(
    r"https?://(?:[\w-]+\.)?"
    r"(?:youtube\.com|youtu\.be|instagram\.com|tiktok\.com|"
    r"vk\.com|twitter\.com|x\.com|"
    r"[\w-]+\.[\w-]+)"
    r"(?:/\S*)?",
    re.IGNORECASE,
)

SHORTS_HEIGHT = 600


def extract_urls(text: str) -> list[str]:
    return list(set(URL_PATTERN.findall(text)))


def is_shorts(url: str) -> bool:
    return "/shorts/" in url


def short_label(url: str) -> str:
    return "🎬 Shorts" if is_shorts(url) else "🎬 Видео"
