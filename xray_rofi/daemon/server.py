"""Asyncio Unix Domain Socket server (`xray-rofid`)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
from typing import Any

from xray_rofi.constants import DEFAULT_SOCKET_PATH
from xray_rofi.core.store import JsonStore
from xray_rofi.daemon.handlers import DaemonService
from xray_rofi.daemon.supervisor import XraySupervisor


class XrayDaemon:
    """Unix Domain Socket transport server wrapping `DaemonService`."""

    def __init__(
        self,
        store: JsonStore | None = None,
        supervisor: XraySupervisor | None = None,
        socket_path: Path | None = None,
    ) -> None:
        self.store = store or JsonStore()
        self.supervisor = supervisor or XraySupervisor()
        self.socket_path = socket_path or DEFAULT_SOCKET_PATH
        self._server: asyncio.AbstractServer | None = None
        self.stop_event: asyncio.Event | None = None
        self.service = DaemonService(store=self.store, supervisor=self.supervisor)

    async def handle_request(self, req: dict[str, Any]) -> dict[str, Any]:
        """Process a single JSON-RPC command from the client."""
        self.service.stop_event = self.stop_event
        return await self.service.dispatch(req)

    async def _client_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not line:
                return
            req = json.loads(line.decode("utf-8", errors="replace"))
            resp = await self.handle_request(req)
            writer.write((json.dumps(resp) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception as exc:
            try:
                err_resp = {"ok": False, "error": str(exc)}
                writer.write((json.dumps(err_resp) + "\n").encode("utf-8"))
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start_server(self) -> None:
        """Start listening on the Unix Domain Socket."""
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass
        self._server = await asyncio.start_unix_server(
            self._client_connected,
            path=str(self.socket_path),
        )
        os.chmod(self.socket_path, 0o600)

    async def close(self) -> None:
        """Stop server and any running Xray instance."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        await self.supervisor.stop(close_helper=True)
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass


async def _run_daemon(socket_path: Path) -> None:
    daemon = XrayDaemon(socket_path=socket_path)
    stop_event = asyncio.Event()
    daemon.stop_event = stop_event
    await daemon.start_server()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    finally:
        await daemon.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="xray-rofid background daemon")
    parser.add_argument(
        "--socket",
        type=Path,
        default=DEFAULT_SOCKET_PATH,
        help="Unix domain socket path",
    )
    args = parser.parse_args()
    asyncio.run(_run_daemon(args.socket))


if __name__ == "__main__":
    main()
