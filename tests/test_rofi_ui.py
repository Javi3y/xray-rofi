"""Tests for Rofi UI formatting, profile sorting, and DaemonClient auto-spawn."""

from __future__ import annotations

import os
from pathlib import Path
import signal

from xray_rofi.ui.app import sort_profiles_for_display
from xray_rofi.ui.client import DaemonClient
from xray_rofi.ui.rofi import (
    RofiAdapter,
    format_ping_badge,
    format_profile_row,
    format_status_header,
)


def test_sort_and_format_profiles() -> None:
    profiles = [
        {"id": "1", "remarks": "Failed Node", "config_type": "vless", "ping_ms": 0},
        {"id": "2", "remarks": "Untested Node", "config_type": "vmess", "ping_ms": -1},
        {"id": "3", "remarks": "Slow Node", "config_type": "trojan", "ping_ms": 280},
        {"id": "4", "remarks": "Fast Node", "config_type": "vless", "stream_security": "reality", "ping_ms": 95},
    ]
    sorted_p = sort_profiles_for_display(profiles)
    assert [p["id"] for p in sorted_p] == ["4", "3", "2", "1"]

    row = format_profile_row(sorted_p[0], is_active=True, is_running=True)
    assert "95ms" in row
    assert "VLESS·Reality" in row
    assert "Fast Node" in row
    assert "●" in row

    assert "--" in format_ping_badge(-1)
    assert "fail" in format_ping_badge(0)


def test_format_status_header() -> None:
    state = {
        "running": True,
        "settings": {
            "active_profile_id": "p1",
            "connection_mode": "proxy",
            "routing_mode": "split",
            "mixed_port": 10808,
            "enable_fragment": True,
        },
        "profiles": [{"id": "p1", "remarks": "Germany Reality"}],
    }
    header = format_status_header(state, banner="Ping complete")
    assert "CONNECTED" in header
    assert "Germany Reality" in header
    assert "127.0.0.1:10808 (SOCKS5+HTTP)" in header
    assert "Split (Iran Direct)" in header
    assert "Ping complete" in header


def test_daemon_client_autospawn(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sock_path = tmp_path / "autospawn.sock"

    client = DaemonClient(socket_path=sock_path)
    state = client.call("get_state")
    assert state["ok"] is True
    assert state["running"] is False
    assert "domain:ir" in state["settings"]["direct_domains"]

    # Clean up the auto-spawned background daemon process
    client.call("shutdown_daemon")


def test_rofi_keybindings_and_flags_valid() -> None:
    import subprocess

    cmd = [
        "rofi",
        "-dmenu",
        "-markup-rows",
        "-i",
        "-p",
        "Xray",
        "-format",
        "i",
        "-kb-move-word-back",
        "Control+Left",
        "-kb-custom-1",
        "Alt+t,Alt+1",
        "-kb-custom-2",
        "Alt+b,Alt+2",
        "-kb-custom-3",
        "Alt+m,Alt+3",
        "-kb-custom-4",
        "Alt+r,Alt+4",
        "-kb-custom-5",
        "Alt+v,Alt+5",
        "-kb-custom-6",
        "Alt+u,Alt+6",
        "-kb-custom-7",
        "Alt+d,Alt+7",
        "-kb-custom-8",
        "Alt+l,Alt+8",
        "-dump-config",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Rofi rejected flags/keybindings: {res.stderr}"
