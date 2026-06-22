import socket
import time
import logging
import threading
import json
import ssl
import http.client
from typing import Optional

logger = logging.getLogger(__name__)

_DOH_IPS = ("8.8.8.8", "8.8.4.4")

_BLOCKED = (
    "youtube.com", ".youtube.com", ".googlevideo.com",
    ".ytimg.com", ".ggpht.com", ".googleapis.com",
    "instagram.com", ".instagram.com", ".cdninstagram.com", ".fbcdn.net",
    ".tiktokcdn.com", ".tiktok.com", "telegram.org", ".telegram.org",
    "t.me", "tdesktop.com",
)

_cache: dict[str, tuple[float, Optional[list[str]]]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 300

_original = socket.getaddrinfo
_applied = False
_ssl_ctx: Optional[ssl.SSLContext] = None


def _get_ssl_ctx() -> ssl.SSLContext:
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx


def _resolve_doh(hostname: str) -> Optional[list[str]]:
    for ip in _DOH_IPS:
        try:
            sock = socket.create_connection((ip, 443), timeout=5)
            ssock = _get_ssl_ctx().wrap_socket(sock, server_hostname="dns.google")
            conn = http.client.HTTPSConnection("dns.google", context=_get_ssl_ctx(), timeout=5)
            conn.sock = ssock
            conn.request("GET", f"/resolve?name={hostname}&type=A",
                         headers={"Accept": "application/dns-json", "Host": "dns.google"})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            ips = [x["data"] for x in data.get("Answer", []) if x.get("type") == 1]
            if ips:
                return ips
        except Exception:
            continue
    return None


def _resolve_cached(hostname: str) -> Optional[list[str]]:
    now = time.time()
    with _cache_lock:
        if hostname in _cache and now - _cache[hostname][0] < _CACHE_TTL:
            return _cache[hostname][1]
    ips = _resolve_doh(hostname)
    with _cache_lock:
        _cache[hostname] = (now, ips)
    return ips


def _is_blocked(host: str) -> bool:
    lower = host.lower()
    for s in _BLOCKED:
        if lower == s or lower.endswith(s):
            return True
    return False


def _patched(host, port, family=0, type=0, proto=0, flags=0):
    if host and isinstance(host, str) and family == 0:
        if _is_blocked(host):
            ips = _resolve_cached(host)
            if ips:
                return [(socket.AF_INET, type, proto, "", (ip, port)) for ip in ips]
        else:
            try:
                return _original(host, port, socket.AF_INET, type, proto, flags)
            except OSError:
                pass
    return _original(host, port, family, type, proto, flags)


def apply():
    global _applied
    if not _applied:
        socket.getaddrinfo = _patched
        _applied = True
        logger.info("DNS: IPv4 + DoH fallback for blocked hosts (%d domains)", len(_BLOCKED))


apply()
