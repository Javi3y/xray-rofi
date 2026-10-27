"""Concurrent Real-Ping (HTTP 204 delay) tester using a single ephemeral Xray instance."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from xray_rofi.constants import DEFAULT_PING_TIMEOUT_SEC, DEFAULT_PING_URL, SPEEDTEST_BASE_PORT, SPEEDTEST_CONFIG_FILE
from xray_rofi.core.builder import build_speedtest_config
from xray_rofi.core.models import ProfileItem
from xray_rofi.daemon.supervisor import resolve_xray_binary


async def _wait_port_ready(host: str, port: int, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=0.15,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            await asyncio.sleep(0.05)
    return False


async def _probe_single_port(
    port: int,
    ping_url: str,
    timeout: float,
    sem: asyncio.Semaphore,
) -> int:
    """Measure HTTP 204 round-trip delay in milliseconds through local mixed port.

    Returns latency in ms (>0) on success, or -1 on timeout/error.
    """
    parsed = urlsplit(ping_url)
    host = parsed.netloc or "www.gstatic.com"
    req_bytes = (
        f"GET {ping_url} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"User-Agent: Mozilla/5.0\r\n"
        f"Connection: close\r\n\r\n"
    ).encode("ascii", errors="ignore")

    async with sem:
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=1.5,
            )
            t0 = time.monotonic()
            writer.write(req_bytes)
            await writer.drain()
            status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            elapsed_ms = int(round((time.monotonic() - t0) * 1000))
            if not status_line:
                return -1
            text = status_line.decode("ascii", errors="replace")
            if text.startswith("HTTP/1.") and (" 204" in text or " 200" in text or " 301" in text or " 302" in text):
                return max(1, elapsed_ms)
            return -1
        except Exception:
            return -1
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass


async def ping_profiles(
    profiles: list[ProfileItem],
    xray_bin: str = "xray",
    ping_url: str = DEFAULT_PING_URL,
    timeout: float = DEFAULT_PING_TIMEOUT_SEC,
    base_port: int = SPEEDTEST_BASE_PORT,
    config_path: Path | None = None,
) -> dict[str, int]:
    """Test real HTTP delay for all profiles concurrently using one ephemeral Xray process."""
    if not profiles:
        return {}

    cfg_file = config_path or SPEEDTEST_CONFIG_FILE
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    speedtest_res = build_speedtest_config(profiles, base_port=base_port)
    speedtest_cfg = speedtest_res[0] if isinstance(speedtest_res, tuple) else speedtest_res

    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(speedtest_cfg, f)
    os.chmod(cfg_file, 0o600)

    resolved_xray = resolve_xray_binary(xray_bin)
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            resolved_xray,
            "run",
            "-c",
            str(cfg_file),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        ready = await _wait_port_ready("127.0.0.1", base_port, timeout=2.0)
        if not ready or proc.returncode is not None:
            return {p.id: -1 for p in profiles}

        sem = asyncio.Semaphore(32)
        tasks = [
            _probe_single_port(base_port + idx, ping_url, timeout, sem)
            for idx in range(len(profiles))
        ]
        results = await asyncio.gather(*tasks)
        return {p.id: ms for p, ms in zip(profiles, results)}
    finally:
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
        try:
            cfg_file.unlink(missing_ok=True)
        except Exception:
            pass
