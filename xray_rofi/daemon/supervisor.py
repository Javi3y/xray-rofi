"""Xray process supervisor for unprivileged Proxy mode and Polkit TUN mode."""

from __future__ import annotations

import asyncio
from collections import deque
import json
import os
from pathlib import Path
import shutil
from typing import Any

from xray_rofi.constants import RUNTIME_CONFIG_FILE, get_data_dir
from xray_rofi.daemon.tun import TunRunner, find_polkit_elevator


def resolve_xray_binary(configured_bin: str = "xray") -> str:
    """Find the xray binary path across standard Linux paths."""
    found = shutil.which(configured_bin)
    if found:
        return found
    for fallback in ("/usr/local/bin/xray", "/usr/bin/xray", "/run/current-system/sw/bin/xray"):
        if os.path.isfile(fallback) and os.access(fallback, os.X_OK):
            return fallback
    return configured_bin


def detect_geodata_dir(xray_bin: str) -> str | None:
    """Locate the directory containing geoip.dat and geosite.dat on standard Linux distros."""
    env_dir = os.environ.get("XRAY_LOCATION_ASSET")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    candidates = [
        get_data_dir(),
        Path("/usr/local/share/xray"),
        Path("/usr/share/xray"),
        Path("/var/lib/xray"),
        Path(xray_bin).resolve().parent,
    ]
    for d in candidates:
        if (d / "geoip.dat").is_file() and (d / "geosite.dat").is_file():
            return str(d)
    return None


class XraySupervisor:
    """Manages the active Xray-core process (`proxy` mode in user-space, `tun` via `TunRunner`)."""

    def __init__(self, runtime_config_path: Path | None = None) -> None:
        self.runtime_config_path = runtime_config_path or RUNTIME_CONFIG_FILE
        self.logs: deque[str] = deque(maxlen=200)
        self.user_proc: asyncio.subprocess.Process | None = None
        self.tun = TunRunner(self.logs)
        self.current_mode: str = "proxy"
        self._log_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def _read_stream_to_logs(self, stream: asyncio.StreamReader) -> None:
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    self.logs.append(text)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def _write_user_config(self, config: dict[str, Any]) -> None:
        self.runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.runtime_config_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self.runtime_config_path)

    async def ensure_tun_session(self) -> tuple[bool, str]:
        """Ensure the privileged Polkit helper is spawned and authenticated for TUN mode."""
        async with self._lock:
            ok, err = await self.tun.ensure_helper()
            if not ok:
                return False, err
            resp = await self.tun.send_cmd({"cmd": "status"})
            if not resp.get("ok"):
                await self.tun.close()
                return False, resp.get("error", "Polkit authentication failed")
            return True, "Polkit authenticated for TUN mode"

    async def start(
        self,
        config: dict[str, Any],
        mode: str = "proxy",
        xray_bin: str = "xray",
    ) -> tuple[bool, str]:
        """Start or reload Xray in the requested mode (`proxy` or `tun`)."""
        async with self._lock:
            resolved_xray = resolve_xray_binary(xray_bin)
            if mode == "tun":
                await self._stop_user_proc_unlocked()
                self.current_mode = "tun"
                return await self.tun.start(config, resolved_xray)
            else:
                await self.tun.stop(close_helper=True)
                self.current_mode = "proxy"
                return await self._start_user_proc_unlocked(config, resolved_xray)

    async def _start_user_proc_unlocked(
        self,
        config: dict[str, Any],
        xray_bin: str,
    ) -> tuple[bool, str]:
        await self._stop_user_proc_unlocked()
        self._write_user_config(config)
        self.logs.append(f"[supervisor] Starting unprivileged Xray ({xray_bin}) in Proxy mode...")

        env = os.environ.copy()
        asset_dir = detect_geodata_dir(xray_bin)
        if asset_dir:
            env["XRAY_LOCATION_ASSET"] = asset_dir

        try:
            self.user_proc = await asyncio.create_subprocess_exec(
                xray_bin,
                "run",
                "-c",
                str(self.runtime_config_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            return False, f"Xray binary not found: {xray_bin}"
        except Exception as exc:
            return False, f"Failed to start Xray: {exc}"

        if self.user_proc.stdout is not None:
            self._log_task = asyncio.create_task(self._read_stream_to_logs(self.user_proc.stdout))

        mixed_port: int | None = None
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") == "mixed" and inbound.get("port"):
                mixed_port = int(inbound["port"])
                break

        for _ in range(50):
            if self.user_proc.returncode is not None:
                recent = "\n".join(list(self.logs)[-5:])
                return False, f"Xray exited early (code {self.user_proc.returncode}): {recent}"
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

        if self.user_proc.returncode is not None:
            recent = "\n".join(list(self.logs)[-5:])
            return False, f"Xray exited early (code {self.user_proc.returncode}): {recent}"

        return True, f"Connected (PID {self.user_proc.pid})"

    async def _stop_user_proc_unlocked(self) -> None:
        if self.user_proc is not None and self.user_proc.returncode is None:
            try:
                self.user_proc.terminate()
                await asyncio.wait_for(self.user_proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self.user_proc.kill()
                await self.user_proc.wait()
            except Exception:
                pass
        self.user_proc = None
        if self._log_task is not None:
            self._log_task.cancel()
            self._log_task = None

    async def stop(self, close_helper: bool = False) -> None:
        """Stop any running Xray instance."""
        async with self._lock:
            await self._stop_user_proc_unlocked()
            await self.tun.stop(close_helper=close_helper)
            self.logs.append("[supervisor] Xray stopped.")

    def is_running(self) -> bool:
        """Return True if Xray is currently running."""
        if self.current_mode == "tun":
            return self.tun.is_running()
        return self.user_proc is not None and self.user_proc.returncode is None

    def get_pid(self) -> int | None:
        if not self.is_running():
            return None
        if self.current_mode == "tun":
            return self.tun.pid
        return self.user_proc.pid if self.user_proc else None

    async def get_logs(self) -> list[str]:
        """Return recent log lines."""
        async with self._lock:
            if self.current_mode == "tun" and self.tun.proc is not None and self.tun.proc.returncode is None:
                resp = await self.tun.send_cmd({"cmd": "status"})
                if resp.get("ok"):
                    for line in resp.get("logs", []):
                        tagged = f"[tun] {line}"
                        if tagged not in self.logs:
                            self.logs.append(tagged)
            return list(self.logs)
