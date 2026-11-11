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
GENERIC = ["Indoor", "Juniors", "Club"]


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
    return ([f"match-photos/{t}" for t in teams + GENERIC] + ["adults", "juniors"])


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
    params = {"$select": "id,name,folder,file,size,@microsoft.graph.downloadUrl", "$top": 999}
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
                walk(k["id"], rel / k["name"])
            elif Path(k["name"]).suffix.lower() in PHOTO_TYPES and k.get("@microsoft.graph.downloadUrl"):
                out = dest / rel / k["name"]
                out.parent.mkdir(parents=True, exist_ok=True)
                r = sp.http.get(k["@microsoft.graph.downloadUrl"], timeout=120)
                if r.status_code == 200:
                    out.write_bytes(r.content)
                    count += 1
                else:
                    log.warning("Couldn't download %s (%s)", rel / k["name"], r.status_code)
    walk(root, Path("."))
    return count
