"""Trojan share link parser and serializer."""

from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlsplit

from xray_rofi.core.fmt.base import (
    build_stream_query,
    encode_query_dict,
    format_host,
    get_q,
    parse_stream_query,
)
from xray_rofi.core.models import ProfileItem


def parse_trojan(uri: str) -> ProfileItem | None:
    try:
        parsed = urlsplit(uri.strip())
        if parsed.scheme.lower() != "trojan" or not parsed.hostname:
            return None
        password = unquote(parsed.username or "")
        if not password:
            return None

        item = ProfileItem(
            config_type="trojan",
            address=parsed.hostname,
            port=parsed.port or 443,
            password=password,
            remarks=unquote(parsed.fragment or ""),
            raw_uri=uri.strip(),
        )
        q = parse_qs(parsed.query, keep_blank_values=True)
        item.flow = get_q(q, "flow", "")
        parse_stream_query(parsed.query, item, default_security="tls")
        return item
    except Exception:
        return None


def to_trojan_uri(item: ProfileItem) -> str:
    params: dict[str, str] = {}
    if item.flow:
        params["flow"] = item.flow
    build_stream_query(item, params)
    query_str = encode_query_dict(params)
    remark = f"#{quote(item.remarks, safe='')}" if item.remarks else ""
    user = quote(item.password, safe="")
    host = format_host(item.address)
    return f"trojan://{user}@{host}:{item.port}?{query_str}{remark}"
