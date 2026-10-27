"""VLESS share link parser and serializer."""

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


def parse_vless(uri: str) -> ProfileItem | None:
    try:
        parsed = urlsplit(uri.strip())
        if parsed.scheme.lower() != "vless" or not parsed.hostname:
            return None
        port = parsed.port or 443
        uuid_str = unquote(parsed.username or "")
        if not uuid_str:
            return None

        item = ProfileItem(
            config_type="vless",
            address=parsed.hostname,
            port=port,
            password=uuid_str,
            remarks=unquote(parsed.fragment or ""),
            raw_uri=uri.strip(),
        )
        q = parse_qs(parsed.query, keep_blank_values=True)
        item.method = get_q(q, "encryption", "none")
        item.flow = get_q(q, "flow", "")
        parse_stream_query(parsed.query, item, default_security="")
        return item
    except Exception:
        return None


def to_vless_uri(item: ProfileItem) -> str:
    params: dict[str, str] = {
        "encryption": item.method if item.method else "none",
    }
    if item.flow:
        params["flow"] = item.flow
    build_stream_query(item, params)
    query_str = encode_query_dict(params)
    remark = f"#{quote(item.remarks, safe='')}" if item.remarks else ""
    user = quote(item.password, safe="")
    host = format_host(item.address)
    return f"vless://{user}@{host}:{item.port}?{query_str}{remark}"
