"""VMess share link parser and serializer (v2rayN Base64 JSON and standard URI)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlsplit

from xray_rofi.core.fmt.base import b64_decode, b64_encode, get_q, parse_stream_query
from xray_rofi.core.models import ProfileItem


def parse_vmess(uri: str) -> ProfileItem | None:
    raw = uri.strip()
    if not raw.lower().startswith("vmess://"):
        return None
    body = raw[8:]
    if "@" in body.split("#")[0]:
        res = _parse_std_vmess(raw)
        if res is not None:
            return res
    return _parse_v2rayn_vmess(raw, body)


def _parse_v2rayn_vmess(raw_uri: str, body: str) -> ProfileItem | None:
    try:
        decoded = b64_decode(body)
        data = json.loads(decoded)
        if not isinstance(data, dict):
            return None

        address = str(data.get("add", "")).strip()
        port = int(data.get("port", 0))
        uuid_str = str(data.get("id", "")).strip()
        if not address or port <= 0 or not uuid_str:
            return None

        net = str(data.get("net", "tcp")).lower()
        if net in ("tcp", "raw", ""):
            net = "raw"
        elif net == "splithttp":
            net = "xhttp"

        header_type = str(data.get("type", "none"))
        host = str(data.get("host", ""))
        path = str(data.get("path", ""))
        tls_val = str(data.get("tls", "")).lower()
        sec = "tls" if tls_val == "tls" else ("reality" if tls_val == "reality" else "")

        item = ProfileItem(
            config_type="vmess",
            remarks=str(data.get("ps", "")),
            address=address,
            port=port,
            password=uuid_str,
            alter_id=int(data.get("aid", 0) or 0),
            method=str(data.get("scy", "") or "auto"),
            network=net,
            header_type=header_type if net in ("raw", "kcp") else "none",
            host=host if net != "grpc" else "",
            authority=host if net == "grpc" else "",
            path=path,
            mode=header_type if net in ("grpc", "xhttp") and header_type != "none" else "",
            stream_security=sec,
            sni=str(data.get("sni", "")),
            alpn=str(data.get("alpn", "")),
            fingerprint=str(data.get("fp", "")),
            allow_insecure=str(data.get("insecure", "0")) in ("1", "true", "True"),
            raw_uri=raw_uri,
        )
        return item
    except Exception:
        return None


def _parse_std_vmess(raw_uri: str) -> ProfileItem | None:
    try:
        parsed = urlsplit(raw_uri)
        if not parsed.hostname or not parsed.username:
            return None
        item = ProfileItem(
            config_type="vmess",
            address=parsed.hostname,
            port=parsed.port or 443,
            password=unquote(parsed.username),
            remarks=unquote(parsed.fragment or ""),
            raw_uri=raw_uri,
        )
        q = parse_qs(parsed.query, keep_blank_values=True)
        item.method = get_q(q, "encryption", "auto")
        parse_stream_query(parsed.query, item, default_security="")
        return item
    except Exception:
        return None


def to_vmess_uri(item: ProfileItem) -> str:
    net = "tcp" if item.network in ("", "raw", "tcp") else item.network
    type_field = "none"
    if net in ("tcp", "kcp"):
        type_field = item.header_type or "none"
    elif net in ("grpc", "xhttp"):
        type_field = item.mode or "none"

    payload = {
        "v": "2",
        "ps": item.remarks,
        "add": item.address,
        "port": str(item.port),
        "id": item.password,
        "aid": str(item.alter_id),
        "scy": item.method or "auto",
        "net": net,
        "type": type_field,
        "host": item.authority if net == "grpc" else item.host,
        "path": item.path,
        "tls": item.stream_security,
        "sni": item.sni,
        "alpn": item.alpn,
        "fp": item.fingerprint,
        "insecure": "1" if item.allow_insecure else "0",
    }
    raw_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return f"vmess://{b64_encode(raw_json)}"
