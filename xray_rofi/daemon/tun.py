"""Polkit privilege elevation and TUN mode controller (`TunRunner`)."""

from __future__ import annotations

import asyncio
from collections import deque
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from typing import Any


def find_polkit_elevator(project_root: str) -> list[str] | None:
    """Find a working Polkit privilege elevator (`pkexec` if setuid, otherwise `run0`)."""
    for candidate in ("/run/wrappers/bin/pkexec", shutil.which("pkexec") or ""):
        if candidate and os.path.isfile(candidate):
            try:
                st = os.stat(candidate)
                if st.st_mode & stat.S_ISUID:
                    return [candidate, "env", f"PYTHONPATH={project_root}"]
            except OSError:
                pass

    run0_bin = shutil.which("run0") or "/run/current-system/sw/bin/run0"
    if os.path.isfile(run0_bin) and os.access(run0_bin, os.X_OK):
        return [
            run0_bin,
            "--pipe",
            "--description=Xray-Rofi TUN Network Interface",
            f"--setenv=PYTHONPATH={project_root}",
        ]

    return None


class TunRunner:
    """Manages the persistent `xray_rofi.pkhelper` root co-process for TUN mode."""

    def __init__(self, logs: deque[str]) -> None:
        self.logs = logs
        self.proc: asyncio.subprocess.Process | None = None
        self.running: bool = False
        self.pid: int | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    async def _read_stderr(self, stream: asyncio.StreamReader) -> None:
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    self.logs.append(f"[polkit] {text}")
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def ensure_helper(self) -> tuple[bool, str]:
        if (
            self.proc is not None
            and self.proc.returncode is None
            and self.proc.stdin is not None
            and self.proc.stdout is not None
        ):
            return True, "ok"

        await self.close()

        project_root = str(Path(__file__).resolve().parents[2])
        cmd: list[str] = []
        if os.geteuid() != 0:
            elevator = find_polkit_elevator(project_root)
            if not elevator:
                return False, "Neither run0 nor setuid pkexec found; cannot elevate for TUN mode"
            cmd.extend(elevator)

        cmd.extend([sys.executable, "-m", "xray_rofi.pkhelper", "--stdio"])
        self.logs.append(f"[supervisor] Requesting Polkit elevation for TUN mode via {cmd[0]}...")

        try:
            self.proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            if self.proc.stderr is not None:
                self._stderr_task = asyncio.create_task(self._read_stderr(self.proc.stderr))
        except Exception as exc:
            return False, f"Failed to spawn pkhelper: {exc}"

        return True, "ok"

    async def send_cmd(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            return {"ok": False, "error": "pkhelper process not connected"}

        raw_req = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            self.proc.stdin.write(raw_req)
            await self.proc.stdin.drain()
            line_bytes = await asyncio.wait_for(self.proc.stdout.readline(), timeout=60.0)
            if not line_bytes:
                await asyncio.sleep(0.05)
                recent_err = [l for l in self.logs if l.startswith("[polkit]")]
                detail = recent_err[-1] if recent_err else "authentication cancelled or denied"
                return {"ok": False, "error": f"Polkit helper closed ({detail})"}
            line = line_bytes.decode("utf-8", errors="replace").strip()
            return json.loads(line)
        except Exception as exc:
            return {"ok": False, "error": f"pkhelper IPC error: {exc}"}

    async def start(self, config: dict[str, Any], xray_bin: str) -> tuple[bool, str]:
        ok, err = await self.ensure_helper()
        if not ok:
            return False, err

        resp = await self.send_cmd({"cmd": "start", "config": config, "xray_bin": xray_bin})
        if not resp.get("ok"):
            await self.close()
            self.running = False
            self.pid = None
            return False, resp.get("error", "Failed to start TUN Xray")

        mixed_port: int | None = None
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") == "mixed" and inbound.get("port"):
                mixed_port = int(inbound["port"])
                break

        for _ in range(50):
            status_resp = await self.send_cmd({"cmd": "status"})
            if not status_resp.get("running"):
                break
            if mixed_port is not None:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", mixed_port),
                        timeout=0.05,
                    )
                    writer.close()
                    await writer.wait_closed()
                    break
                except Exception:
                    pass
            await asyncio.sleep(0.05)

        status_resp = await self.send_cmd({"cmd": "status"})
        for log_line in status_resp.get("logs", [])[-10:]:
            tagged = f"[tun] {log_line}"
            if tagged not in self.logs:
                self.logs.append(tagged)

        if not status_resp.get("running"):
            self.running = False
            self.pid = None
            recent = "\n".join(status_resp.get("logs", [])[-5:])
            return False, f"TUN Xray exited early: {recent}"

        self.running = True
        self.pid = status_resp.get("pid")
        return True, f"Connected TUN (PID {self.pid})"

    async def stop(self, close_helper: bool = False) -> None:
        if self.proc is not None and self.proc.returncode is None:
            try:
                await self.send_cmd({"cmd": "stop"})
            except Exception:
                pass
        self.running = False
        self.pid = None
        if close_helper:
            await self.close()

    async def close(self) -> None:
        if self.proc is not None:
            if self.proc.stdin is not None:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
            if self.proc.returncode is None:
                try:
                    self.proc.terminate()
                    await asyncio.wait_for(self.proc.wait(), timeout=2.0)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
        self.proc = None
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            self._stderr_task = None

    def is_running(self) -> bool:
        return self.running and self.proc is not None and self.proc.returncode is None
