"""Atomic JSON file store for settings.json and profiles.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.parse import urlsplit

from xray_rofi.constants import DEFAULT_DIRECT_DOMAINS, DEFAULT_DIRECT_IPS, get_config_dir
from xray_rofi.core.models import ProfileItem, Settings, SubscriptionItem


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


class JsonStore:
    """Manages in-memory state backed by settings.json and profiles.json."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or get_config_dir()
        self.settings_path = self.config_dir / "settings.json"
        self.profiles_path = self.config_dir / "profiles.json"

        self.settings: Settings = Settings()
        self.subscriptions: list[SubscriptionItem] = []
        self.profiles: list[ProfileItem] = []
        self.load()

    def load(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if self.settings_path.exists():
            try:
                raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.settings = Settings.from_dict(raw)
            except Exception:
                self.settings = Settings()
        else:
            self.save_settings()

        if self.profiles_path.exists():
            try:
                raw = json.loads(self.profiles_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.subscriptions = [
                        SubscriptionItem.from_dict(s) for s in raw.get("subscriptions", [])
                    ]
                    self.profiles = [
                        ProfileItem.from_dict(p) for p in raw.get("profiles", [])
                    ]
            except Exception:
                self.subscriptions = []
                self.profiles = []
        else:
            self.save_profiles()

    def save_settings(self) -> None:
        _atomic_write_json(self.settings_path, self.settings.to_dict())

    def save_profiles(self) -> None:
        payload = {
            "subscriptions": [s.to_dict() for s in self.subscriptions],
            "profiles": [p.to_dict() for p in self.profiles],
        }
        _atomic_write_json(self.profiles_path, payload)

    def get_profile(self, profile_id: str) -> ProfileItem | None:
        for p in self.profiles:
            if p.id == profile_id:
                return p
        return None

    def get_subscription(self, sub_id: str) -> SubscriptionItem | None:
        for s in self.subscriptions:
            if s.id == sub_id:
                return s
        return None

    def add_profiles(self, items: list[ProfileItem], sub_id: str = "") -> tuple[int, int]:
        """Add profiles with deduplication. Returns (added_count, duplicate_count)."""
        existing_hashes = {p.fingerprint_hash() for p in self.profiles}
        existing_ids = {p.id for p in self.profiles}
        added = 0
        duplicates = 0

        for item in items:
            if sub_id:
                item.sub_id = sub_id
            fp_hash = item.fingerprint_hash()
            if fp_hash in existing_hashes:
                duplicates += 1
                continue
            while item.id in existing_ids:
                item.id = ProfileItem().id
            existing_hashes.add(fp_hash)
            existing_ids.add(item.id)
            self.profiles.append(item)
            added += 1

        if added > 0:
            if not self.settings.active_profile_id and self.profiles:
                self.settings.active_profile_id = self.profiles[0].id
                self.save_settings()
            self.save_profiles()
        return added, duplicates

    def replace_subscription_profiles(self, sub_id: str, new_items: list[ProfileItem]) -> int:
        """Replace all profiles belonging to a subscription, preserving active profile selection if matched."""
        old_sub_profiles = {p.fingerprint_hash(): p for p in self.profiles if p.sub_id == sub_id}
        self.profiles = [p for p in self.profiles if p.sub_id != sub_id]
        other_hashes = {p.fingerprint_hash() for p in self.profiles}
        existing_ids = {p.id for p in self.profiles}

        added = 0
        for item in new_items:
            item.sub_id = sub_id
            fp_hash = item.fingerprint_hash()
            if fp_hash in other_hashes:
                continue
            # Preserve ID and previous ping result if identical node existed in this subscription
            if fp_hash in old_sub_profiles:
                old = old_sub_profiles[fp_hash]
                item.id = old.id
                if item.ping_ms == -1 and old.ping_ms != -1:
                    item.ping_ms = old.ping_ms
                    item.last_tested_at = old.last_tested_at
            while item.id in existing_ids:
                item.id = ProfileItem().id
            other_hashes.add(fp_hash)
            existing_ids.add(item.id)
            self.profiles.append(item)
            added += 1

        # Verify active_profile_id still exists
        if self.settings.active_profile_id and not self.get_profile(self.settings.active_profile_id):
            self.settings.active_profile_id = self.profiles[0].id if self.profiles else ""
            self.save_settings()

        self.save_profiles()
        return added

    def delete_profile(self, profile_id: str) -> bool:
        before = len(self.profiles)
        self.profiles = [p for p in self.profiles if p.id != profile_id]
        if len(self.profiles) < before:
            if self.settings.active_profile_id == profile_id:
                self.settings.active_profile_id = self.profiles[0].id if self.profiles else ""
                self.save_settings()
            self.save_profiles()
            return True
        return False

    def delete_subscription(self, sub_id: str) -> bool:
        before = len(self.subscriptions)
        self.subscriptions = [s for s in self.subscriptions if s.id != sub_id]
        self.profiles = [p for p in self.profiles if p.sub_id != sub_id]
        if len(self.subscriptions) < before:
            if self.settings.active_profile_id and not self.get_profile(self.settings.active_profile_id):
                self.settings.active_profile_id = self.profiles[0].id if self.profiles else ""
                self.save_settings()
            self.save_profiles()
            return True
        return False

    def upsert_subscription(self, sub: SubscriptionItem) -> None:
        for i, existing in enumerate(self.subscriptions):
            if existing.id == sub.id:
                self.subscriptions[i] = sub
                self.save_profiles()
                return
        self.subscriptions.append(sub)
        self.save_profiles()

    def update_pings(self, pings: dict[str, int]) -> None:
        now = int(time.time())
        changed = False
        for p in self.profiles:
            if p.id in pings:
                p.ping_ms = pings[p.id]
                p.last_tested_at = now
                changed = True
        if changed:
            self.save_profiles()

    def add_direct_rule(self, entry: str) -> bool:
        """Add a domain or IP/CIDR to direct_domains or direct_ips."""
        val = entry.strip()
        if not val:
            return False
        if "://" in val:
            val = urlsplit(val).hostname or val
        if self._looks_like_ip_rule(val):
            if val not in self.settings.direct_ips:
                self.settings.direct_ips.append(val)
                self.save_settings()
                return True
        else:
            if not val.startswith(("geosite:", "domain:", "full:", "regexp:", "keyword:", "ext:")):
                val = f"domain:{val.lstrip('.')}"
            if val not in self.settings.direct_domains:
                self.settings.direct_domains.append(val)
                self.save_settings()
                return True
        return False

    def remove_direct_rule(self, entry: str) -> bool:
        val = entry.strip()
        changed = False
        for candidate in (val, f"domain:{val}"):
            if candidate in self.settings.direct_domains:
                self.settings.direct_domains.remove(candidate)
                changed = True
        if val in self.settings.direct_ips:
            self.settings.direct_ips.remove(val)
            changed = True
        if changed:
            self.save_settings()
        return changed

    def reset_direct_rules(self) -> None:
        self.settings.direct_domains = list(DEFAULT_DIRECT_DOMAINS)
        self.settings.direct_ips = list(DEFAULT_DIRECT_IPS)
        self.save_settings()

    @staticmethod
    def _looks_like_ip_rule(val: str) -> bool:
        if val.startswith("geoip:"):
            return True
        if val.startswith(("geosite:", "domain:", "full:", "regexp:", "keyword:", "ext:")):
            return False
        # Check IPv4 / CIDR or IPv6
        parts = val.split("/")[0].split(".")
        if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            return True
        if ":" in val and all(c in "0123456789abcdefABCDEF:./" for c in val):
            return True
        return False
