"""Core data models for xray-rofi."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import time
import uuid
from typing import Any

from xray_rofi.constants import (
    DEFAULT_DIRECT_DOMAINS,
    DEFAULT_DIRECT_IPS,
    DEFAULT_MIXED_PORT,
    DEFAULT_PING_URL,
    DEFAULT_USER_AGENT,
)


def generate_short_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class ProfileItem:
    id: str = field(default_factory=generate_short_id)
    sub_id: str = ""
    config_type: str = "vless"  # vless | vmess | trojan | ss | socks
    remarks: str = ""
    address: str = ""
    port: int = 443

    # Auth
    password: str = ""  # UUID for vless/vmess, password for trojan/ss/socks
    username: str = ""  # socks
    method: str = ""  # encryption for vless ("none" / mlkem...), scy for vmess, cipher for ss
    flow: str = ""  # e.g. "xtls-rprx-vision"
    alter_id: int = 0  # vmess aid

    # Transport (streamSettings)
    network: str = "raw"  # raw | ws | grpc | httpupgrade | xhttp | kcp
    header_type: str = "none"  # none | http | srtp | utp | wechat-video | dtls | wireguard
    host: str = ""
    path: str = ""  # ws/http path, grpc serviceName, or kcp seed
    authority: str = ""  # grpc authority
    mode: str = ""  # grpc mode ("gun"|"multi") or xhttp mode ("auto"|"packet-up"|"stream-up"|"stream-one")
    extra: str = ""  # xhttp extra JSON string

    # TLS / Reality
    stream_security: str = ""  # "" | "none" | "tls" | "reality"
    sni: str = ""
    alpn: str = ""
    fingerprint: str = ""  # chrome | firefox | safari | random | ...
    allow_insecure: bool = False
    public_key: str = ""  # reality pbk
    short_id: str = ""  # reality sid
    spider_x: str = ""  # reality spx
    mldsa65_verify: str = ""  # reality pqv
    ech_config_list: str = ""  # tls ech

    # Metadata & Telemetry
    raw_uri: str = ""
    ping_ms: int = -1  # -1 = untested, 0 = timeout/failed, >0 = latency in ms
    last_tested_at: int = 0
    added_at: int = field(default_factory=lambda: int(time.time()))

    def fingerprint_hash(self) -> str:
        """Compute deterministic hash of connection-defining fields for deduplication."""
        net = "raw" if self.network in ("", "tcp", "raw") else self.network.lower()
        sec = "" if self.stream_security in ("", "none") else self.stream_security.lower()
        payload = {
            "config_type": self.config_type.lower(),
            "address": self.address.strip().lower(),
            "port": int(self.port),
            "password": self.password,
            "username": self.username,
            "method": self.method,
            "flow": self.flow.lower(),
            "network": net,
            "header_type": self.header_type,
            "host": self.host.strip().lower(),
            "path": self.path,
            "authority": self.authority,
            "mode": self.mode,
            "stream_security": sec,
            "sni": self.sni.strip().lower(),
            "public_key": self.public_key,
            "short_id": self.short_id,
            "spider_x": self.spider_x,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileItem:
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        if "port" in filtered:
            filtered["port"] = int(filtered["port"])
        return cls(**filtered)


@dataclass
class SubscriptionItem:
    id: str = field(default_factory=generate_short_id)
    remarks: str = ""
    url: str = ""
    user_agent: str = DEFAULT_USER_AGENT
    enabled: bool = True
    upload_bytes: int = 0
    download_bytes: int = 0
    total_bytes: int = 0
    expire_timestamp: int = 0
    updated_at: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubscriptionItem:
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class Settings:
    active_profile_id: str = ""
    connection_mode: str = "proxy"  # "proxy" (mixed port, unprivileged) | "tun" (xray_tun + mixed port)
    routing_mode: str = "split"  # "split" | "global" | "direct"
    mixed_port: int = DEFAULT_MIXED_PORT
    allow_lan: bool = False
    dns_remote: str = "1.1.1.1"
    dns_direct: str = "8.8.8.8"
    enable_fragment: bool = False
    fragment_packets: str = "tlshello"
    fragment_length: str = "10-20"
    fragment_interval: str = "10-20"
    tun_name: str = "xray_tun"
    tun_mtu: int = 9000
    ping_url: str = DEFAULT_PING_URL
    direct_domains: list[str] = field(default_factory=lambda: list(DEFAULT_DIRECT_DOMAINS))
    direct_ips: list[str] = field(default_factory=lambda: list(DEFAULT_DIRECT_IPS))
    block_ads: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
