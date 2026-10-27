"""Shadowsocks (SIP002, 2022, and Legacy Base64) and SOCKS share link parsers."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlsplit

from xray_rofi.core.fmt.base import b64_decode, b64_encode, format_host
from xray_rofi.core.models import ProfileItem


def parse_shadowsocks(uri: str) -> ProfileItem | None:
    raw = uri.strip()
    if not raw.lower().startswith("ss://"):
        return None
    before_hash = raw.split("#", 1)[0]
    if "@" in before_hash:
        return _parse_ss_sip002(raw)
    return _parse_ss_legacy(raw)


def _parse_ss_sip002(raw: str) -> ProfileItem | None:
    try:
        parsed = urlsplit(raw)
        if not parsed.hostname or not parsed.port:
            return None
        remarks = unquote(parsed.fragment or "")

        if parsed.password is not None:
            method = unquote(parsed.username or "")
            password = unquote(parsed.password)
        else:
            decoded_user = b64_decode(unquote(parsed.username or ""))
            if ":" not in decoded_user:
                return None
            method, password = decoded_user.split(":", 1)

        if not method or not password:
            return None

        return ProfileItem(
            config_type="ss",
            remarks=remarks,
            address=parsed.hostname,
            port=parsed.port,
            method=method,
            password=password,
            raw_uri=raw,
        )
    except Exception:
        return None


def _parse_ss_legacy(raw: str) -> ProfileItem | None:
    try:
        body = raw[5:]
        remarks = ""
        if "#" in body:
            body, frag = body.split("#", 1)
            remarks = unquote(frag)
        decoded = b64_decode(body.rstrip("/"))
        if "@" not in decoded or ":" not in decoded:
            return None
        userinfo, hostport = decoded.rsplit("@", 1)
        method, password = userinfo.split(":", 1)
        parsed = urlsplit(f"ss://{hostport}")
        if not parsed.hostname or not parsed.port:
            return None
        return ProfileItem(
            config_type="ss",
            remarks=remarks,
            address=parsed.hostname,
            port=parsed.port,
            method=method,
            password=password,
            raw_uri=raw,
        )
    except Exception:
        return None


def to_shadowsocks_uri(item: ProfileItem) -> str:
    userinfo = b64_encode(f"{item.method}:{item.password}", urlsafe=True)
    host = format_host(item.address)
    remark = f"#{quote(item.remarks, safe='')}" if item.remarks else ""
    return f"ss://{userinfo}@{host}:{item.port}{remark}"


def parse_socks(uri: str) -> ProfileItem | None:
    try:
        raw = uri.strip()
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in ("socks", "socks5", "socks4") or not parsed.hostname:
            return None
        port = parsed.port or 1080
        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")

        # v2rayN base64 user:pass in username
        if username and not password:
            try:
                decoded = b64_decode(username)
                if ":" in decoded:
                    username, password = decoded.split(":", 1)
            except Exception:
                pass

        return ProfileItem(
            config_type="socks",
            remarks=unquote(parsed.fragment or ""),
            address=parsed.hostname,
            port=port,
            username=username,
            password=password,
            raw_uri=raw,
        )
    except Exception:
        return None


def to_socks_uri(item: ProfileItem) -> str:
    host = format_host(item.address)
    remark = f"#{quote(item.remarks, safe='')}" if item.remarks else ""
    if item.username or item.password:
        auth = f"{quote(item.username, safe='')}:{quote(item.password, safe='')}@"
    else:
        auth = ""
    return f"socks5://{auth}{host}:{item.port}{remark}"
