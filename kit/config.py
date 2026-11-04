"""Load and check club.yml, and work out the graphic colour palette."""
import colorsys
import re
from copy import deepcopy
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

ROOT = Path(__file__).resolve().parent.parent
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DEFAULTS = {
    "club": {"hashtags": "", "timezone": "Europe/London", "website": "", "handle": ""},
    "branding": {"badge": "assets/badge.svg", "primary_colour": "#1A4192", "accent_colour": "#DBE2EA"},
    "posts": {
        "fixtures": {"enabled": True, "day": "friday"},
        "results_roundup": {"enabled": True, "day": "monday"},
        "match_results": {"enabled": True, "lookback_days": 1},
        "approval": "review",
        "networks": ["facebook", "instagram"],
    },
    "juniors": {
        "team_pattern": r"\b(U\s?\d{1,2}[A-Z]?|Under\s?\d{1,2}|Girls|Boys|Juniors?|All Stars|Dynamos|Colts)\b",
        "names": "initial",
    },
    "scoring": {
        "wickets_per_innings": 10,
        "no_wicket_margin_teams": r"\b(Indoor|Softball|Pairs|U\s?\d{1,2}|Under\s?\d{1,2}|All Stars|Dynamos)\b",
    },
    "facebook": {"page_id": ""},
}


class ConfigError(ValueError):
    """club.yml has a problem the club needs to fix. The message is written for them."""


def _merge(base, extra):
    out = deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


class Config(dict):
    """club.yml as a dict, plus a few derived helpers."""

    @property
    def tz(self):
        return ZoneInfo(self["club"]["timezone"])

    @property
    def site_id(self):
        return int(self["club"]["play_cricket_site_id"])

    @property
    def short_name(self):
        return self["club"]["short_name"]

    def badge_path(self):
        return (self.root / self["branding"]["badge"]).resolve()

    def is_junior(self, team):
        return bool(re.search(self["juniors"]["team_pattern"], team or "", re.I))

    def no_wicket_margin(self, team):
        return bool(re.search(self["scoring"]["no_wicket_margin_teams"], team or "", re.I))

    def palette(self):
        return make_palette(self["branding"]["primary_colour"], self["branding"]["accent_colour"])


def load(path=None):
    path = Path(path or ROOT / "club.yml")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        raise ConfigError(f"I can't find {path.name}. It should be in the top folder of your repository.")
    except yaml.YAMLError as e:
        line = getattr(getattr(e, "problem_mark", None), "line", None)
        where = f" near line {line + 1}" if line is not None else ""
        raise ConfigError(f"{path.name} isn't laid out correctly{where}. Check the spacing at the start of each line, "
                          f"and that any text containing a colon is in quotes.")
    cfg = Config(_merge(DEFAULTS, raw))
    cfg.root = path.parent
    validate(cfg)
    return cfg


def validate(cfg):
    problems = []
    c, b, p = cfg["club"], cfg["branding"], cfg["posts"]
    for key in ("name", "short_name", "play_cricket_name"):
        v = str(c.get(key) or "")
        if not v.strip() or "YOUR" in v:
            problems.append(f"club → {key}: please replace the example text with your club's details.")
    try:
        if int(c.get("play_cricket_site_id") or 0) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("club → play_cricket_site_id: put your Play-Cricket Site ID here (a number, found at the "
                        "bottom of your Play-Cricket site).")
    try:
        ZoneInfo(c["timezone"])
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        problems.append(f"club → timezone: '{c.get('timezone')}' isn't a time zone I recognise. Try Europe/London.")
    for key in ("primary_colour", "accent_colour"):
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", str(b.get(key, ""))):
            problems.append(f"branding → {key}: use a 6-digit hex colour in quotes, like \"#1A4192\".")
    badge = (cfg.root / b["badge"])
    if not badge.exists():
        problems.append(f"branding → badge: I can't find '{b['badge']}'. Upload your badge to the assets folder "
                        f"and check the file name matches exactly (including capitals).")
    elif badge.suffix.lower() not in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
        problems.append("branding → badge: use an SVG, PNG or JPG file.")
    for kind in ("fixtures", "results_roundup"):
        if str(p[kind].get("day", "")).lower() not in DAYS:
            problems.append(f"posts → {kind} → day: use a day name like friday.")
    try:
        if not 1 <= int(p["match_results"].get("lookback_days", 1)) <= 7:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("posts → match_results → lookback_days: use a number from 1 to 7.")
    if p.get("approval") not in ("review", "automatic"):
        problems.append("posts → approval: use review or automatic.")
    nets = p.get("networks") or []
    if not nets or any(n not in ("facebook", "instagram") for n in nets):
        problems.append("posts → networks: list facebook, instagram, or both, like [facebook, instagram].")
    if cfg["juniors"].get("names") not in ("initial", "first", "full", "none"):
        problems.append("juniors → names: use initial, first, full or none.")
    for sect, key in (("juniors", "team_pattern"), ("scoring", "no_wicket_margin_teams")):
        try:
            re.compile(cfg[sect][key])
        except re.error:
            problems.append(f"{sect} → {key}: this pattern isn't valid. Put it back to the original if unsure.")
    if problems:
        raise ConfigError("Please fix these in club.yml:\n- " + "\n- ".join(problems))


# --- colours ---------------------------------------------------------------

def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _to_hex(rgb):
    return "#" + "".join(f"{round(max(0, min(1, v)) * 255):02X}" for v in rgb)


def luminance(h):
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in _hex(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _shade(h, factor):
    r, g, b = _hex(h)
    hh, l, s = colorsys.rgb_to_hls(r, g, b)
    return _to_hex(colorsys.hls_to_rgb(hh, l * factor, s))


def make_palette(primary, accent):
    primary = "#" + primary.lstrip("#").upper()
    accent = "#" + accent.lstrip("#").upper()
    # The darker club colour becomes the background and the lighter one the highlight,
    # so a gold-and-green club gets green with gold, not darkened gold.
    if luminance(primary) > luminance(accent) and contrast(primary, accent) >= 2:
        primary, accent = accent, primary
    # Background must stay dark enough for white text: darken until it is.
    bg = primary
    while luminance(bg) > 0.09:
        bg = _shade(bg, 0.9)
    deep = _shade(bg, 0.62)
    ink = _shade(bg, 0.42)
    # Accent is used for text on the dark background, so it must be readable.
    if contrast(accent, deep) < 4.5:
        accent = "#F2F4F7"
    r1, g1, b1 = _hex(accent)
    r2, g2, b2 = _hex(deep)
    dim = _to_hex((r1 * 0.68 + r2 * 0.32, g1 * 0.68 + g2 * 0.32, b1 * 0.68 + b2 * 0.32))
    return {"navy": bg, "navy-deep": deep, "navy-ink": ink, "silver": accent, "silver-dim": dim}
