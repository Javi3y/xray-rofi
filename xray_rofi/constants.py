"""Global constants and XDG directory paths for xray-rofi."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "xray-rofi"


def get_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def get_data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def get_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / APP_NAME


def get_runtime_dir() -> Path:
    uid = os.getuid()
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{APP_NAME}-{uid}"
    return Path(base)


def get_socket_path() -> Path:
    env_sock = os.environ.get("XRAY_ROFI_SOCKET")
    if env_sock:
        return Path(env_sock)
    return get_runtime_dir() / f"{APP_NAME}.sock"


DEFAULT_MIXED_PORT = 10808
DEFAULT_SPEEDTEST_BASE_PORT = 20000
SPEEDTEST_BASE_PORT = DEFAULT_SPEEDTEST_BASE_PORT
DEFAULT_PING_URL = "http://www.gstatic.com/generate_204"
DEFAULT_PING_TIMEOUT_SEC = 4.0
DEFAULT_USER_AGENT = "v2rayN/7.0"

CACHE_DIR = get_cache_dir()
RUNTIME_CONFIG_FILE = CACHE_DIR / "runtime_config.json"
SPEEDTEST_CONFIG_FILE = CACHE_DIR / "speedtest_config.json"
DEFAULT_SOCKET_PATH = get_socket_path()

DEFAULT_DIRECT_DOMAINS = [
    "domain:ir",
    "geosite:category-ir",
    "geosite:private",
]

DEFAULT_DIRECT_IPS = [
    "geoip:ir",
    "geoip:private",
]

PRIVATE_IP_CIDRS = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "100.64.0.0/10",
    "169.254.0.0/16",
    "fc00::/7",
    "fe80::/10",
    "::1/128",
]
