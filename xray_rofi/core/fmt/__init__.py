"""Unified dispatcher for parsing and serializing proxy share links."""

from __future__ import annotations

from xray_rofi.core.fmt.shadowsocks import (
    parse_shadowsocks,
    parse_socks,
    to_shadowsocks_uri,
    to_socks_uri,
)
from xray_rofi.core.fmt.subscription import decode_subscription_body
from xray_rofi.core.fmt.trojan import parse_trojan, to_trojan_uri
from xray_rofi.core.fmt.vless import parse_vless, to_vless_uri
from xray_rofi.core.fmt.vmess import parse_vmess, to_vmess_uri
from xray_rofi.core.models import ProfileItem


def parse_link(uri: str) -> ProfileItem | None:
    s = uri.strip()
    if not s or "://" not in s:
        return None
    scheme = s.split("://", 1)[0].lower()
    if scheme == "vless":
        return parse_vless(s)
    if scheme == "vmess":
        return parse_vmess(s)
    if scheme == "trojan":
        return parse_trojan(s)
    if scheme == "ss":
        return parse_shadowsocks(s)
    if scheme in ("socks", "socks5", "socks4"):
        return parse_socks(s)
    return None


def to_link(item: ProfileItem) -> str | None:
    ct = item.config_type.lower()
    if ct == "vless":
        return to_vless_uri(item)
    if ct == "vmess":
        return to_vmess_uri(item)
    if ct == "trojan":
        return to_trojan_uri(item)
    if ct == "ss":
        return to_shadowsocks_uri(item)
    if ct == "socks":
        return to_socks_uri(item)
    return None


def parse_links_text(text: str) -> list[ProfileItem]:
    lines = decode_subscription_body(text)
    items: list[ProfileItem] = []
    for line in lines:
        parsed = parse_link(line)
        if parsed is not None:
            items.append(parsed)
    return items
