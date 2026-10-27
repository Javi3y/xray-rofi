# xray-rofi

Fast, lightweight **Rofi 2.0** client and background `asyncio` daemon for **Xray-core v26+** on Linux.

## Features

- **Single Mixed Port (`127.0.0.1:10808`)**: Serves both **SOCKS5 (with UDP)** and **HTTP Proxy** on the exact same port (`"protocol": "mixed"`).
- **100% Unprivileged Proxy Mode**: Running the local proxy, testing real HTTP 204 latency, and updating subscriptions run entirely as your normal user and **never** prompt for root/Polkit permissions.
- **Native Xray v26 TUN Mode (`xray_tun`)**: Optional system-wide TUN interface elevated via Polkit (`pkexec` or `run0`) only when explicitly toggled on.
- **Iran Split Routing + Live Direct Bypass Editor**: Routes Iranian domains (`domain:ir`, `geosite:category-ir`), Iranian IPs (`geoip:ir`), and private LAN traffic directly by default, with an interactive Rofi submenu to add/remove custom domains or IP CIDRs on the fly.
- **Modern Protocols & Transports**: Supports `vless://`, `vmess://`, `trojan://`, `ss://` (SIP002 / 2022 / Legacy), and `socks://` across `raw`/`tcp`, `xhttp` (`splithttp`), `ws`, `grpc`, `httpupgrade`, `kcp`, `tls`, `reality`, XTLS Vision, and TLS Fragment (DPI bypass).
- **Concurrent Real-Ping Engine**: Tests all servers concurrently using a single ephemeral multi-port Xray instance (`HTTP 204` delay).
- **Zero Python Dependencies**: Pure Python 3.12+ standard library.

---

## Requirements

- **Linux** with Python `>= 3.12`
- **`xray`** (`Xray-core` v26+ in `$PATH`, `/usr/local/bin/xray`, or `/usr/bin/xray`)
- **`rofi`** (`>= 1.7` / `2.0`)
- Optional clipboard tool for `Alt+v` paste: `wl-clipboard` (`wl-paste`) or `xclip` / `xsel`

---

## Installation

### Using `uv` (Recommended)

```bash
# Install directly from GitHub:
uv tool install git+https://github.com/Javi3y/xray-rofi

# Or install from a local clone:
git clone https://github.com/Javi3y/xray-rofi
cd xray-rofi
uv tool install .
```

### Using `pipx`

```bash
pipx install git+https://github.com/Javi3y/xray-rofi
```

---

## Usage

Run `xray-rofi` from your application launcher, terminal, or window manager keybind (the background daemon `xray-rofid` starts automatically on first launch):

```bash
xray-rofi
```

### Window Manager Keybind Example (Hyprland / Sway / i3)

```ini
# Hyprland (~/.config/hypr/hyprland.conf)
bind = $mainMod, X, exec, xray-rofi

# i3 / Sway (~/.config/sway/config)
bindsym $mod+x exec xray-rofi
```

### Rofi Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Enter` | Connect to selected server / Activate menu item |
| `Alt+t` / `Alt+1` | **Ping All Servers** (concurrent real HTTP 204 delay test) |
| `Alt+b` / `Alt+2` | **Connect Fastest Server** (lowest positive ping) |
| `Alt+m` / `Alt+3` | **Toggle Mode** (`Proxy 127.0.0.1:10808` $\leftrightarrow$ `TUN xray_tun`) |
| `Alt+r` / `Alt+4` | **Cycle Routing** (`Split (Iran Direct)` $\rightarrow$ `Global` $\rightarrow$ `Direct`) |
| `Alt+v` / `Alt+5` | **Import from Clipboard** (share links or `https://` subscription URL) |
| `Alt+u` / `Alt+6` | **Update All Subscriptions** |
| `Alt+d` / `Alt+7` | **Delete Highlighted Server** |
| `Alt+l` / `Alt+8` | **View Xray Runtime Logs** |

---

## Configuration Files

All state is stored in human-readable JSON files in `~/.config/xray-rofi/`:

- `~/.config/xray-rofi/settings.json`: Port (`mixed_port: 10808`), mode (`proxy` / `tun`), routing (`split` / `global` / `direct`), TLS fragment settings, and `direct_domains` / `direct_ips`.
- `~/.config/xray-rofi/profiles.json`: Subscriptions and server profiles.

---

## Development & Tests

```bash
uv run pytest -v
```
