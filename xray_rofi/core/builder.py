"""Xray v26+ configuration compiler (`config.json` and speedtest config)."""

from __future__ import annotations

from typing import Any

from xray_rofi.constants import DEFAULT_SPEEDTEST_BASE_PORT, PRIVATE_IP_CIDRS
from xray_rofi.core.models import ProfileItem, Settings
from xray_rofi.core.outbound import build_proxy_outbound


def _filter_geodata_rules(items: list[str], use_geodata: bool) -> list[str]:
    if use_geodata:
        return list(items)
    return [i for i in items if not i.startswith(("geosite:", "geoip:", "ext:"))]


def build_client_config(
    profile: ProfileItem,
    settings: Settings,
    use_geodata: bool = True,
) -> dict[str, Any]:
    """Compile a full Xray v26+ client configuration dictionary for `profile` and `settings`."""
    is_tun = settings.connection_mode == "tun"
    listen_addr = "0.0.0.0" if settings.allow_lan else "127.0.0.1"

    # 1. Inbounds: Always include mixed (SOCKS5 + HTTP on the same port)
    mixed_inbound: dict[str, Any] = {
        "tag": "mixed-in",
        "port": int(settings.mixed_port),
        "listen": listen_addr,
        "protocol": "mixed",
        "settings": {"udp": True},
        "sniffing": {
            "enabled": True,
            "destOverride": ["http", "tls", "quic"],
            "routeOnly": True,
        },
    }
    inbounds: list[dict[str, Any]] = [mixed_inbound]

    if is_tun:
        inbounds.append(
            {
                "tag": "tun",
                "protocol": "tun",
                "settings": {
                    "name": settings.tun_name or "xray_tun",
                    "MTU": int(settings.tun_mtu or 9000),
                    "gateway": ["172.18.0.1/30", "fdfe:dcba:9876::1/126"],
                    "dns": [settings.dns_remote or "1.1.1.1", settings.dns_direct or "8.8.8.8"],
                    "autoSystemRoutingTable": ["0.0.0.0/0", "::/0"],
                    "autoOutboundsInterface": "auto",
                    "autoSystemDnsToGateway": True,
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
            }
        )

    # 2. Outbounds: First outbound is the default fallback in Xray
    proxy_outbound = build_proxy_outbound(
        profile=profile,
        tag="proxy",
        enable_fragment=settings.enable_fragment,
    )
    direct_outbound: dict[str, Any] = {"tag": "direct", "protocol": "freedom"}
    block_outbound: dict[str, Any] = {"tag": "block", "protocol": "blackhole"}

    if settings.routing_mode == "direct":
        outbounds: list[dict[str, Any]] = [direct_outbound, proxy_outbound, block_outbound]
    else:
        outbounds = [proxy_outbound, direct_outbound, block_outbound]

    if settings.enable_fragment:
        outbounds.append(
            {
                "tag": "fragment",
                "protocol": "freedom",
                "settings": {
                    "fragment": {
                        "packets": settings.fragment_packets or "tlshello",
                        "length": settings.fragment_length or "10-20",
                        "interval": settings.fragment_interval or "10-20",
                    }
                },
            }
        )

    if is_tun:
        outbounds.append({"tag": "dns-out", "protocol": "dns"})

    # 3. Routing
    rules: list[dict[str, Any]] = []
    if is_tun:
        rules.append({"inboundTag": ["tun"], "port": 53, "outboundTag": "dns-out"})

    if settings.routing_mode == "split":
        if settings.block_ads and use_geodata:
            rules.append({"domain": ["geosite:category-ads-all"], "outboundTag": "block"})

        direct_domains = _filter_geodata_rules(settings.direct_domains, use_geodata)
        if direct_domains:
            rules.append({"domain": direct_domains, "outboundTag": "direct"})

        direct_ips = _filter_geodata_rules(settings.direct_ips, use_geodata)
        if not use_geodata:
            direct_ips.extend(c for c in PRIVATE_IP_CIDRS if c not in direct_ips)
        if direct_ips:
            rules.append({"ip": direct_ips, "outboundTag": "direct"})
    elif settings.routing_mode == "global":
        if use_geodata:
            rules.append({"ip": ["geoip:private"], "outboundTag": "direct"})
        else:
            rules.append({"ip": list(PRIVATE_IP_CIDRS), "outboundTag": "direct"})

    # 4. DNS
    dns_servers: list[Any] = [settings.dns_remote or "1.1.1.1"]
    if settings.routing_mode == "split":
        direct_domains_for_dns = _filter_geodata_rules(settings.direct_domains, use_geodata)
        if direct_domains_for_dns:
            dns_servers.append(
                {
                    "address": settings.dns_direct or "8.8.8.8",
                    "domains": direct_domains_for_dns,
                }
            )

    return {
        "log": {"loglevel": "warning"},
        "dns": {"servers": dns_servers},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": rules,
        },
    }


def build_speedtest_config(
    profiles: list[ProfileItem],
    base_port: int = DEFAULT_SPEEDTEST_BASE_PORT,
    enable_fragment: bool = False,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Build a single ephemeral Xray config mapping each profile to a dedicated local mixed port."""
    inbounds: list[dict[str, Any]] = []
    outbounds: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    port_map: dict[str, int] = {}

    for idx, prof in enumerate(profiles):
        port = base_port + idx
        in_tag = f"in_{idx}"
        out_tag = f"proxy_{idx}"

        inbounds.append(
            {
                "tag": in_tag,
                "port": port,
                "listen": "127.0.0.1",
                "protocol": "mixed",
                "settings": {"udp": False},
            }
        )
        outbounds.append(
            build_proxy_outbound(
                profile=prof,
                tag=out_tag,
                enable_fragment=enable_fragment,
            )
        )
        rules.append({"inboundTag": [in_tag], "outboundTag": out_tag})
        port_map[prof.id] = port

    if enable_fragment:
        outbounds.append(
            {
                "tag": "fragment",
                "protocol": "freedom",
                "settings": {
                    "fragment": {
                        "packets": "tlshello",
                        "length": "10-20",
                        "interval": "10-20",
                    }
                },
            }
        )

    outbounds.append({"tag": "direct", "protocol": "freedom"})

    config = {
        "log": {"loglevel": "none"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "AsIs",
            "rules": rules,
        },
    }
    return config, port_map
