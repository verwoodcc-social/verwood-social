"""Milestone posts: 50s, 100s and five-wicket hauls, optionally with a player's photo.

Player photos live in a PRIVATE store (checked out to ./player-photos by the workflow):
    player-photos/adults/<Name as on Play-Cricket>.jpg   adults (18+) who have agreed
    player-photos/juniors/<Name as on Play-Cricket>.jpg  under-18s, with parent/carer consent

ECB guidance: a child's picture and name must not appear together. So a junior milestone shows
either their (shortened) name OR their photo, never both: milestones → junior_photos.
Photos are only ever drawn into the finished graphic; the photo files themselves are never
copied into this (public) repository.
"""
import re
from pathlib import Path

PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp")
TITLES = {"100": "Century", "50": "Fifty", "5w": "Five-wicket haul"}
CHEER = {"100": "a magnificent century", "50": "a brilliant fifty", "5w": "a superb five-wicket haul"}


def _key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


class PhotoStore:
    """Finds a player's photo by their name as Play-Cricket writes it (capitals, spaces and dots ignored)."""

    def __init__(self, root):
        self.root = Path(root)
        self.index = {}
        for group in ("adults", "juniors"):
            folder = self.root / group
            if not folder.is_dir():
                continue
            for f in sorted(folder.iterdir()):
                if f.suffix.lower() in PHOTO_TYPES and f.is_file():
                    self.index.setdefault(_key(f.stem), (f, group))

    def __len__(self):
        return len(self.index)

    def find(self, full_name):
        """(path, 'adults' | 'juniors') or None."""
        return self.index.get(_key(full_name))


def find_milestones(cfg, card):
    """Milestones in one match card, best first."""
    ms = cfg["milestones"]
    out = []
    for b in card.get("all_batting", []):
        hit = max((t for t in ms["batting"] if b["runs"] >= t), default=None)
        if hit:
            kind = "100" if hit >= 100 else "50"
            balls = f"{b['balls']} balls" if b["balls"] not in (999, 0) else ""
            out.append({"type": kind, "score": b["runs"], "figures": b["figures"], "detail": balls,
                        "full_name": b["full_name"], "name": b["name"], "player_id": b["player_id"]})
    for b in card.get("all_bowling", []):
        if b["w"] >= int(ms["bowling_wickets"]):
            out.append({"type": "5w", "score": b["w"] * 1000 - b["r"], "figures": b["figures"],
                        "detail": b["detail"], "full_name": b["full_name"], "name": b["name"], "player_id": b["player_id"]})
    out.sort(key=lambda m: (m["type"] != "100", -m["score"]))
    return out


def presentation(cfg, card, m, photos):
    """Apply the photo and naming rules. Returns (name_to_show, photo_path_or_None, reason)."""
    found = photos.find(m["full_name"]) if photos else None
    name = m["name"] if card.get("show_names", True) else ""
    if not found:
        return name, None, "no photo"
    path, group = found
    if group == "juniors" or card.get("junior"):
        # ECB: never a junior's photo and name together.
        if cfg["milestones"]["junior_photos"] == "photo_no_name":
            return "", path, "junior: photo, no name"
        return name, None, "junior: name, no photo"
    return name, path, "adult: photo and name"


def milestone_posts(cfg, card, photos=None):
    """Post dicts for each milestone in a match card."""
    if not cfg["milestones"]["enabled"]:
        return []
    out = []
    for m in find_milestones(cfg, card):
        name, photo, why = presentation(cfg, card, m, photos)
        title = TITLES[m["type"]]
        who = name or f"one of our {card['team']} players"
        data = {"kind": "milestone", "type": m["type"], "label": title, "figures": m["figures"],
                "detail": m["detail"], "name": name, "photo_path": str(photo) if photo else "",
                "team": card["team"], "opponent": f"{card['opponent']} {card['opponent_team']}".strip(),
                "date": card["date"], "date_obj": card.get("date_obj")}
        pid = m["player_id"] or _key(m["full_name"])
        tags = (cfg["club"].get("hashtags") or "").strip()
        sponsor = ""
        b = cfg["branding"]
        if b.get("sponsor_in_captions") and (b.get("sponsor_text") or "").strip():
            sponsor = f"{(b.get('sponsor_label') or 'Supported by').strip()} {b['sponsor_text'].strip()}"
        detail = f" ({m['detail']})" if m["detail"] else ""
        lines = [f"🎉 Congratulations to {who} on {CHEER[m['type']]}!",
                 f"{m['figures']}{detail} for our {card['team']} v {data['opponent']}."]
        extra = [x for x in (sponsor, tags) if x]
        caption = "\n".join(lines) + ("\n\n" + "\n".join(extra) if extra else "")
        out.append({"key": f"milestone-{card['id']}-{m['type']}-{pid}", "kind": "milestone",
                    "title": f"{title}: {name or card['team']} ({m['figures']})", "data": data,
                    "caption": caption,
                    "alt": f"{cfg['club']['name']} milestone: {title.lower()} of {m['figures']} for "
                           f"{who} ({card['team']} v {data['opponent']}).", "photo_rule": why})
    return out
