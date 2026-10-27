"""Tests for Phase 2: Share link and subscription parsers (fmt)."""

from xray_rofi.core.fmt import parse_link, parse_links_text, to_link
from xray_rofi.core.fmt.base import b64_encode
from xray_rofi.core.fmt.subscription import parse_subscription_userinfo


def test_vless_reality_vision_roundtrip() -> None:
    uri = (
        "vless://b831381d-6324-4d53-ad4f-8cda48b30811@edge.example.com:443"
        "?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com"
        "&fp=chrome&pbk=PublicKey12345&sid=a1b2c3d4&spx=%2F&type=tcp&headerType=none#Germany-01"
    )
    item = parse_link(uri)
    assert item is not None
    assert item.config_type == "vless"
    assert item.address == "edge.example.com"
    assert item.port == 443
    assert item.password == "b831381d-6324-4d53-ad4f-8cda48b30811"
    assert item.flow == "xtls-rprx-vision"
    assert item.stream_security == "reality"
    assert item.sni == "www.microsoft.com"
    assert item.fingerprint == "chrome"
    assert item.public_key == "PublicKey12345"
    assert item.short_id == "a1b2c3d4"
    assert item.spider_x == "/"
    assert item.remarks == "Germany-01"

    exported = to_link(item)
    assert exported is not None
    re_parsed = parse_link(exported)
    assert re_parsed is not None
    assert re_parsed.fingerprint_hash() == item.fingerprint_hash()
    assert re_parsed.remarks == "Germany-01"


def test_vless_xhttp_roundtrip() -> None:
    uri = (
        "vless://b831381d-6324-4d53-ad4f-8cda48b30811@cdn.example.com:443"
        "?encryption=none&security=tls&sni=cdn.example.com&fp=firefox"
        "&type=xhttp&host=cdn.example.com&path=%2Fxhttp&mode=packet-up#XHTTP-Node"
    )
    item = parse_link(uri)
    assert item is not None
    assert item.network == "xhttp"
    assert item.path == "/xhttp"
    assert item.mode == "packet-up"

    re_parsed = parse_link(to_link(item) or "")
    assert re_parsed is not None
    assert re_parsed.fingerprint_hash() == item.fingerprint_hash()


def test_vmess_v2rayn_roundtrip() -> None:
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@vmess.example.com:8443"
        "?type=ws&security=tls&host=ws.example.com&path=%2Fws&sni=ws.example.com#VMess-Node"
    )
    seed = parse_link(uri)
    assert seed is not None
    seed.config_type = "vmess"
    seed.method = "auto"

    vmess_uri = to_link(seed)
    assert vmess_uri is not None and vmess_uri.startswith("vmess://")

    parsed = parse_link(vmess_uri)
    assert parsed is not None
    assert parsed.config_type == "vmess"
    assert parsed.address == "vmess.example.com"
    assert parsed.port == 8443
    assert parsed.network == "ws"
    assert parsed.host == "ws.example.com"
    assert parsed.path == "/ws"
    assert parsed.stream_security == "tls"
    assert parsed.remarks == "VMess-Node"


def test_trojan_and_shadowsocks_and_socks() -> None:
    trojan_uri = "trojan://MySecretPass@trojan.example.com:443?security=tls&sni=trojan.example.com&type=grpc&serviceName=mygrpc#Trojan-GRPC"
    t_item = parse_link(trojan_uri)
    assert t_item is not None
    assert t_item.config_type == "trojan"
    assert t_item.network == "grpc"
    assert t_item.path == "mygrpc"
    assert parse_link(to_link(t_item) or "").fingerprint_hash() == t_item.fingerprint_hash()

    ss_uri = f"ss://{b64_encode('2022-blake3-aes-128-gcm:secretkey', urlsafe=True)}@ss.example.com:8388#SS-Node"
    ss_item = parse_link(ss_uri)
    assert ss_item is not None
    assert ss_item.config_type == "ss"
    assert ss_item.method == "2022-blake3-aes-128-gcm"
    assert ss_item.password == "secretkey"

    socks_uri = "socks5://myuser:mypass@127.0.0.1:1080#Local-Socks"
    s_item = parse_link(socks_uri)
    assert s_item is not None
    assert s_item.config_type == "socks"
    assert s_item.username == "myuser"
    assert s_item.password == "mypass"


def test_subscription_batch_and_userinfo() -> None:
    links = [
        "trojan://pw1@h1.example.com:443#Node1",
        "vless://uuid2@h2.example.com:443?security=tls#Node2",
    ]
    b64_payload = b64_encode("\n".join(links))
    items = parse_links_text(b64_payload)
    assert len(items) == 2
    assert items[0].remarks == "Node1"
    assert items[1].remarks == "Node2"

    info = parse_subscription_userinfo("upload=1048576; download=2097152; total=10737418240; expire=1800000000")
    assert info["upload_bytes"] == 1048576
    assert info["download_bytes"] == 2097152
    assert info["total_bytes"] == 10737418240
    assert info["expire_timestamp"] == 1800000000
