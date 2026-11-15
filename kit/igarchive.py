"""Instagram archive: the photos from the club's own Instagram posts, saved to the SharePoint photo store.

    Social media photos/Instagram archive/<YYYY-MM>/<date> <start of caption>[ n].jpg   the whole photo
    Social media photos/Instagram archive/<YYYY-MM>/Crops/<same name> person <k>.jpg   head-and-shoulders crops

The kit's own graphics (and the earlier Metricool version's) are skipped: their captions end with the club's
hashtag line. For a video, only its cover image is saved. Crops come from face DETECTION (OpenCV's built-in
detector): it finds where faces are, never who anyone is. Small faces are skipped, as their crops would be too
soft to use. Each file keeps its Instagram date, so moving an old photo into a team folder can never make it
look like a photo from a recent game. The archive folder is never used for posts and isn't copied by the
photo sync; the social media team moves the photos they want into team or adults folders.
"""
import io
import json
import logging
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .backup import BackupError

log = logging.getLogger(__name__)
ARCHIVE = "Instagram archive"
STATE = "state/ig-archive.json"
FIELDS = ("id,caption,timestamp,media_type,media_url,thumbnail_url,permalink,"
          "children{id,media_type,media_url,thumbnail_url}")


def is_kit_graphic(caption, tags):
    return bool(tags) and tags in (caption or "")


def safe_name(when, caption, n=None):
    """'2025-07-12 Well done to our ladies A team 2.jpg': the date and the start of the caption."""
    first = next((l.strip() for l in (caption or "").splitlines() if l.strip()), "")
    first = re.sub(r"[#@]\w+", "", first)
    first = re.sub(r"[^\w '&,.!-]", "", first).strip(" .,")
    if len(first) > 60:
        first = first[:60].rsplit(" ", 1)[0]
    base = f"{when:%Y-%m-%d} {first}".strip() if first else f"{when:%Y-%m-%d} photo"
    return f"{base}{f' {n}' if n else ''}.jpg"


def media_since(meta, since):
    """Every post on the Instagram account since `since` (newest first), following the pages."""
    meta.resolve()
    if not meta.ig_id:
        raise BackupError("No Instagram account is linked to the Facebook Page.")
    out, after = [], None
    while True:
        params = {"fields": FIELDS, "limit": 50}
        if after:
            params["after"] = after
        page = meta._call("GET", f"{meta.ig_id}/media", token=meta.page_token, **params)
        stop = False
        for m in page.get("data", []):
            when = datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
            if when < since:
                stop = True
                break
            out.append(m)
        after = ((page.get("paging") or {}).get("cursors") or {}).get("after")
        if stop or not after or not (page.get("paging") or {}).get("next"):
            return out


def images_of(m):
    """[(media id, image url)] for a post: each photo of a carousel; a video's cover image."""
    items = (m.get("children") or {}).get("data") or [m]
    out = []
    for c in items:
        url = c.get("media_url") if c.get("media_type") != "VIDEO" else c.get("thumbnail_url")
        if url:
            out.append((c.get("id") or m["id"], url))
    return out


def crops(jpeg_bytes, min_face=70):
    """Head-and-shoulders crops (JPEG bytes, 4:5) around each face found in the photo."""
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    h, w = img.shape[:2]
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = det.detectMultiScale(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), scaleFactor=1.1, minNeighbors=7,
                                 minSize=(min_face, min_face))
    out = []
    for (x, y, fw, fh) in sorted(faces, key=lambda f: f[0]):
        cw = int(fw * 3.2)
        ch = int(cw * 5 / 4)
        cx = x + fw // 2
        left = max(0, min(w - cw, cx - cw // 2)) if cw <= w else 0
        top = max(0, min(h - ch, y - int(fh * 0.9))) if ch <= h else 0
        crop = img[top:top + min(ch, h), left:left + min(cw, w)]
        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if ok:
            out.append(buf.tobytes())
    return out


def run(cfg, env, meta, http_get, sp, root, years=2, now=None, do_crops=True):
    """Save the photos. sp: a backup.SharePoint. Returns summary lines."""
    ps = cfg["photo_store"]
    tags = (cfg["club"].get("hashtags") or "").strip()
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=int(365.25 * years))
    state_path = Path(root) / STATE
    try:
        done = set(json.loads(state_path.read_text()))
    except (FileNotFoundError, ValueError):
        done = set()
    drive = sp.drive(ps["site"])
    folders = {}

    def folder(path):
        if path not in folders:
            folders[path] = sp.folder(drive, path)
        return folders[path]
    posts = media_since(meta, since)
    saved = cropped = skipped = 0
    for m in posts:
        if is_kit_graphic(m.get("caption"), tags):
            skipped += 1
            continue
        when = datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
        imgs = images_of(m)
        where = f"{ps['folder']}/{ARCHIVE}/{when:%Y-%m}"
        for i, (mid, url) in enumerate(imgs, 1):
            if mid in done:
                continue
            r = http_get(url, timeout=120)
            if r.status_code != 200:
                log.warning("Couldn't download %s (%s)", m.get("permalink"), r.status_code)
                continue
            name = safe_name(when, m.get("caption"), i if len(imgs) > 1 else None)
            stamp = when.isoformat().replace("+00:00", "Z")
            with tempfile.TemporaryDirectory() as d:
                f = Path(d) / name
                f.write_bytes(r.content)
                sp.upload(drive, folder(where), f, created=stamp)
                saved += 1
                if do_crops:
                    for k, c in enumerate(crops(r.content), 1):
                        cf = Path(d) / f"{Path(name).stem} person {k}.jpg"
                        cf.write_bytes(c)
                        sp.upload(drive, folder(f"{where}/Crops"), cf, created=stamp)
                        cropped += 1
            done.add(mid)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(sorted(done)) + "\n")  # ids only: safe to rerun
    return [f"- ✅ {len(posts)} Instagram posts since {since:%d %B %Y}; {skipped} were club graphics and skipped.",
            f"- 📷 Saved {saved} photo(s) and {cropped} person crop(s) to {ps['folder']} → {ARCHIVE}."]
