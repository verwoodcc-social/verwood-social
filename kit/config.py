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
    "branding": {"badge": "assets/badge.svg", "primary_colour": "#1A4192", "accent_colour": "#DBE2EA",
                 "background_image": "", "fixtures_background": "", "results_background": "",
                 "match_background": "", "background_darkness": "medium",
                 "sponsor_logo": "", "sponsor_text": "", "sponsor_label": "Supported by",
                 "sponsor_in_captions": False},
    "wording": {"fixtures_title": "This Week's Fixtures", "results_title": "Last Week's Results",
                "win": "Victory", "loss": "Defeat", "draw": "Draw", "tie": "Tied",
                "abandoned": "Abandoned", "cancelled": "Cancelled", "no_result": "No result",
                "fixtures_sign_off": "Come down and support! 🏏",
                "story_cta": "Full details on our page"},
    "milestones": {"enabled": True, "batting": [50, 100], "bowling_wickets": 5,
                   "junior_photos": "name_no_photo", "stories": True},
    "matchday": {"enabled": False, "include": "all", "juniors": False, "default_home_ground": "",
                 "no_default_ground_teams": r"\bIndoor\b", "exclude_teams": "",
                 "months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "title": "Matchday",
                 "cta": "Come and support!"},
    "show": {"top_performers": True, "toss": True, "ground_on_fixtures": False, "handle_and_website": True},
    "posts": {
        "fixtures": {"enabled": True, "day": "friday"},
        "results_roundup": {"enabled": True, "day": "monday"},
        "match_results": {"enabled": True, "lookback_days": 1},
        "approval": "review",
        "stories": {"enabled": False, "for": ["match", "fixtures", "roundup"]},
        "networks": ["facebook", "instagram"],
    },
    "juniors": {
        "team_pattern": r"\b(U\s?\d{1,2}[A-Z]?|Under\s?\d{1,2}|Girls|Boys|Juniors?|All Stars|Dynamos|Colts)\b",
        "names": "initial",
        "apply_to_all_teams": True,
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

    def shorten_names(self, team):
        """Whether this team's player names follow the juniors → names rule.
        With apply_to_all_teams (the default) every team does, because juniors often play in adult sides."""
        return bool(self["juniors"].get("apply_to_all_teams", True)) or self.is_junior(team)

    def no_wicket_margin(self, team):
        return bool(re.search(self["scoring"]["no_wicket_margin_teams"], team or "", re.I))

    def palette(self):
        return make_palette(self["branding"]["primary_colour"], self["branding"]["accent_colour"])

    def image(self, key):
        """Path to an uploaded image named in branding → key, or None if not set."""
        name = str(self["branding"].get(key) or "").strip()
        return (self.root / name).resolve() if name else None

    def background_for(self, kind):
        """Uploaded background for a post kind (fixtures / results / match), falling back to the general one."""
        return self.image(f"{kind}_background") or self.image("background_image")

    def stories_for(self, kind):
        """Whether this kind of post (match / fixtures / roundup / milestone) also goes out as a story."""
        st = self["posts"].get("stories") or {}
        if kind == "milestone":
            return bool(st.get("enabled")) and bool(self["milestones"].get("stories", True))
        return bool(st.get("enabled")) and kind in (st.get("for") or [])

    def words(self):
        w = self["wording"]
        return {"W": w["win"], "L": w["loss"], "D": w["draw"], "T": w["tie"], "A": w["abandoned"],
                "C": w["cancelled"], "N": w["no_result"], "P": "Match report"}


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
    st = p.get("stories") or {}
    if not isinstance(st.get("enabled", False), bool):
        problems.append("posts → stories → enabled: use true or false.")
    if any(k not in ("match", "fixtures", "roundup") for k in (st.get("for") or [])):
        problems.append("posts → stories → for: list any of match, fixtures, roundup, like [match, fixtures, roundup].")
    mi = cfg.get("milestones") or {}
    if not isinstance(mi.get("enabled", True), bool):
        problems.append("milestones → enabled: use true or false.")
    try:
        if not mi.get("batting") or any(int(x) <= 0 for x in mi["batting"]) or int(mi.get("bowling_wickets", 5)) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("milestones → batting / bowling_wickets: use numbers, like batting: [50, 100] and bowling_wickets: 5.")
    if mi.get("junior_photos") not in ("name_no_photo", "photo_no_name"):
        problems.append("milestones → junior_photos: use name_no_photo or photo_no_name (ECB guidance: never both).")
    md = cfg.get("matchday") or {}
    if md.get("include", "all") not in ("all", "home"):
        problems.append("matchday → include: use all or home.")
    months = md.get("months", [])
    if not isinstance(months, list) or not all(isinstance(m, int) and 1 <= m <= 12 for m in months):
        problems.append("matchday → months: list month numbers 1 to 12, e.g. [4, 5, 6, 7, 8, 9].")
    try:
        re.compile(md.get("exclude_teams") or "")
    except re.error:
        problems.append("matchday → exclude_teams: that pattern isn't valid.")
    for k in ("enabled", "juniors"):
        if not isinstance(md.get(k, False), bool):
            problems.append(f"matchday → {k}: use true or false.")
    if p.get("approval") not in ("review", "automatic"):
        problems.append("posts → approval: use review or automatic.")
    nets = p.get("networks") or []
    if not nets or any(n not in ("facebook", "instagram") for n in nets):
        problems.append("posts → networks: list facebook, instagram, or both, like [facebook, instagram].")
    if cfg["juniors"].get("names") not in ("initial", "first", "full", "none"):
        problems.append("juniors → names: use initial, first, full or none.")
    if not isinstance(cfg["juniors"].get("apply_to_all_teams", True), bool):
        problems.append("juniors → apply_to_all_teams: use true or false.")
    for sect, key in (("juniors", "team_pattern"), ("scoring", "no_wicket_margin_teams")):
        try:
            re.compile(cfg[sect][key])
        except re.error:
            problems.append(f"{sect} → {key}: this pattern isn't valid. Put it back to the original if unsure.")
    cfg.warnings = []
    for key, what in IMAGE_SETTINGS.items():
        check_image(cfg, key, what, problems, cfg.warnings)
    if str(b.get("background_darkness", "medium")).lower() not in OVERLAY:
        problems.append("branding → background_darkness: use light, medium or strong.")
    for sect in ("wording", "show"):
        if not isinstance(cfg.get(sect), dict):
            problems.append(f"{sect}: this section should be a list of settings, like the example. Put it back if unsure.")
    for key, val in (cfg.get("show") or {}).items():
        if not isinstance(val, bool):
            problems.append(f"show → {key}: use true or false.")
    for key, val in (cfg.get("wording") or {}).items():
        if not isinstance(val, str) or not val.strip():
            problems.append(f"wording → {key}: this can't be empty. Put the words in quotes, like \"Victory\".")
    if problems:
        raise ConfigError("Please fix these in club.yml:\n- " + "\n- ".join(problems))


# --- uploaded images -----------------------------------------------------------

IMAGE_SETTINGS = {
    "background_image": "background photo",
    "fixtures_background": "fixtures background photo",
    "results_background": "results background photo",
    "match_background": "match result background photo",
    "sponsor_logo": "sponsor logo",
}
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".svg")
MAX_MB = 15
OVERLAY = {"light": (0.45, 0.55, 0.70), "medium": (0.62, 0.72, 0.84), "strong": (0.78, 0.86, 0.92)}


