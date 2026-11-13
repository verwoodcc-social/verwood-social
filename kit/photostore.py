"""The photo store in the club SharePoint (club.yml → photo_store).

Layout, inside the store folder (default "Social media photos" in Club Documents):
    match-photos/<Team name>/   team photos, used as post backgrounds (see matchphotos.py)
    match-photos/Indoor, Juniors, Club
    adults/<Name as on Play-Cricket>.jpg    player photos for milestone posts
    juniors/<Name>.jpg                      (never shown with a name)

Before posts are made, `sync` copies the photos into ./player-photos (never committed: it's git-ignored),
so the rest of the kit works exactly as it did with the old GitHub photo store. The kit only reads
photos; `folders` makes any missing team folders, named as the teams are on Play-Cricket.
Uses the M365 app (Sites.Selected on the club documents site), like the weekly backup.
"""
import logging
from pathlib import Path

from .backup import BackupError, SharePoint
from . import mailer

log = logging.getLogger(__name__)
PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp")
HEIC = (".heic", ".heif")   # iPhone photos: converted to JPEG when they're copied in
GENERIC = ["Indoor", "Juniors", "Club"]
TO_CHECK = "To check"   # emailed-in photos wait here until someone moves them into a team folder


def _sp(env, http=None):
    try:
        s = mailer.settings(env)
    except mailer.MailError as e:
        raise BackupError(str(e))
    if not s:
        raise BackupError("Microsoft 365 isn't set up (the M365_* secrets), so the SharePoint photo store can't be read.")
    return SharePoint(s, http)


def folder_names(cfg):
    teams = [str(t).strip() for t in (cfg["photo_store"].get("teams") or []) if str(t).strip()]
    return ([f"match-photos/{t}" for t in teams + GENERIC] + ["adults", "juniors", TO_CHECK])


def make_folders(cfg, env, http=None):
    """Create any missing folders. Returns the ones made."""
    ps = cfg["photo_store"]
    sp = _sp(env, http)
    drive = sp.drive(ps["site"])
    made = []
    existing = set(_walk_names(sp, drive, sp.folder(drive, ps["folder"]), ""))
    for name in folder_names(cfg):
        if name not in existing:
            sp.folder(drive, f"{ps['folder']}/{name}")
            made.append(name)
    return made


def _children(sp, drive, item):
    url = f"/drives/{drive}/items/{item}/children"
    params = {"$top": 999}
    while url:
        page = sp._req("GET", url, params=params)
        yield from page.get("value", [])
        url, params = page.get("@odata.nextLink"), None


def _walk_names(sp, drive, item, prefix):
    for k in _children(sp, drive, item):
        if "folder" in k:
            path = f"{prefix}{k['name']}"
            yield path
            yield from _walk_names(sp, drive, k["id"], path + "/")


def sync(cfg, env, dest, http=None):
    """Copy every photo from the SharePoint store into dest. Returns how many."""
    ps = cfg["photo_store"]
    sp = _sp(env, http)
    drive = sp.drive(ps["site"])
    root = sp.folder(drive, ps["folder"])
    dest = Path(dest)
    count = 0

    def walk(item, rel):
        nonlocal count
        for k in _children(sp, drive, item):
            if "folder" in k:
                if k["name"].strip().lower() != TO_CHECK.lower():  # never use photos nobody has checked
                    walk(k["id"], rel / k["name"])
            elif Path(k["name"]).suffix.lower() in PHOTO_TYPES + HEIC:
                out = dest / rel / k["name"]
                out.parent.mkdir(parents=True, exist_ok=True)
                url = k.get("@microsoft.graph.downloadUrl")
                if url:
                    r = sp.http.get(url, timeout=120)
                else:  # Graph leaves the download link out of some listings: ask for the file itself
                    r = sp.http.get(f"https://graph.microsoft.com/v1.0/drives/{drive}/items/{k['id']}/content",
                                    headers={"Authorization": f"Bearer {sp.token}"}, timeout=120)
                if r.status_code == 200:
                    if out.suffix.lower() in HEIC:
                        try:
                            out = to_jpeg(r.content, out)
                        except Exception as e:  # a photo that can't be read is skipped, never fatal
                            log.warning("Couldn't convert %s: %s", rel / k["name"], e)
                            continue
                    else:
                        out.write_bytes(r.content)
                    _stamp(out, k.get("createdDateTime"))
                    count += 1
                else:
                    log.warning("Couldn't download %s (%s)", rel / k["name"], r.status_code)
    walk(root, Path("."))
    return count


def _stamp(path, when):
    """Give the copy the date the photo was added to SharePoint (moving it from To check keeps that date),
    so a photo-led result post can tell which photos are from the game."""
    if not when:
        return
    import os
    from datetime import datetime
    try:
        t = datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        os.utime(path, (t, t))
    except (ValueError, OSError):
        pass


