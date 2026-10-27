"""Tests for Phase 1: Models and JsonStore."""

from pathlib import Path
from xray_rofi.core.models import ProfileItem, SubscriptionItem
from xray_rofi.core.store import JsonStore


def test_store_init_and_defaults(tmp_path: Path) -> None:
    store = JsonStore(config_dir=tmp_path)
    assert (tmp_path / "settings.json").exists()
    assert (tmp_path / "profiles.json").exists()
    assert store.settings.connection_mode == "proxy"
    assert store.settings.mixed_port == 10808
    assert "domain:ir" in store.settings.direct_domains
    assert "geoip:ir" in store.settings.direct_ips


def test_profile_deduplication_and_persistence(tmp_path: Path) -> None:
    store = JsonStore(config_dir=tmp_path)
    p1 = ProfileItem(
        config_type="vless",
        remarks="Node 1",
        address="edge.example.com",
        port=443,
        password="uuid-1234",
        stream_security="reality",
        public_key="pbk123",
    )
    # Identical connection details, different remarks
    p2 = ProfileItem(
        config_type="vless",
        remarks="Node 1 Renamed",
        address="EDGE.EXAMPLE.COM",
        port=443,
        password="uuid-1234",
        stream_security="reality",
        public_key="pbk123",
    )
    added, dupes = store.add_profiles([p1, p2])
    assert added == 1
    assert dupes == 1
    assert store.settings.active_profile_id == p1.id

    # Reload from disk
    store2 = JsonStore(config_dir=tmp_path)
    assert len(store2.profiles) == 1
    assert store2.profiles[0].id == p1.id
    assert store2.settings.active_profile_id == p1.id


def test_subscription_replacement_preserves_id_and_ping(tmp_path: Path) -> None:
    store = JsonStore(config_dir=tmp_path)
    sub = SubscriptionItem(remarks="MySub", url="https://example.com/sub")
    store.subscriptions.append(sub)

    p1 = ProfileItem(config_type="trojan", address="1.2.3.4", port=443, password="pw1", ping_ms=110)
    store.add_profiles([p1], sub_id=sub.id)
    orig_id = p1.id

    # Refresh subscription with same node + a new node
    p1_new = ProfileItem(config_type="trojan", address="1.2.3.4", port=443, password="pw1")
    p2_new = ProfileItem(config_type="trojan", address="5.6.7.8", port=443, password="pw2")
    count = store.replace_subscription_profiles(sub.id, [p1_new, p2_new])
    assert count == 2

    kept = store.get_profile(orig_id)
    assert kept is not None
    assert kept.ping_ms == 110


def test_direct_rules_management(tmp_path: Path) -> None:
    store = JsonStore(config_dir=tmp_path)
    assert store.add_direct_rule("domain:digikala.com")
    assert "domain:digikala.com" in store.settings.direct_domains

    assert store.add_direct_rule("185.143.232.0/22")
    assert "185.143.232.0/22" in store.settings.direct_ips

    assert store.remove_direct_rule("domain:digikala.com")
    assert "domain:digikala.com" not in store.settings.direct_domains
