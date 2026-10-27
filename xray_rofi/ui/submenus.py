"""Interactive submenu workflows (Direct Rules, Subscriptions, Settings, Logs)."""

from __future__ import annotations

from typing import Any

from xray_rofi.ui.client import DaemonClient, read_clipboard
from xray_rofi.ui.rofi import RofiAdapter


def show_direct_rules_menu(client: DaemonClient, ui: RofiAdapter) -> str:
    """Interactive submenu to view, add, remove, and reset Direct Bypass domains & IPs."""
    banner = ""
    while True:
        state = client.call("get_state")
        settings = state.get("settings", {})
        domains: list[str] = settings.get("direct_domains", [])
        ips: list[str] = settings.get("direct_ips", [])

        rows: list[str] = [
            "⬅  Back to Main Menu",
            "➕  Add Direct Domain or IP/CIDR (e.g. digikala.com, 185.143.232.0/22)...",
            "↺  Reset to Default Iran Direct Rules (domain:ir, geosite:category-ir, geoip:ir)",
        ]
        rule_targets: list[str] = []
        for d in domains:
            rows.append(ui.format_direct_rule_row(d, kind="Domain"))
            rule_targets.append(d)
        for ip in ips:
            rows.append(ui.format_direct_rule_row(ip, kind="IP/Geo"))
            rule_targets.append(ip)

        mesg = ui.format_submenu_header(
            title="Direct Bypass List (Split Routing)",
            subtitle="Traffic matching these domains or IPs connects DIRECTLY without going through the proxy.",
            banner=banner,
        )

        code, idx = ui.select("Direct Rules", rows, mesg=mesg)
        if code != 0 or idx <= 0:
            return banner
        if idx == 1:
            entry = ui.prompt_input(
                "Add Direct Rule",
                "Enter a domain (e.g. digikala.com, domain:ir, geosite:category-ir) or IP/CIDR (e.g. 1.2.3.0/24, geoip:ir):",
            )
            if entry:
                resp = client.call("add_direct_rule", rule=entry)
                banner = resp.get("message") or resp.get("error", "")
        elif idx == 2:
            resp = client.call("reset_direct_rules")
            banner = resp.get("message") or resp.get("error", "")
        else:
            rule_idx = idx - 3
            if 0 <= rule_idx < len(rule_targets):
                resp = client.call("remove_direct_rule", rule=rule_targets[rule_idx])
                banner = resp.get("message") or resp.get("error", "")


def show_subscriptions_menu(client: DaemonClient, ui: RofiAdapter) -> str:
    """Interactive submenu to import share links and manage subscriptions."""
    banner = ""
    while True:
        state = client.call("get_state")
        subs: list[dict[str, Any]] = state.get("subscriptions", [])
        profiles: list[dict[str, Any]] = state.get("profiles", [])

        rows = [
            "⬅  Back to Main Menu",
            "📋  Import Share Links from Clipboard (vless://, vmess://, trojan://, ss://, socks://)",
            "✏  Paste Share Link(s) Manually...",
            "➕  Add Subscription URL (https://...)...",
            "🔄  Update All Subscriptions Now",
        ]
        for sub in subs:
            sub_id = sub.get("id", "")
            count = sum(1 for p in profiles if p.get("sub_id") == sub_id)
            rows.append(ui.format_subscription_row(sub, count))

        mesg = ui.format_submenu_header(title="Subscriptions & Link Import", banner=banner)

        code, idx = ui.select("Subscriptions", rows, mesg=mesg)
        if code != 0 or idx <= 0:
            return banner
        if idx == 1:
            clip = read_clipboard()
            if not clip:
                banner = "Clipboard is empty or wl-paste/xclip not found."
            else:
                resp = client.call("import_links", text=clip)
                banner = resp.get("message") or resp.get("error", "")
        elif idx == 2:
            text = ui.prompt_input(
                "Paste Share Link",
                "Paste vless://, vmess://, trojan://, ss://, or socks:// URI:",
            )
            if text:
                resp = client.call("import_links", text=text)
                banner = resp.get("message") or resp.get("error", "")
        elif idx == 3:
            url = ui.prompt_input("Subscription URL", "Enter https:// subscription URL:")
            if url:
                name = (
                    ui.prompt_input(
                        "Subscription Name",
                        "Optional display name (leave empty for domain name):",
                    )
                    or ""
                )
                resp = client.call("add_sub", url=url, name=name)
                banner = resp.get("message") or resp.get("error", "")
        elif idx == 4:
            resp = client.call("update_subs")
            banner = resp.get("message") or resp.get("error", "")
        else:
            sub_idx = idx - 5
            if 0 <= sub_idx < len(subs):
                resp = client.call("delete_sub", sub_id=subs[sub_idx]["id"])
                banner = resp.get("message") or resp.get("error", "")


def show_logs_menu(client: DaemonClient, ui: RofiAdapter) -> None:
    """Display recent Xray-core and supervisor logs."""
    resp = client.call("get_logs")
    logs: list[str] = resp.get("logs", [])
    rows = ["⬅  Back"] + [ui.escape(line) for line in reversed(logs[-100:])]
    ui.select("Xray Logs", rows, mesg="Most recent Xray-core logs (newest first):")


def show_settings_menu(client: DaemonClient, ui: RofiAdapter) -> str:
    """Interactive submenu for connection mode, routing mode, fragment, direct list, and logs."""
    banner = ""
    while True:
        state = client.call("get_state")
        settings = state.get("settings", {})
        mode = settings.get("connection_mode", "proxy")
        routing = settings.get("routing_mode", "split")

        rows = ui.format_settings_rows(settings)
        mesg = ui.format_submenu_header(
            title="Settings",
            subtitle=(
                "• Proxy Mode runs 100% unprivileged (never asks for root/Polkit).\n"
                "• TUN Mode creates a virtual network interface (xray_tun) and asks for Polkit once."
            ),
            banner=banner,
        )

        code, idx = ui.select("Settings", rows, mesg=mesg)
        if code != 0 or idx <= 0:
            return banner
        if idx == 1:
            target_mode = "tun" if mode == "proxy" else "proxy"
            resp = client.call("set_mode", mode=target_mode)
            banner = resp.get("message") or resp.get("error", "")
        elif idx == 2:
            order = ["split", "global", "direct"]
            next_route = order[(order.index(routing) + 1) % len(order)] if routing in order else "split"
            resp = client.call("set_routing", routing_mode=next_route)
            banner = resp.get("message") or resp.get("error", "")
        elif idx == 3:
            banner = show_direct_rules_menu(client, ui)
        elif idx == 4:
            resp = client.call("toggle_fragment")
            banner = resp.get("message") or resp.get("error", "")
        elif idx == 5:
            show_logs_menu(client, ui)
