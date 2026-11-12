"""Match photos as post backgrounds, from the PRIVATE photo store (./player-photos/match-photos).

    match-photos/<Team name>/   photos for one team, e.g. "1st XI", "Women's Softball"
    match-photos/Indoor/        any indoor team without a folder of its own
    match-photos/Juniors/       any junior team without a folder of its own
    match-photos/Club/          anything else, and the Monday results summary

A photo doesn't have to be from the game itself: each post takes the team's photo that was used
least recently, so they rotate. Photos are only drawn into the finished graphic (darkened under the
club colour); the files themselves are never copied into the public repository.
"""
import hashlib
import re
from pathlib import Path

PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp")
INDOOR, JUNIORS, CLUB = "Indoor", "Juniors", "Club"


def _key(name):
    """Folder/team names compared ignoring capitals, spaces and punctuation, and with "Under" = "U"
    (Play-Cricket writes some teams both ways, e.g. "Under 12 Indoor" and "U12 Indoor")."""
    n = re.sub(r"\bunder\s*(?=\d)", "u", (name or "").lower())
    return re.sub(r"[^a-z0-9]", "", n)


class MatchPhotos:
    def __init__(self, root, used=None):
        self.root = Path(root) / "match-photos"
        self.used = used if used is not None else {}  # photo -> date last used (ISO)
        self.folders = {}
        if self.root.is_dir():
            for d in sorted(self.root.iterdir()):
                if d.is_dir():
                    files = [f for f in sorted(d.rglob("*")) if f.is_file() and f.suffix.lower() in PHOTO_TYPES]
                    if files:
                        self.folders[_key(d.name)] = (d.name, files)

    def __len__(self):
        return sum(len(f) for _, f in self.folders.values())

    def counts(self):
        return {name: len(files) for name, files in self.folders.values()}

    def folder_for(self, cfg, team):
        """Which folder a team's photos come from: its own, then Indoor / Juniors, then Club."""
        order = [team]
        if re.search(r"\bIndoor\b", team or "", re.I):
            order.append(INDOOR)
        if cfg.is_junior(team):
            order.insert(1, JUNIORS)
        order.append(CLUB)
        for name in order:
            if _key(name) in self.folders:
                return self.folders[_key(name)]
        return None

    def pick(self, cfg, team, post_key, today, any_folder=False):
        """The least recently used photo for this team (or any photo), marking it used. Path or None."""
        if any_folder:
            club = self.folders.get(_key(CLUB))
            files = club[1] if club else [f for _, fs in self.folders.values() for f in fs]
        else:
            found = self.folder_for(cfg, team)
            files = found[1] if found else []
        if not files:
            return None
        rel = lambda f: str(f.relative_to(self.root))
        tie = lambda f: hashlib.sha1(f"{post_key}{rel(f)}".encode()).hexdigest()
        best = min(files, key=lambda f: (self.used.get(rel(f), ""), tie(f)))
        self.used[rel(best)] = today.isoformat()
        return best


def add_backgrounds(cfg, made, photos, today):
    """Give match, milestone and round-up posts a match photo background when there is one."""
    if not photos or not cfg["match_photos"]["enabled"]:
        return
    use = cfg["match_photos"]["use_for"]
    for p in made:
        d, kind = p["data"], p["kind"]
        if kind not in use:
            continue
        if kind == "milestone" and d.get("photo_path"):
            continue  # a player photo is already the star of the graphic
        if kind in ("roundup", "countdown"):
            f = photos.pick(cfg, "", p["key"], today, any_folder=True)
        else:
            f = photos.pick(cfg, d.get("team", ""), p["key"], today)
        if f:
            d["bg_photo"] = str(f)