def import_dir(cfg, env, src, http=None):
    """Copy photos from a local folder (the old GitHub photo store) into SharePoint, keeping the layout.
    Photos already there (same folder and name) are left alone. Returns the ones copied."""
    ps = cfg["photo_store"]
    sp = _sp(env, http)
    drive = sp.drive(ps["site"])
    src = Path(src)
    done = []
    for f in sorted(src.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in PHOTO_TYPES or ".git" in f.parts:
            continue
        rel = f.relative_to(src)
        parent = sp.folder(drive, "/".join([ps["folder"], *rel.parts[:-1]]))
        if any(k["name"] == f.name for k in _children(sp, drive, parent)):
            continue
        sp.upload(drive, parent, f)
        done.append(str(rel))
    return done


def to_jpeg(data, out):
    """Save HEIC/HEIF bytes as a JPEG next to where the original would go. Returns the new path."""
    import io
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener
    register_heif_opener()
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    jpg = out.with_suffix(".jpg")
    im.save(jpg, quality=90)
    return jpg


def tree(cfg, env, http=None):
    """{folder path: [file names]} for every folder in the store (photos only)."""
    ps = cfg["photo_store"]
    sp = _sp(env, http)
    drive = sp.drive(ps["site"])
    root = sp.folder(drive, ps["folder"])
    out = {}

    def walk(item, rel):
        files = []
        for k in _children(sp, drive, item):
            if "folder" in k:
                walk(k["id"], f"{rel}/{k['name']}" if rel else k["name"])
            elif Path(k["name"]).suffix.lower() in PHOTO_TYPES + HEIC:
                files.append(k["name"])
        out[rel] = files
    walk(root, "")
    return out


def counts(cfg, t):
    """Photos per team folder (including subfolders), from tree(); teams in club.yml with none are listed too."""
    teams = {}
    for path, files in t.items():
        parts = path.split("/")
        if parts[0] == "match-photos" and len(parts) >= 2:
            teams[parts[1]] = teams.get(parts[1], 0) + len(files)
    for name in [str(x) for x in cfg["photo_store"].get("teams") or []] + GENERIC:
        teams.setdefault(name, 0)
    players = sum(len(f) for p, f in t.items() if p.split("/")[0] == "adults")
    waiting = sum(len(f) for p, f in t.items() if p.split("/")[0] == TO_CHECK)
    return teams, players, waiting


def summary_text(cfg, t):
    """A few lines about the photo store, for the monthly committee email."""
    teams, players, waiting = counts(cfg, t)
    total = sum(teams.values())
    have = sorted((n, c) for n, c in teams.items() if c)
    none = [n for n, c in teams.items() if not c and n not in GENERIC]
    lines = [f"Photo store: {total} team photo{'s' if total != 1 else ''} and {players} player photo"
             f"{'s' if players != 1 else ''}" + (f", with {waiting} waiting in To check." if waiting else ".")]
    if have:
        lines.append("Photos per team: " + ", ".join(f"{n} {c}" for n, c in have) + ".")
    if none:
        lines.append(f"No photos yet ({len(none)} teams, so their posts use the Juniors, Indoor or Club photos or "
                     f"the plain club colours): " + ", ".join(none) + ".")
    return "\n".join(lines)


SEEN = "state/photos-to-check.json"


def notify(cfg, env, root, http=None, send=None):
    """Email the committee about photos that have arrived in To check since last time. Returns how many."""
    import json
    t = tree(cfg, env, http)
    waiting = sorted(f"{p}/{f}" for p, fs in t.items() if p.split("/")[0] == TO_CHECK for f in fs)
    path = Path(root) / SEEN
    try:
        seen = set(json.loads(path.read_text()))
    except (FileNotFoundError, ValueError):
        seen = set()
    new = [w for w in waiting if w not in seen]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(waiting, indent=1) + "\n")  # forget ones that have been moved or deleted
    if not new:
        return 0
    ps = cfg["photo_store"]
    link = f"https://{ps['site']}/Shared%20Documents/{ps['folder'].replace(' ', '%20')}/{TO_CHECK.replace(' ', '%20')}"
    names = "\n".join(f"- {w.split('/', 1)[1]}" for w in new[:30]) + ("\n- …" if len(new) > 30 else "")
    text = (f"Hello,\n\n{len(new)} new photo{'s have' if len(new) != 1 else ' has'} been emailed in and "
            f"{'are' if len(new) != 1 else 'is'} waiting in To check:\n\n{names}\n\n"
            f"Open the folder: {link}\n\nMove each photo you're happy with into its team folder (select it, then "
            f"Move to), and delete any that shouldn't be used. Photos in To check are never posted.\n\n"
            f"(Sent automatically by the Verwood social media kit.)")
    s = mailer.settings(env)
    if not s:
        return 0
    (send or mailer.send)(s, f"{cfg.short_name_upper} social media: {len(new)} new photo{'s' if len(new) != 1 else ''} to check", text)
    return len(new)
