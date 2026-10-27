"""Integration tests for XrayDaemon Unix socket RPC and unprivileged Xray supervisor."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import socket

from xray_rofi.core.store import JsonStore
from xray_rofi.daemon.server import XrayDaemon
from xray_rofi.daemon.supervisor import XraySupervisor


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _send_rpc(sock_path: Path, payload: dict) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(sock_path))
    try:
        writer.write((json.dumps(payload) + "\n").encode("utf-8"))
        await writer.drain()
        line = await reader.readline()
        return json.loads(line.decode("utf-8"))
    finally:
        writer.close()
        await writer.wait_closed()


def test_daemon_rpc_lifecycle_and_unprivileged_proxy(tmp_path: Path) -> None:
    async def _run() -> None:
        store = JsonStore(config_dir=tmp_path / "config")
        store.settings.mixed_port = _find_free_port()
        store.save_settings()
        mixed_port = store.settings.mixed_port

        supervisor = XraySupervisor(runtime_config_path=tmp_path / "cache" / "runtime_config.json")
        sock_path = tmp_path / "xray-rofi.sock"
        daemon = XrayDaemon(store=store, supervisor=supervisor, socket_path=sock_path)
        await daemon.start_server()

        try:
            # 1. Import a VLESS link
            vless_uri = (
                "vless://b831381d-6324-4d53-ad4f-8cda48b30811@198.51.100.10:443"
                "?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com"
                "&fp=chrome&pbk=j8v2d7f9g0h1j2k3l4m5n6p7q8r9s0t1u2v3w4x5y6A"
                "&sid=0123456789abcdef&type=tcp#Test-Node-1"
            )
            resp = await _send_rpc(sock_path, {"cmd": "import_links", "text": vless_uri})
            assert resp["ok"] is True
            assert resp["added"] == 1

            # 2. Connect in unprivileged Proxy mode (must NOT ask for root)
            conn_resp = await _send_rpc(sock_path, {"cmd": "connect"})
            assert conn_resp["ok"] is True, f"Connect failed: {conn_resp}"
            assert conn_resp["running"] is True

            state = await _send_rpc(sock_path, {"cmd": "get_state"})
            assert state["running"] is True
            assert state["pid"] is not None

            # Verify the local mixed SOCKS5+HTTP port is actually listening
            reader, writer = await asyncio.open_connection("127.0.0.1", mixed_port)
            writer.close()
            await writer.wait_closed()

            # 3. Manage Direct Bypass list while running (live reload)
            add_rule = await _send_rpc(sock_path, {"cmd": "add_direct_rule", "rule": "digikala.com"})
            assert add_rule["ok"] is True
            assert "domain:digikala.com" in add_rule["settings"]["direct_domains"]

            rem_rule = await _send_rpc(sock_path, {"cmd": "remove_direct_rule", "rule": "domain:digikala.com"})
            assert rem_rule["ok"] is True
            assert "domain:digikala.com" not in rem_rule["settings"]["direct_domains"]

            # 4. Switch routing mode and toggle TLS fragment
            route_resp = await _send_rpc(sock_path, {"cmd": "set_routing", "routing_mode": "global"})
            assert route_resp["ok"] is True

            frag_resp = await _send_rpc(sock_path, {"cmd": "toggle_fragment"})
            assert frag_resp["ok"] is True
            assert frag_resp["tls_fragment_enabled"] is True

            # 5. Check logs
            logs_resp = await _send_rpc(sock_path, {"cmd": "get_logs"})
            assert logs_resp["ok"] is True
            assert len(logs_resp["logs"]) > 0

            # 6. Disconnect
            disc_resp = await _send_rpc(sock_path, {"cmd": "disconnect"})
            assert disc_resp["ok"] is True
            assert disc_resp["running"] is False
        finally:
            await daemon.close()

    asyncio.run(_run())
