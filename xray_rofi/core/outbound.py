"""Xray v26+ outbound and streamSettings compiler."""

from __future__ import annotations

import json
from typing import Any

from xray_rofi.core.models import ProfileItem


def build_proxy_outbound(
    profile: ProfileItem,
    tag: str = "proxy",
    enable_fragment: bool = False,
) -> dict[str, Any]:
    """Convert a ProfileItem into an Xray v26 outbound object."""
    ct = profile.config_type.lower()
    protocol = "shadowsocks" if ct == "ss" else ct

    settings: dict[str, Any] = {
        "address": profile.address,
        "port": int(profile.port),
    }

    if ct == "vless":
        settings["id"] = profile.password
        settings["encryption"] = profile.method or "none"
        if profile.flow:
            settings["flow"] = profile.flow
    elif ct == "vmess":
        settings["id"] = profile.password
        settings["security"] = profile.method or "auto"
    elif ct == "trojan":
        settings["password"] = profile.password
        if profile.flow:
            settings["flow"] = profile.flow
    elif ct == "ss":
        settings["method"] = profile.method or "none"
        settings["password"] = profile.password
    elif ct == "socks":
        if profile.username:
            settings["user"] = profile.username
            settings["pass"] = profile.password

    stream_settings = _build_stream_settings(profile, enable_fragment=enable_fragment)

    return {
        "tag": tag,
        "protocol": protocol,
        "settings": settings,
        "streamSettings": stream_settings,
    }


def _build_stream_settings(
    profile: ProfileItem,
    enable_fragment: bool = False,
) -> dict[str, Any]:
    net = profile.network.lower() if profile.network else "raw"
    if net in ("tcp", "raw", ""):
        net = "raw"
    elif net == "splithttp":
        net = "xhttp"

    stream: dict[str, Any] = {
        "network": net,
    }

    sni = profile.sni or profile.host or profile.address

    if net == "raw":
        if profile.header_type == "http":
            headers: dict[str, Any] = {}
            if profile.host:
                headers["Host"] = [h.strip() for h in profile.host.split(",") if h.strip()]
            stream["rawSettings"] = {
                "header": {
                    "type": "http",
                    "request": {
                        "path": [profile.path or "/"],
                        "headers": headers,
                    },
                }
            }
    elif net == "ws":
        ws_settings: dict[str, Any] = {}
        if profile.path:
            ws_settings["path"] = profile.path
        if profile.host:
            ws_settings["host"] = profile.host
        stream["wsSettings"] = ws_settings
    elif net == "httpupgrade":
        hu_settings: dict[str, Any] = {}
        if profile.path:
            hu_settings["path"] = profile.path
        if profile.host:
            hu_settings["host"] = profile.host
        stream["httpupgradeSettings"] = hu_settings
    elif net == "xhttp":
        xhttp_settings: dict[str, Any] = {
            "mode": profile.mode or "auto",
        }
        if profile.path:
            xhttp_settings["path"] = profile.path
        if profile.host:
            xhttp_settings["host"] = profile.host
        if profile.extra:
            try:
                extra_obj = json.loads(profile.extra)
                if isinstance(extra_obj, dict):
                    xhttp_settings["extra"] = extra_obj
            except Exception:
                pass
        stream["xhttpSettings"] = xhttp_settings
    elif net == "grpc":
        grpc_settings: dict[str, Any] = {}
        if profile.path:
            grpc_settings["serviceName"] = profile.path
        if profile.authority:
            grpc_settings["authority"] = profile.authority
        if profile.mode == "multi":
            grpc_settings["multiMode"] = True
        stream["grpcSettings"] = grpc_settings
    elif net == "kcp":
        kcp_settings: dict[str, Any] = {}
        if profile.path:
            kcp_settings["seed"] = profile.path
        stream["kcpSettings"] = kcp_settings

    sec = profile.stream_security.lower() if profile.stream_security else "none"
    if sec == "tls":
        stream["security"] = "tls"
        tls_settings: dict[str, Any] = {
            "serverName": sni,
            "allowInsecure": bool(profile.allow_insecure),
            "fingerprint": profile.fingerprint or "chrome",
        }
        if profile.alpn:
            tls_settings["alpn"] = [a.strip() for a in profile.alpn.split(",") if a.strip()]
        if profile.ech_config_list:
            tls_settings["echConfigList"] = profile.ech_config_list
        stream["tlsSettings"] = tls_settings
    elif sec == "reality":
        stream["security"] = "reality"
        reality_settings: dict[str, Any] = {
            "serverName": sni,
            "fingerprint": profile.fingerprint or "chrome",
            "publicKey": profile.public_key,
            "shortId": profile.short_id,
            "spiderX": profile.spider_x or "/",
        }
        if profile.mldsa65_verify:
            reality_settings["mldsa65Verify"] = profile.mldsa65_verify
        stream["realitySettings"] = reality_settings
    else:
        stream["security"] = "none"

    if enable_fragment:
        stream["sockopt"] = {"dialerProxy": "fragment"}

    return stream
