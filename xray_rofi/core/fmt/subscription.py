"""Subscription fetching, Base64 decoding, and Subscription-Userinfo header parsing."""

from __future__ import annotations

import os
import ssl
import urllib.request

from xray_rofi.constants import DEFAULT_USER_AGENT
from xray_rofi.core.fmt.base import b64_decode


def decode_subscription_body(raw_text: str) -> list[str]:
    """Decode a subscription response body (either raw share links or Base64 encoded)."""
    stripped = raw_text.strip()
    if not stripped:
        return []
    if "://" not in stripped:
        try:
            decoded = b64_decode(stripped)
            if "://" in decoded:
                stripped = decoded
        except Exception:
            pass
    return [line.strip() for line in stripped.splitlines() if line.strip() and not line.strip().startswith("#")]


def parse_subscription_userinfo(header_value: str) -> dict[str, int]:
    """Parse `Subscription-Userinfo: upload=123; download=456; total=789; expire=1700000000`."""
    result = {
        "upload_bytes": 0,
        "download_bytes": 0,
        "total_bytes": 0,
        "expire_timestamp": 0,
    }
    if not header_value:
        return result
    mapping = {
        "upload": "upload_bytes",
        "download": "download_bytes",
        "total": "total_bytes",
        "expire": "expire_timestamp",
    }
    for part in header_value.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        key = k.strip().lower()
        val_str = v.strip()
        if key in mapping and val_str.isdigit():
            result[mapping[key]] = int(val_str)
    return result


def _build_ssl_contexts() -> list[ssl.SSLContext]:
    contexts: list[ssl.SSLContext] = []
    for cafile in ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem"):
        if os.path.isfile(cafile):
            try:
                contexts.append(ssl.create_default_context(cafile=cafile))
                break
            except Exception:
                pass
    contexts.append(ssl._create_unverified_context())
    return contexts


def fetch_subscription(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    proxy_port: int | None = None,
    timeout: float = 15.0,
) -> tuple[str, dict[str, int]]:
    """Fetch subscription content via HTTP(S), with automatic proxy/direct and SSL fallbacks."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent or DEFAULT_USER_AGENT,
            "Accept": "*/*",
        },
    )

    proxy_configs: list[list[urllib.request.BaseHandler]] = [[]]
    if proxy_port and proxy_port > 0:
        proxy_url = f"http://127.0.0.1:{proxy_port}"
        proxy_configs = [
            [urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})],
            [],
        ]

    last_exc: Exception | None = None
    for handlers in proxy_configs:
        for ssl_ctx in _build_ssl_contexts():
            try:
                opener = urllib.request.build_opener(
                    *handlers,
                    urllib.request.HTTPSHandler(context=ssl_ctx),
                )
                with opener.open(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    userinfo_hdr = (
                        resp.headers.get("Subscription-Userinfo")
                        or resp.headers.get("subscription-userinfo")
                        or ""
                    )
                    return body, parse_subscription_userinfo(userinfo_hdr)
            except Exception as exc:
                last_exc = exc
                continue

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to fetch subscription")
