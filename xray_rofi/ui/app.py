"""Main UI Menu Controller (`xray-rofi`)."""

from __future__ import annotations

from typing import Any

from xray_rofi.ui.client import DaemonClient, read_clipboard
from xray_rofi.ui.rofi import RofiAdapter
from xray_rofi.ui.submenus import (
    show_direct_rules_menu,
    show_logs_menu,
    show_settings_menu,
    show_subscriptions_menu,
)


def sort_profiles_for_display(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort profiles: positive ping ascending first, then untested (-1), then failed (<=0)."""

    def _sort_key(p: dict[str, Any]) -> tuple[int, int, str]:
        ms = int(p.get("ping_ms", -1))
        if ms > 0:
            return (0, ms, p.get("remarks", ""))
        if ms == -1:
            return (1, 999999, p.get("remarks", ""))
        return (2, 999999, p.get("remarks", ""))

    return sorted(profiles, key=_sort_key)


class MenuController:
    """Drives the interactive menu workflow using a pluggable menu adapter (`RofiAdapter`)."""

    def __init__(
        self,
        client: DaemonClient | None = None,
        ui: RofiAdapter | None = None,
    ) -> None:
        self.client = client or DaemonClient()
        self.ui = ui or RofiAdapter()

    def _handle_hotkey(
        self,
        code: int,
        idx: int,
        action_count: int,
        settings: dict[str, Any],
        sorted_profiles: list[dict[str, Any]],
    ) -> str:
        if code == 10:  # Alt+t: Ping All
            resp = self.client.call("ping_all")
            return resp.get("message") or resp.get("error", "")
        if code == 11:  # Alt+b: Connect Best
            resp = self.client.call("connect_best")
            return resp.get("message") or resp.get("error", "")
        if code == 12:  # Alt+m: Toggle Mode
            mode = settings.get("connection_mode", "proxy")
            resp = self.client.call("set_mode", mode="tun" if mode == "proxy" else "proxy")
            return resp.get("message") or resp.get("error", "")
        if code == 13:  # Alt+r: Cycle Routing
            routing = settings.get("routing_mode", "split")
            order = ["split", "global", "direct"]
            next_route = order[(order.index(routing) + 1) % len(order)] if routing in order else "split"
            resp = self.client.call("set_routing", routing_mode=next_route)
            return resp.get("message") or resp.get("error", "")
        if code == 14:  # Alt+v: Paste from Clipboard
            clip = read_clipboard()
            if not clip:
                return "Clipboard is empty."
            resp = self.client.call("import_links", text=clip)
            return resp.get("message") or resp.get("error", "")
        if code == 15:  # Alt+u: Update Subscriptions
            resp = self.client.call("update_subs")
            return resp.get("message") or resp.get("error", "")
        if code == 16:  # Alt+d: Delete highlighted server
            srv_idx = idx - action_count
            if 0 <= srv_idx < len(sorted_profiles):
                resp = self.client.call("delete_profile", profile_id=sorted_profiles[srv_idx]["id"])
                return resp.get("message") or resp.get("error", "")
            return "Highlight a server row first to delete it (Alt+d)."
        if code == 17:  # Alt+l: Logs
            show_logs_menu(self.client, self.ui)
        return ""

    def run(self) -> None:
        """Run the main interactive menu loop."""
        banner = ""

        while True:
            state = self.client.call("get_state")
            if not state.get("ok"):
                self.ui.select("Xray Error", ["Exit"], mesg=self.ui.escape(state.get("error", "Daemon error")))
                return

            running = bool(state.get("running"))
            settings = state.get("settings", {})
            active_id = settings.get("active_profile_id", "")
            sorted_profiles = sort_profiles_for_display(state.get("profiles", []))

            action_rows = [
                self.ui.format_toggle_row(running),
                "⚡  Ping All Servers (Real HTTP 204 Delay)",
                "🚀  Connect Fastest Server (Best Ping)",
                "📥  Subscriptions &amp; Import Links...",
                "⇄  Direct Bypass List (Domains &amp; IPs)...",
                "⚙  Settings &amp; Logs (Mode / Routing / Fragment)...",
            ]

            server_rows: list[str] = []
            active_row_idx: int | None = None
            for i, prof in enumerate(sorted_profiles):
                is_act = prof.get("id") == active_id
                if is_act:
                    active_row_idx = len(action_rows) + i
                server_rows.append(self.ui.format_profile_row(prof, is_active=is_act, is_running=running))

            all_rows = action_rows + server_rows
            mesg = self.ui.format_status_header(state, banner=banner)
            banner = ""

            code, idx = self.ui.select(
                "Xray",
                all_rows,
                mesg=mesg,
                active_row=active_row_idx,
                custom_keys=True,
            )

            if code == 1 or (idx < 0 and code == 0):
                break

            if 10 <= code <= 17:
                banner = self._handle_hotkey(code, idx, len(action_rows), settings, sorted_profiles)
                continue

            if idx == 0:
                resp = self.client.call("disconnect" if running else "connect")
                banner = resp.get("message") or resp.get("error", "")
            elif idx == 1:
                resp = self.client.call("ping_all")
                banner = resp.get("message") or resp.get("error", "")
            elif idx == 2:
                resp = self.client.call("connect_best")
                banner = resp.get("message") or resp.get("error", "")
            elif idx == 3:
                banner = show_subscriptions_menu(self.client, self.ui)
            elif idx == 4:
                banner = show_direct_rules_menu(self.client, self.ui)
            elif idx == 5:
                banner = show_settings_menu(self.client, self.ui)
            else:
                srv_idx = idx - len(action_rows)
                if 0 <= srv_idx < len(sorted_profiles):
                    chosen = sorted_profiles[srv_idx]
                    resp = self.client.call("connect", profile_id=chosen["id"])
                    if resp.get("ok"):
                        break
                    banner = resp.get("error", "Connection failed")


def main() -> None:
    """Entry point for `xray-rofi`."""
    MenuController().run()
