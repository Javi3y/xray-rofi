"""Shared URI parsing and query parameter utilities for proxy share links."""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, quote, unquote

from xray_rofi.core.models import ProfileItem


def b64_decode(data: str) -> str:
    """Decode standard or URL-safe Base64 string with automatic padding recovery."""
    cleaned = data.strip().replace("\r", "").replace("\n", "").replace(" ", "")
    if not cleaned:
        return ""
    padding = (-len(cleaned)) % 4
    if padding:
        cleaned += "=" * padding
    try:
        return base64.urlsafe_b64decode(cleaned.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return base64.b64decode(cleaned.encode("ascii")).decode("utf-8", errors="replace")


def b64_encode(text: str, urlsafe: bool = False) -> str:
    raw = text.encode("utf-8")
    if urlsafe:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return base64.b64encode(raw).decode("ascii")


def format_host(address: str) -> str:
    if ":" in address and not (address.startswith("[") and address.endswith("]")):
        return f"[{address}]"
    return address


def get_q(query: dict[str, list[str]], key: str, default: str = "") -> str:
    vals = query.get(key)
    if not vals:
        return default
    return unquote(vals[0])


def parse_stream_query(query_str: str, item: ProfileItem, default_security: str = "") -> None:
    """Populate transport and TLS/Reality fields on ProfileItem from URI query string."""
    q = parse_qs(query_str, keep_blank_values=True)

    sec = get_q(q, "security", default_security).lower()
    item.stream_security = "" if sec == "none" else sec
    item.sni = get_q(q, "sni") or get_q(q, "peer")
    item.fingerprint = get_q(q, "fp")
    item.alpn = get_q(q, "alpn")
    item.public_key = get_q(q, "pbk")
    item.short_id = get_q(q, "sid")
    item.spider_x = get_q(q, "spx")
    item.mldsa65_verify = get_q(q, "pqv")
    item.ech_config_list = get_q(q, "ech")

    insecure_val = get_q(q, "allowInsecure") or get_q(q, "insecure")
    if insecure_val in ("1", "true", "True"):
        item.allow_insecure = True

    net = get_q(q, "type", "raw").lower()
    if net in ("tcp", "raw", ""):
        net = "raw"
    elif net == "splithttp":
        net = "xhttp"
    item.network = net

    if net == "raw":
        item.header_type = get_q(q, "headerType", "none")
        item.host = get_q(q, "host")
        item.path = get_q(q, "path")
    elif net in ("ws", "httpupgrade", "http", "h2"):
        item.host = get_q(q, "host")
        item.path = get_q(q, "path")
    elif net == "xhttp":
        item.host = get_q(q, "host")
        item.path = get_q(q, "path")
        item.mode = get_q(q, "mode", "auto")
        item.extra = get_q(q, "extra")
    elif net == "grpc":
        item.path = get_q(q, "serviceName") or get_q(q, "path")
        item.authority = get_q(q, "authority") or get_q(q, "host")
        item.mode = get_q(q, "mode", "gun")
    elif net == "kcp":
        item.header_type = get_q(q, "headerType", "none")
        item.path = get_q(q, "seed")


def build_stream_query(item: ProfileItem, params: dict[str, str]) -> None:
    """Populate URI query dictionary from ProfileItem transport and TLS/Reality fields."""
    if item.stream_security:
        params["security"] = item.stream_security
    else:
        params["security"] = "none"

    if item.sni:
        params["sni"] = item.sni
    if item.fingerprint:
        params["fp"] = item.fingerprint
    if item.alpn:
        params["alpn"] = item.alpn
    if item.public_key:
        params["pbk"] = item.public_key
    if item.short_id:
        params["sid"] = item.short_id
    if item.spider_x:
        params["spx"] = item.spider_x
    if item.mldsa65_verify:
        params["pqv"] = item.mldsa65_verify
    if item.ech_config_list:
        params["ech"] = item.ech_config_list
    if item.allow_insecure:
        params["allowInsecure"] = "1"

    net = "tcp" if item.network in ("", "raw", "tcp") else item.network
    params["type"] = net

    if net == "tcp":
        if item.header_type and item.header_type != "none":
            params["headerType"] = item.header_type
        if item.host:
            params["host"] = item.host
        if item.path:
            params["path"] = item.path
    elif net in ("ws", "httpupgrade", "http"):
        if item.host:
            params["host"] = item.host
        if item.path:
            params["path"] = item.path
    elif net == "xhttp":
        if item.host:
            params["host"] = item.host
        if item.path:
            params["path"] = item.path
        if item.mode:
            params["mode"] = item.mode
        if item.extra:
            params["extra"] = item.extra
    elif net == "grpc":
        if item.path:
            params["serviceName"] = item.path
        if item.authority:
            params["authority"] = item.authority
        if item.mode:
            params["mode"] = item.mode
    elif net == "kcp":
        if item.header_type and item.header_type != "none":
            params["headerType"] = item.header_type
        if item.path:
            params["seed"] = item.path


def encode_query_dict(params: dict[str, str]) -> str:
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v != "")
