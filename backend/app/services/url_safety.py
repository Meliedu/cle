"""URL validation helpers for SSRF mitigation."""

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import settings


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable → treat as unsafe
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolves_to_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    return any(_is_private_ip(info[4][0]) for info in infos)


def validate_canvas_base_url(url: str) -> str:
    """Validate a Canvas LMS base URL: HTTPS, allowlisted host, no private IPs.

    Returns the normalized URL on success; raises ValueError otherwise.
    """
    if not url:
        raise ValueError("canvas_base_url is required")

    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("canvas_base_url must use https://")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("canvas_base_url is missing a hostname")
    if parsed.port and parsed.port not in (443,):
        raise ValueError("canvas_base_url may only use the default https port")

    allowed = [h.strip().lower() for h in (settings.canvas_allowed_hosts or "").split(",") if h.strip()]
    if allowed:
        if not any(host == a or host.endswith("." + a) for a in allowed):
            raise ValueError(f"canvas_base_url host '{host}' not in allowlist")
    else:
        # No allowlist configured — at minimum reject private addresses and
        # hosts that resolve to private IPs (SSRF defense in depth).
        if _resolves_to_private(host):
            raise ValueError("canvas_base_url resolves to a private/internal address")

    return parsed.geturl().rstrip("/")
