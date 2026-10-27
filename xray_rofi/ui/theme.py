"""Dynamic Rofi theme palette extractor (`rofi -dump-theme`)."""

from __future__ import annotations

import colorsys
import re
import subprocess


def _rgb_to_pango(r: float, g: float, b: float) -> str:
    ri = max(0, min(255, int(round(r * 255))))
    gi = max(0, min(255, int(round(g * 255))))
    bi = max(0, min(255, int(round(b * 255))))
    return f"#{ri:02x}{gi:02x}{bi:02x}"


def load_rofi_palette() -> dict[str, str]:
    """Derive semantic UI colors dynamically from the user's active Rofi theme (`rofi -dump-theme`)."""
    raw_colors: dict[str, tuple[float, float, float]] = {}
    try:
        res = subprocess.run(
            ["rofi", "-dump-theme"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        rgba_re = re.compile(
            r"^\s*([a-zA-Z0-9_-]+)\s*:\s*rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)",
            re.MULTILINE,
        )
        for m in rgba_re.finditer(res.stdout):
            name = m.group(1).lower()
            if name not in raw_colors:
                raw_colors[name] = (
                    int(m.group(2)) / 255.0,
                    int(m.group(3)) / 255.0,
                    int(m.group(4)) / 255.0,
                )
    except Exception:
        pass

    bg = raw_colors.get("background") or raw_colors.get("normal-background") or (0.12, 0.12, 0.18)
    fg = raw_colors.get("foreground") or raw_colors.get("normal-foreground") or (0.85, 0.85, 0.90)
    muted = raw_colors.get("foreground-muted") or (
        fg[0] * 0.65 + bg[0] * 0.35,
        fg[1] * 0.65 + bg[1] * 0.35,
        fg[2] * 0.65 + bg[2] * 0.35,
    )
    crit = raw_colors.get("critical") or raw_colors.get("urgent-background") or raw_colors.get("urgent-foreground")

    _, l_bg, _ = colorsys.rgb_to_hls(*bg)
    _, l_fg, s_fg = colorsys.rgb_to_hls(*fg)

    if crit is not None:
        _, l_crit, s_crit = colorsys.rgb_to_hls(*crit)
        target_l = l_fg * 0.55 + l_crit * 0.45
        target_s = max(0.45, min(0.75, s_crit * 0.80))
    else:
        target_l = 0.35 if l_bg > 0.5 else 0.70
        target_s = max(0.50, min(0.70, s_fg + 0.45))

    if l_bg > 0.5:
        target_l = min(target_l, l_bg - 0.42)
    else:
        target_l = max(target_l, l_bg + 0.42)
    target_l = max(0.22, min(0.82, target_l))

    def _derive_hue(names: tuple[str, ...], hue: float) -> str:
        for n in names:
            if n in raw_colors:
                return _rgb_to_pango(*raw_colors[n])
        return _rgb_to_pango(*colorsys.hls_to_rgb(hue, target_l, target_s))

    return {
        "fg": _rgb_to_pango(*fg),
        "muted": _rgb_to_pango(*muted),
        "error": _rgb_to_pango(*crit) if crit else _derive_hue(("red", "critical"), 0.01),
        "ok": _derive_hue(("green", "success", "active-foreground"), 0.30),
        "warn": _derive_hue(("yellow", "warning"), 0.11),
        "slow": _derive_hue(("orange",), 0.06),
        "info": _derive_hue(("blue", "info"), 0.54),
        "accent": _derive_hue(("purple", "magenta"), 0.80),
    }


PALETTE = load_rofi_palette()
