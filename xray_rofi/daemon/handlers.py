"""Application service handlers for `xray-rofid` RPC commands."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlsplit

from xray_rofi.constants import DEFAULT_PING_TIMEOUT_SEC
from xray_rofi.core.builder import build_client_config
from xray_rofi.core.fmt import parse_links_text
from xray_rofi.core.fmt.subscription import fetch_subscription
from xray_rofi.core.models import ProfileItem, SubscriptionItem
from xray_rofi.core.store import JsonStore
from xray_rofi.daemon.supervisor import XraySupervisor
from xray_rofi.daemon.tester import ping_profiles


class DaemonService:
    """Executes all daemon business logic commands (`cmd_<name>`)."""

    def __init__(
        self,
        store: JsonStore,
        supervisor: XraySupervisor,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self.store = store
        self.supervisor = supervisor
        self.stop_event = stop_event

    def _find_profile(self, profile_id: str | None) -> ProfileItem | None:
        if not self.store.profiles:
            return None
        if profile_id:
            found = self.store.get_profile(profile_id)
            if found:
                return found
        if self.store.settings.active_profile_id:
            found = self.store.get_profile(self.store.settings.active_profile_id)
            if found:
                return found
        return self.store.profiles[0]

    async def _start_with_geodata_fallback(self, profile: ProfileItem) -> tuple[bool, str]:
        settings = self.store.settings
        config = build_client_config(profile, settings, use_geodata=True)
        ok, msg = await self.supervisor.start(config, mode=settings.connection_mode)
        if not ok and ("geosite.dat" in msg or "geoip.dat" in msg):
            config_no_geo = build_client_config(profile, settings, use_geodata=False)
            ok, msg = await self.supervisor.start(config_no_geo, mode=settings.connection_mode)
        return ok, msg

    async def _reload_if_running(self) -> tuple[bool, str]:
        if not self.supervisor.is_running():
            return True, "Updated"
        profile = self._find_profile(self.store.settings.active_profile_id)
        if profile is None:
            await self.supervisor.stop()
            return True, "Stopped (no active profile)"
        return await self._start_with_geodata_fallback(profile)

    async def dispatch(self, req: dict[str, Any]) -> dict[str, Any]:
        cmd = str(req.get("cmd", ""))
        handler = getattr(self, f"cmd_{cmd}", None)
        if handler is None:
            return {"ok": False, "error": f"Unknown command: {cmd}"}
        try:
            return await handler(req)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def cmd_ping_daemon(self, _req: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "running": self.supervisor.is_running()}

    async def cmd_shutdown_daemon(self, _req: dict[str, Any]) -> dict[str, Any]:
        if self.stop_event is not None:
            self.stop_event.set()
        return {"ok": True, "message": "Daemon shutting down"}

    async def cmd_get_state(self, _req: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "running": self.supervisor.is_running(),
            "pid": self.supervisor.get_pid(),
            "settings": self.store.settings.to_dict(),
            "profiles": [p.to_dict() for p in self.store.profiles],
            "subscriptions": [s.to_dict() for s in self.store.subscriptions],
        }

    async def cmd_connect(self, req: dict[str, Any]) -> dict[str, Any]:
        profile = self._find_profile(req.get("profile_id"))
        if profile is None:
            return {"ok": False, "error": "No servers available. Import a link or subscription first."}
        self.store.settings.active_profile_id = profile.id
        self.store.save_settings()

        ok, msg = await self._start_with_geodata_fallback(profile)
        return {
            "ok": ok,
            "message": msg if ok else "",
            "error": "" if ok else msg,
            "running": self.supervisor.is_running(),
            "active_profile_id": profile.id,
        }

    async def cmd_disconnect(self, _req: dict[str, Any]) -> dict[str, Any]:
        await self.supervisor.stop()
        return {"ok": True, "message": "Disconnected", "running": False}

    async def cmd_set_mode(self, req: dict[str, Any]) -> dict[str, Any]:
        new_mode = req.get("mode", "proxy")
        if new_mode not in ("proxy", "tun"):
            return {"ok": False, "error": f"Invalid connection mode: {new_mode}"}
        prev_mode = self.store.settings.connection_mode
        self.store.settings.connection_mode = new_mode
        self.store.save_settings()

        if self.supervisor.is_running():
            ok, msg = await self._reload_if_running()
            if not ok:
                self.store.settings.connection_mode = prev_mode
                self.store.save_settings()
                await self._reload_if_running()
                return {"ok": False, "error": msg}
            return {"ok": True, "message": f"Mode set to {new_mode.upper()} ({msg})"}

        if new_mode == "tun":
            ok, msg = await self.supervisor.ensure_tun_session()
            if not ok:
                self.store.settings.connection_mode = prev_mode
                self.store.save_settings()
                return {"ok": False, "error": msg}
            return {"ok": True, "message": f"Mode set to TUN ({msg})"}

        await self.supervisor.stop(close_helper=True)
        return {"ok": True, "message": "Mode set to PROXY"}

    async def cmd_set_routing(self, req: dict[str, Any]) -> dict[str, Any]:
        routing_mode = req.get("routing_mode", "split")
        if routing_mode not in ("split", "global", "direct"):
            return {"ok": False, "error": f"Invalid routing mode: {routing_mode}"}
        self.store.settings.routing_mode = routing_mode
        self.store.save_settings()
        ok, msg = await self._reload_if_running()
        return {"ok": ok, "message": f"Routing set to {routing_mode}", "error": "" if ok else msg}

    async def cmd_toggle_fragment(self, _req: dict[str, Any]) -> dict[str, Any]:
        self.store.settings.enable_fragment = not self.store.settings.enable_fragment
        self.store.save_settings()
        ok, msg = await self._reload_if_running()
        state_str = "ON" if self.store.settings.enable_fragment else "OFF"
        return {
            "ok": ok,
            "enable_fragment": self.store.settings.enable_fragment,
            "tls_fragment_enabled": self.store.settings.enable_fragment,
            "message": f"TLS Fragment {state_str}",
            "error": "" if ok else msg,
        }

    async def cmd_import_links(self, req: dict[str, Any]) -> dict[str, Any]:
        text = str(req.get("text", "")).strip()
        if text.startswith(("http://", "https://")) and "\n" not in text:
            return await self.cmd_add_sub({"url": text})
        parsed = parse_links_text(text)
        if not parsed:
            return {"ok": False, "error": "No valid share links found in input."}
        added, dupes = self.store.add_profiles(parsed)
        return {
            "ok": True,
            "added": added,
            "duplicates": dupes,
            "total_parsed": len(parsed),
            "message": f"Imported {added} new server(s) ({dupes} duplicates skipped)",
        }

    async def cmd_add_sub(self, req: dict[str, Any]) -> dict[str, Any]:
        url = str(req.get("url", "")).strip()
        name = str(req.get("name", "")).strip()
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "error": "Subscription URL must start with http:// or https://"}
        proxy_port = self.store.settings.mixed_port if self.supervisor.is_running() else None
        body, userinfo = await asyncio.to_thread(fetch_subscription, url, proxy_port=proxy_port)
        profiles = parse_links_text(body)
        if not profiles:
            return {"ok": False, "error": "Subscription returned 0 valid servers."}
        default_name = urlsplit(url).hostname or "Subscription"
        sub = SubscriptionItem(
            remarks=name or default_name,
            url=url,
            enabled=True,
            updated_at=int(time.time()),
            **userinfo,
        )
        self.store.upsert_subscription(sub)
        self.store.replace_subscription_profiles(sub.id, profiles)
        return {
            "ok": True,
            "sub": sub.to_dict(),
            "count": len(profiles),
            "message": f"Added subscription '{sub.remarks}' ({len(profiles)} servers)",
        }

    async def cmd_update_subs(self, _req: dict[str, Any]) -> dict[str, Any]:
        subs = self.store.subscriptions
        if not subs:
            return {"ok": False, "error": "No subscriptions configured."}
        updated_subs = 0
        total_profiles = 0
        errors: list[str] = []
        proxy_port = self.store.settings.mixed_port if self.supervisor.is_running() else None
        for sub in list(subs):
            if not sub.enabled:
                continue
            try:
                body, userinfo = await asyncio.to_thread(
                    fetch_subscription, sub.url, sub.user_agent, proxy_port
                )
                profiles = parse_links_text(body)
                if profiles:
                    sub.updated_at = int(time.time())
                    sub.upload_bytes = userinfo.get("upload_bytes", sub.upload_bytes)
                    sub.download_bytes = userinfo.get("download_bytes", sub.download_bytes)
                    sub.total_bytes = userinfo.get("total_bytes", sub.total_bytes)
                    sub.expire_timestamp = userinfo.get("expire_timestamp", sub.expire_timestamp)
                    self.store.upsert_subscription(sub)
                    self.store.replace_subscription_profiles(sub.id, profiles)
                    updated_subs += 1
                    total_profiles += len(profiles)
            except Exception as exc:
                errors.append(f"{sub.remarks}: {exc}")

        if updated_subs == 0 and errors:
            return {"ok": False, "error": "; ".join(errors)}
        return {
            "ok": True,
            "updated_subs": updated_subs,
            "total_profiles": total_profiles,
            "message": f"Updated {updated_subs} subscription(s) ({total_profiles} servers)",
        }

    async def cmd_delete_profile(self, req: dict[str, Any]) -> dict[str, Any]:
        profile_id = req.get("profile_id", "")
        if self.store.settings.active_profile_id == profile_id and self.supervisor.is_running():
            await self.supervisor.stop()
        removed = self.store.delete_profile(profile_id)
        return {"ok": removed, "message": "Server deleted" if removed else "Server not found"}

    async def cmd_delete_sub(self, req: dict[str, Any]) -> dict[str, Any]:
        removed = self.store.delete_subscription(req.get("sub_id", ""))
        return {"ok": removed, "message": "Subscription deleted" if removed else "Subscription not found"}

    async def cmd_add_direct_rule(self, req: dict[str, Any]) -> dict[str, Any]:
        rule = str(req.get("rule", "")).strip()
        if not rule:
            return {"ok": False, "error": "Rule cannot be empty"}
        self.store.add_direct_rule(rule)
        await self._reload_if_running()
        return {
            "ok": True,
            "settings": self.store.settings.to_dict(),
            "message": f"Added direct rule: {rule}",
        }

    async def cmd_remove_direct_rule(self, req: dict[str, Any]) -> dict[str, Any]:
        rule = str(req.get("rule", "")).strip()
        self.store.remove_direct_rule(rule)
        await self._reload_if_running()
        return {
            "ok": True,
            "settings": self.store.settings.to_dict(),
            "message": f"Removed direct rule: {rule}",
        }

    async def cmd_reset_direct_rules(self, _req: dict[str, Any]) -> dict[str, Any]:
        self.store.reset_direct_rules()
        await self._reload_if_running()
        return {
            "ok": True,
            "settings": self.store.settings.to_dict(),
            "message": "Reset direct rules to Iran defaults",
        }

    async def cmd_ping_all(self, _req: dict[str, Any]) -> dict[str, Any]:
        profiles = self.store.profiles
        if not profiles:
            return {"ok": False, "error": "No servers to ping."}
        pings = await ping_profiles(
            profiles,
            ping_url=self.store.settings.ping_url,
            timeout=DEFAULT_PING_TIMEOUT_SEC,
        )
        self.store.update_pings(pings)
        alive = sum(1 for ms in pings.values() if ms > 0)
        return {
            "ok": True,
            "pings": pings,
            "alive": alive,
            "total": len(pings),
            "message": f"Ping complete: {alive}/{len(pings)} reachable",
        }

    async def cmd_connect_best(self, req: dict[str, Any]) -> dict[str, Any]:
        profiles = self.store.profiles
        if not profiles:
            return {"ok": False, "error": "No servers available."}
        alive = [p for p in profiles if p.ping_ms > 0]
        if not alive or req.get("force_ping", False):
            pings = await ping_profiles(
                profiles,
                ping_url=self.store.settings.ping_url,
                timeout=DEFAULT_PING_TIMEOUT_SEC,
            )
            self.store.update_pings(pings)
            alive = [p for p in self.store.profiles if p.ping_ms > 0]
        if not alive:
            return {"ok": False, "error": "No reachable servers found during ping test."}
        best = min(alive, key=lambda p: p.ping_ms)
        return await self.cmd_connect({"profile_id": best.id})

    async def cmd_get_logs(self, _req: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "logs": await self.supervisor.get_logs()}