def check_image(cfg, key, what, problems, warnings):
    name = str(cfg["branding"].get(key) or "").strip()
    if not name:
        return
    path = cfg.root / name
    if not path.exists():
        near = sorted(p.name for p in (cfg.root / "assets").glob("*")) if (cfg.root / "assets").exists() else []
        hint = f" Files in your assets folder: {', '.join(near)}." if near else ""
        problems.append(f"branding → {key}: I can't find '{name}'. Upload your {what} to the assets folder and check "
                        f"the name matches exactly, including capitals and the ending (.jpg, .png).{hint}")
        return
    if path.suffix.lower() not in IMAGE_TYPES:
        problems.append(f"branding → {key}: '{name}' isn't a picture I can use. Use a JPG or PNG.")
        return
    mb = path.stat().st_size / 1_000_000
    if mb > MAX_MB:
        problems.append(f"branding → {key}: '{name}' is {mb:.0f} MB. Please use a picture under {MAX_MB} MB.")
        return
    if path.suffix.lower() == ".svg":
        return
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        problems.append(f"branding → {key}: '{name}' couldn't be opened as a picture. Try saving it again as a JPG or PNG.")
        return
    if key.endswith("background") or key == "background_image":
        if w < 1080 or h < 1080:
            warnings.append(f"Your {what} is only {w}×{h} pixels, so it may look blurry. "
                            f"A photo at least 1080 pixels on each side works best.")
    elif w < 200:
        warnings.append(f"Your {what} is only {w} pixels wide, so it may look blurry. A larger version would be sharper.")


def overlay(palette, darkness):
    """Club-colour layer laid over a photo so white text stays readable."""
    a1, a2, a3 = OVERLAY.get(str(darkness).lower(), OVERLAY["medium"])
    def rgba(h, a):
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r},{g},{b},{a})"
    return {"overlay-top": rgba(palette["navy"], a1), "overlay-mid": rgba(palette["navy-deep"], a2),
            "overlay-bottom": rgba(palette["navy-ink"], a3)}


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
