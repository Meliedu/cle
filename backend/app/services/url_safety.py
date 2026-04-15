"""URL validation helpers for SSRF mitigation."""

import ipaddress
import socket
from urllib.parse import urlparse


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


def validate_canvas_base_url(url: str, allowed_hosts: str | None = None) -> str:
    """Validate a Canvas LMS base URL: HTTPS, allowlisted host, no private IPs.

    ``allowed_hosts`` is an optional comma-separated allowlist; when omitted
    the caller is telling us no allowlist is configured and we fall back to
    rejecting hosts that resolve to private/internal addresses.

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

    allowed = [
        h.strip().lower()
        for h in (allowed_hosts or "").split(",")
        if h.strip()
    ]
    if allowed:
        if not any(host == a or host.endswith("." + a) for a in allowed):
            raise ValueError(f"canvas_base_url host '{host}' not in allowlist")
    else:
        # No allowlist configured — at minimum reject private addresses and
        # hosts that resolve to private IPs (SSRF defense in depth).
        if _resolves_to_private(host):
            raise ValueError("canvas_base_url resolves to a private/internal address")

    return parsed.geturl().rstrip("/")


def validate_frontend_url(url: str) -> str:
    """Validate ``frontend_url`` used for post-OAuth redirects.

    The value is operator-configured (not attacker-controlled), but we still
    fail fast at startup if it's empty or points somewhere obviously wrong,
    so we don't build an open-redirect-looking URL at runtime. Rules:
    - must be non-empty
    - scheme must be https, OR http with a loopback/localhost host for dev
    - must have a hostname

    Returns the normalized URL (trailing slash stripped).
    """
    if not url:
        raise ValueError("frontend_url is required")
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("frontend_url is missing a hostname")
    if parsed.scheme == "https":
        pass
    elif parsed.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
        pass
    else:
        raise ValueError(
            "frontend_url must use https:// (http:// is only allowed for localhost)"
        )
    return parsed.geturl().rstrip("/")
