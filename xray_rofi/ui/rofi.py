"""Rofi 2.0 UI Adapter (`RofiAdapter`)."""

from __future__ import annotations

import html
import subprocess
from typing import Any

from xray_rofi.ui.theme import PALETTE, load_rofi_palette


def format_ping_badge(ping_ms: int, palette: dict[str, str] | None = None) -> str:
    """Return Pango-formatted latency badge using the active Rofi theme palette."""
    p = palette or PALETTE
    if ping_ms > 0:
        if ping_ms < 180:
            color = p["ok"]
        elif ping_ms < 350:
            color = p["warn"]
        else:
            color = p["slow"]
        return f"<span foreground='{color}'>{ping_ms:>4}ms</span>"
    if ping_ms == -1:
        return f"<span foreground='{p['muted']}'>  --  </span>"
    return f"<span foreground='{p['error']}'>  fail</span>"


def format_profile_row(
    profile: dict[str, Any],
    is_active: bool,
    is_running: bool,
    palette: dict[str, str] | None = None,
) -> str:
    """Format a single server row with Pango markup."""
    p = palette or PALETTE
    if is_active and is_running:
        dot = f"<span foreground='{p['ok']}'>●</span>"
    elif is_active:
        dot = f"<span foreground='{p['info']}'>◉</span>"
    else:
        dot = " "

    ping_str = format_ping_badge(int(profile.get("ping_ms", -1)), palette=p)
    proto = str(profile.get("config_type", "vless")).upper()
    sec = str(profile.get("stream_security", "")).lower()
    net = str(profile.get("network", "raw")).lower()
    if net == "raw":
        net = "tcp"

    tag_parts = [proto]
    if sec in ("reality", "tls"):
        tag_parts.append("Reality" if sec == "reality" else "TLS")
    if net not in ("tcp", ""):
        tag_parts.append(net)
    tag = "·".join(tag_parts)

    remarks = html.escape(profile.get("remarks") or f"{profile.get('address')}:{profile.get('port')}")
    return f"{dot} {ping_str}  <span foreground='{p['info']}'>[{html.escape(tag):<15}]</span>  {remarks}"


def format_status_header(
    state: dict[str, Any],
    banner: str = "",
    palette: dict[str, str] | None = None,
) -> str:
    """Build the Pango markup status header displayed in Rofi `-mesg`."""
    p = palette or PALETTE
    running = bool(state.get("running"))
    settings = state.get("settings", {})
    profiles = state.get("profiles", [])
    active_id = settings.get("active_profile_id", "")
    active_prof = next((prof for prof in profiles if prof.get("id") == active_id), None)
    active_name = html.escape(active_prof.get("remarks", "None")) if active_prof else "None"

    if running:
        status_badge = f"<span foreground='{p['ok']}' weight='bold'>● CONNECTED</span>"
    else:
        status_badge = f"<span foreground='{p['error']}' weight='bold'>○ DISCONNECTED</span>"

    mode = settings.get("connection_mode", "proxy")
    mixed_port = settings.get("mixed_port", 10808)
    if mode == "tun":
        mode_str = f"<span foreground='{p['accent']}' weight='bold'>TUN (xray_tun)</span> + Mixed :{mixed_port}"
    else:
        mode_str = f"<span foreground='{p['info']}' weight='bold'>Proxy</span> 127.0.0.1:{mixed_port} (SOCKS5+HTTP)"

    routing = settings.get("routing_mode", "split")
    routing_labels = {
        "split": "Split (Iran Direct)",
        "global": "Global (All Proxy)",
        "direct": "Direct (Bypass All)",
    }
    route_str = routing_labels.get(routing, routing)
    frag_str = "ON" if settings.get("enable_fragment") else "OFF"

    lines = [
        f"{status_badge}  │  <b>Server:</b> {active_name}",
        f"<b>Mode:</b> {mode_str}  │  <b>Routing:</b> {html.escape(route_str)}  │  <b>Fragment:</b> {frag_str}",
        f"<span size='small' foreground='{p['muted']}'>Enter:Connect  Alt+t:Ping  Alt+b:Best  Alt+m:Mode  Alt+r:Route  Alt+v:Paste  Alt+u:Sub  Alt+d:Del</span>",
    ]
    if banner:
        lines.insert(2, f"<span foreground='{p['warn']}' weight='bold'>{html.escape(banner)}</span>")
    return "\n".join(lines)


def run_rofi_menu(
    prompt: str,
    rows: list[str],
    mesg: str = "",
    active_row: int | None = None,
    custom_keys: bool = False,
) -> tuple[int, int]:
    """Invoke `rofi -dmenu` and return `(exit_code, selected_index)`."""
    cmd = [
        "rofi",
        "-dmenu",
        "-markup-rows",
        "-i",
        "-p",
        prompt,
        "-format",
        "i",
        "-kb-secondary-paste",
        "Insert",
        "-kb-primary-paste",
        "Control+v,Control+V,Shift+Insert",
    ]
    if mesg:
        cmd.extend(["-mesg", mesg])
    if active_row is not None and active_row >= 0:
        cmd.extend(["-a", str(active_row), "-selected-row", str(active_row)])
    if custom_keys:
        cmd.extend(
            [
                "-kb-move-word-back",
                "Control+Left",
                "-kb-custom-1",
                "Alt+t,Alt+1",
                "-kb-custom-2",
                "Alt+b,Alt+2",
                "-kb-custom-3",
                "Alt+m,Alt+3",
                "-kb-custom-4",
                "Alt+r,Alt+4",
                "-kb-custom-5",
                "Alt+v,Alt+5",
                "-kb-custom-6",
                "Alt+u,Alt+6",
                "-kb-custom-7",
                "Alt+d,Alt+7",
                "-kb-custom-8",
                "Alt+l,Alt+8",
            ]
        )

    payload = "\n".join(rows)
    res = subprocess.run(cmd, input=payload, capture_output=True, text=True, check=False)
    out = res.stdout.strip()
    idx = int(out) if out.lstrip("-").isdigit() else -1
    return res.returncode, idx


