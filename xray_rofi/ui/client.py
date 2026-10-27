"""Unix Domain Socket RPC client and OS clipboard helper for the UI layer."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

from xray_rofi.constants import DEFAULT_SOCKET_PATH


class DaemonClient:
    """Synchronous Unix Domain Socket client with automatic daemon startup."""

    def __init__(self, socket_path: Path | None = None) -> None:
        self.socket_path = socket_path or DEFAULT_SOCKET_PATH

    def _raw_request(self, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(self.socket_path))
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            buf = bytearray()
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            if not buf:
                return {"ok": False, "error": "Empty response from daemon"}
            line = buf.split(b"\n", 1)[0].decode("utf-8", errors="replace")
            return json.loads(line)

    def ensure_daemon(self) -> None:
        """Ensure `xray-rofid` is running, spawning it in the background if needed."""
        try:
            resp = self._raw_request({"cmd": "ping_daemon"}, timeout=1.0)
            if resp.get("ok"):
                return
        except Exception:
            pass

        subprocess.Popen(
            [sys.executable, "-m", "xray_rofi.daemon.server", "--socket", str(self.socket_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                resp = self._raw_request({"cmd": "ping_daemon"}, timeout=0.5)
                if resp.get("ok"):
                    return
            except Exception:
                time.sleep(0.05)

    def call(self, cmd: str, **kwargs: Any) -> dict[str, Any]:
        self.ensure_daemon()
        payload = {"cmd": cmd, **kwargs}
        try:
            return self._raw_request(payload, timeout=45.0)
        except Exception as exc:
            return {"ok": False, "error": f"Daemon communication error: {exc}"}


def read_clipboard() -> str:
    """Read text from the system clipboard, preferring buffers that contain proxy/HTTP links."""
    candidates = [
        ["wl-paste", "--no-newline"],
        ["xclip", "-o", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--output"],
        ["wl-paste", "--primary", "--no-newline"],
        ["xclip", "-o", "-selection", "primary"],
    ]
    schemes = ("vless://", "vmess://", "trojan://", "ss://", "socks://", "socks5://", "https://", "http://")
    fallback = ""
    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0, check=False)
                val = res.stdout.strip()
                if res.returncode == 0 and val:
                    if any(s in val.lower() for s in schemes):
                        return val
                    if not fallback:
                        fallback = val
            except Exception:
                continue
    return fallback
