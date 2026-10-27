"""Tests for Phase 3: Xray v26 Config Compiler validated against real `xray run -test`."""

import json
import shutil
import subprocess
from typing import Any

import pytest

from xray_rofi.core.builder import build_client_config, build_speedtest_config
from xray_rofi.core.models import ProfileItem, Settings


def _validate_with_xray(config: dict[str, Any]) -> None:
    xray_bin = shutil.which("xray")
    if not xray_bin:
        pytest.skip("xray binary not found in PATH")
    proc = subprocess.run(
        [xray_bin, "run", "-test"],
        input=json.dumps(config).encode("utf-8"),
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"xray validation failed:\n{proc.stdout.decode()}\n{proc.stderr.decode()}"


def test_build_vless_reality_proxy_and_tun_configs() -> None:
    prof = ProfileItem(
        config_type="vless",
        remarks="DE-Reality",
        address="edge.example.com",
        port=443,
        password="b831381d-6324-4d53-ad4f-8cda48b30811",
        flow="xtls-rprx-vision",
        network="raw",
        stream_security="reality",
        sni="www.microsoft.com",
        fingerprint="chrome",
        public_key="j8v2d7f9g0h1j2k3l4m5n6p7q8r9s0t1u2v3w4x5y6A",
        short_id="a1b2c3d4",
        spider_x="/",
    )

    # 1. Proxy mode (mixed port 10808, Iran split routing)
    settings_proxy = Settings(connection_mode="proxy", routing_mode="split", mixed_port=10808)
    cfg_proxy = build_client_config(prof, settings_proxy)
    assert len(cfg_proxy["inbounds"]) == 1
    assert cfg_proxy["inbounds"][0]["protocol"] == "mixed"
    assert cfg_proxy["inbounds"][0]["port"] == 10808
    _validate_with_xray(cfg_proxy)

    # 2. TUN mode + TLS Fragment enabled
    settings_tun = Settings(connection_mode="tun", routing_mode="split", enable_fragment=True)
    cfg_tun = build_client_config(prof, settings_tun)
    assert any(i["protocol"] == "tun" for i in cfg_tun["inbounds"])
    assert any(o["tag"] == "fragment" for o in cfg_tun["outbounds"])
    _validate_with_xray(cfg_tun)


def test_build_vmess_ws_trojan_grpc_xhttp_and_ss() -> None:
    profiles = [
        ProfileItem(
            config_type="vmess",
            address="vmess.example.com",
            port=443,
            password="b831381d-6324-4d53-ad4f-8cda48b30811",
            network="ws",
            host="vmess.example.com",
            path="/ws",
            stream_security="tls",
        ),
        ProfileItem(
            config_type="trojan",
            address="trojan.example.com",
            port=443,
            password="MyTrojanPassword",
            network="grpc",
            path="grpc_service",
            stream_security="tls",
        ),
        ProfileItem(
            config_type="vless",
            address="xhttp.example.com",
            port=443,
            password="b831381d-6324-4d53-ad4f-8cda48b30811",
            network="xhttp",
            path="/xhttp",
            mode="packet-up",
            stream_security="tls",
        ),
        ProfileItem(
            config_type="ss",
            address="ss.example.com",
            port=8388,
            method="2022-blake3-aes-128-gcm",
            password="j8v2d7f9g0h1j2k3l4m5n6p7q8r9s0t1u2v3w4x5y6A=",
        ),
    ]

    settings = Settings(connection_mode="proxy", routing_mode="global")
    for p in profiles:
        cfg = build_client_config(p, settings)
        _validate_with_xray(cfg)

    # Also test multi-port speedtest config for all 4 profiles together
    speed_cfg, port_map = build_speedtest_config(profiles, base_port=21000)
    assert len(port_map) == 4
    _validate_with_xray(speed_cfg)