def run_rofi_input(prompt: str, mesg: str = "") -> str | None:
    """Prompt the user for a single line of text in Rofi."""
    cmd = [
        "rofi",
        "-dmenu",
        "-p",
        prompt,
        "-theme-str",
        "listview { lines: 0; }",
        "-kb-secondary-paste",
        "Insert",
        "-kb-primary-paste",
        "Control+v,Control+V,Shift+Insert",
    ]
    if mesg:
        cmd.extend(["-mesg", mesg])
    res = subprocess.run(cmd, input="", capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return None
    val = res.stdout.strip()
    return val if val else None


class RofiAdapter:
    """Pluggable Rofi 2.0 UI adapter used by `MenuController`."""

    def __init__(self, palette: dict[str, str] | None = None) -> None:
        self.palette = palette or PALETTE

    @staticmethod
    def escape(text: str) -> str:
        return html.escape(text)

    def select(
        self,
        prompt: str,
        rows: list[str],
        mesg: str = "",
        active_row: int | None = None,
        custom_keys: bool = False,
    ) -> tuple[int, int]:
        return run_rofi_menu(
            prompt=prompt,
            rows=rows,
            mesg=mesg,
            active_row=active_row,
            custom_keys=custom_keys,
        )

    def prompt_input(self, prompt: str, mesg: str = "") -> str | None:
        return run_rofi_input(prompt=prompt, mesg=mesg)

    def format_profile_row(self, profile: dict[str, Any], is_active: bool, is_running: bool) -> str:
        return format_profile_row(profile, is_active=is_active, is_running=is_running, palette=self.palette)

    def format_status_header(self, state: dict[str, Any], banner: str = "") -> str:
        return format_status_header(state, banner=banner, palette=self.palette)

    def format_toggle_row(self, running: bool) -> str:
        if running:
            return f"<span foreground='{self.palette['error']}' weight='bold'>⏹  Disconnect Xray</span>"
        return f"<span foreground='{self.palette['ok']}' weight='bold'>▶  Connect Active Server</span>"

    def format_direct_rule_row(self, rule: str, kind: str) -> str:
        color = self.palette["info"] if kind == "Domain" else self.palette["ok"]
        return (
            f"🗑  <span foreground='{color}'>[{html.escape(kind)}]</span>  {html.escape(rule)}  "
            f"<span foreground='{self.palette['muted']}'>(Enter to remove)</span>"
        )

    def format_subscription_row(self, sub: dict[str, Any], count: int) -> str:
        remarks = html.escape(sub.get("remarks") or "Subscription")
        url_short = html.escape((sub.get("url") or "")[:45])
        return (
            f"🗑  <b>{remarks}</b>  <span foreground='{self.palette['info']}'>({count} servers)</span>  "
            f"<span foreground='{self.palette['muted']}'>{url_short} (Enter to delete)</span>"
        )

    def format_settings_rows(self, settings: dict[str, Any]) -> list[str]:
        mode = settings.get("connection_mode", "proxy")
        routing = settings.get("routing_mode", "split")
        frag = "ON" if settings.get("enable_fragment") else "OFF"
        mixed_port = settings.get("mixed_port", 10808)
        direct_count = len(settings.get("direct_domains", [])) + len(settings.get("direct_ips", []))

        mode_desc = (
            f"Proxy (Unprivileged SOCKS5+HTTP on 127.0.0.1:{mixed_port})"
            if mode == "proxy"
            else f"TUN (System-Wide xray_tun via Polkit + 127.0.0.1:{mixed_port})"
        )
        return [
            "⬅  Back to Main Menu",
            f"🔀  Toggle Connection Mode  <span foreground='{self.palette['info']}'>[Current: {html.escape(mode_desc)}]</span>",
            f"🧭  Cycle Routing Mode  <span foreground='{self.palette['info']}'>[Current: {html.escape(routing.upper())}]</span> (split → global → direct)",
            f"⇄  Manage Direct Bypass List  <span foreground='{self.palette['ok']}'>({direct_count} rules)</span>...",
            f"🛡  Toggle TLS Fragment (DPI Bypass)  <span foreground='{self.palette['warn']}'>[{frag}]</span>",
            "📜  View Xray Runtime Logs...",
        ]

    def format_submenu_header(self, title: str, subtitle: str = "", banner: str = "") -> str:
        msg = f"<b>{html.escape(title)}</b>"
        if subtitle:
            msg += f"\n{html.escape(subtitle)}"
        if banner:
            msg += f"\n<span foreground='{self.palette['warn']}' weight='bold'>{html.escape(banner)}</span>"
        return msg
