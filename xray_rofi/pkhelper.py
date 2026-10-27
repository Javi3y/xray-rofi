"""Privileged Polkit helper for Xray TUN mode.

This module is ONLY invoked (via `run0 --pipe` or `pkexec`) when the user
explicitly selects TUN mode. In normal Proxy mode (SOCKS5 + HTTP mixed port),
this module is NEVER executed.

It communicates with the unprivileged `xray-rofid` daemon over `--stdio` pipes
(with `run0 --pipe`) or an inherited `socketpair()` file descriptor (`--fd`).
If the unprivileged daemon exits or crashes, the pipe/socket closes (`EOF`),
and this helper immediately terminates the root `xray` process and removes
`/run/xray-rofi/config.json`.
"""

from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from typing import Any, TextIO


RUN_DIR = Path("/run/xray-rofi")
CONFIG_PATH = RUN_DIR / "config.json"


class RootXrayController:
    """Manages the root Xray process for TUN mode."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen[str] | None = None
        self.logs: deque[str] = deque(maxlen=200)
        self._lock = threading.Lock()

    def _reader_thread(self, pipe: Any) -> None:
        try:
            for line in iter(pipe.readline, ""):
                if not line:
                    break
                with self._lock:
                    self.logs.append(line.rstrip("\r\n"))
        except Exception:
            pass

    def write_config(self, config: dict[str, Any]) -> None:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(RUN_DIR, 0o700)
        fd, tmp_name = tempfile.mkstemp(dir=str(RUN_DIR), prefix=".config-", suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, CONFIG_PATH)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def start(self, config: dict[str, Any], xray_bin: str) -> dict[str, Any]:
        self.stop()
        self.write_config(config)
        self.proc = subprocess.Popen(
            [xray_bin, "run", "-c", str(CONFIG_PATH)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if self.proc.stdout is not None:
            t = threading.Thread(target=self._reader_thread, args=(self.proc.stdout,), daemon=True)
            t.start()
        return {"ok": True, "pid": self.proc.pid}

    def stop(self) -> dict[str, Any]:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=1.0)
            except Exception:
                pass
        self.proc = None
        if CONFIG_PATH.exists():
            try:
                CONFIG_PATH.unlink(missing_ok=True)
            except Exception:
                pass
        return {"ok": True}

    def status(self) -> dict[str, Any]:
        running = self.proc is not None and self.proc.poll() is None
        pid = self.proc.pid if running and self.proc else None
        with self._lock:
            logs = list(self.logs)
        return {"ok": True, "running": running, "pid": pid, "logs": logs}


def main() -> None:
    parser = argparse.ArgumentParser(description="Privileged Polkit helper for xray-rofi TUN mode.")
    parser.add_argument("--fd", type=int, default=None, help="Inherited socketpair file descriptor.")
    parser.add_argument("--stdio", action="store_true", help="Use stdin/stdout pipes (for run0 --pipe).")
    args = parser.parse_args()

    controller = RootXrayController()

    def _cleanup_handler(_signum: int, _frame: Any) -> None:
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup_handler)
    signal.signal(signal.SIGINT, _cleanup_handler)

    sock: socket.socket | None = None
    rfile: TextIO
    wfile: TextIO

    if args.fd is not None:
        sock = socket.fromfd(args.fd, socket.AF_UNIX, socket.SOCK_STREAM)
        os.close(args.fd)
        rfile = sock.makefile("r", encoding="utf-8", buffering=1)
        wfile = sock.makefile("w", encoding="utf-8", buffering=1)
    else:
        rfile = sys.stdin
        out_fd = os.dup(sys.stdout.fileno())
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        wfile = os.fdopen(out_fd, "w", encoding="utf-8", buffering=1)

    try:
        for line in rfile:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                cmd = req.get("cmd")
                if cmd == "start":
                    resp = controller.start(req["config"], req.get("xray_bin", "xray"))
                elif cmd == "stop":
                    resp = controller.stop()
                elif cmd == "status":
                    resp = controller.status()
                else:
                    resp = {"ok": False, "error": f"Unknown command: {cmd}"}
            except Exception as exc:
                resp = {"ok": False, "error": str(exc)}

            wfile.write(json.dumps(resp) + "\n")
            wfile.flush()
    finally:
        controller.stop()
        try:
            wfile.close()
            if sock is not None:
                rfile.close()
                sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
