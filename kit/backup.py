"""Weekly backup of the kit (and the private photo store) to the club's SharePoint.

The workflow makes a git bundle of each repository: one file holding every file and its whole history,
which can be turned back into a repository anywhere with `git clone <file>.bundle`. This uploads them to
club.yml → backup → site / folder, one dated subfolder per week, and keeps the newest `keep` weeks.

Uses the same Microsoft 365 app as the emails (M365_* secrets). It needs one extra application
permission, Sites.Selected, with admin consent, and write access granted on that one site
(docs/BACKUP-SETUP.md). The app can't see any other SharePoint site.
"""
import logging
import re
from datetime import date
from pathlib import Path

import requests

from . import mailer

log = logging.getLogger(__name__)
GRAPH = "https://graph.microsoft.com/v1.0"
CHUNK = 5 * 1024 * 1024  # a multiple of 320 KiB, as Graph asks
WEEK = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BackupError(RuntimeError):
    pass


class SharePoint:
    def __init__(self, settings, http=None):
        self.http = http or requests.Session()
        try:
            self.token = mailer._token(settings, self.http)
        except mailer.MailError as e:
            raise BackupError(str(e))

    def _req(self, method, url, ok=(200, 201, 204), **kw):
        kw.setdefault("timeout", 120)
        r = self.http.request(method, url if url.startswith("http") else GRAPH + url,
                              headers={"Authorization": f"Bearer {self.token}", **kw.pop("headers", {})}, **kw)
        if r.status_code not in ok:
            err = (r.json().get("error") or {}) if r.content and "json" in r.headers.get("Content-Type", "") else {}
            msg = err.get("message") or r.text[:200]
            if r.status_code in (401, 403):
                msg += (" The Microsoft 365 app needs the Sites.Selected permission (admin consented) and write "
                        "access to this site: see docs/BACKUP-SETUP.md.")
            raise BackupError(f"SharePoint said {r.status_code}: {msg}")
        return r.json() if r.content and "json" in r.headers.get("Content-Type", "") else {}

    def drive(self, site):
        host, _, path = site.partition("/")
        s = self._req("GET", f"/sites/{host}:/{path.strip('/')}")
        d = self._req("GET", f"/sites/{s['id']}/drive")
        return d["id"]

    def folder(self, drive, path):
        """Make sure each folder in path exists; return the last one's item id."""
        parent = "root"
        for name in [p for p in path.split("/") if p]:
            kids = self._req("GET", f"/drives/{drive}/items/{parent}/children",
                             params={"$select": "id,name,folder", "$top": 999})
            hit = next((k for k in kids.get("value", []) if k["name"] == name and "folder" in k), None)
            if not hit:
                hit = self._req("POST", f"/drives/{drive}/items/{parent}/children",
                                json={"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
            parent = hit["id"]
        return parent

    def upload(self, drive, parent, file):
        file = Path(file)
        size = file.stat().st_size
        sess = self._req("POST", f"/drives/{drive}/items/{parent}:/{file.name}:/createUploadSession",
                         json={"item": {"@microsoft.graph.conflictBehavior": "replace"}})
        url, done = sess["uploadUrl"], {}
        with file.open("rb") as f:
            start = 0
            while start < size or size == 0:
                data = f.read(CHUNK)
                end = start + len(data) - 1
                r = self.http.put(url, data=data, timeout=300,
                                  headers={"Content-Length": str(len(data)),
                                           "Content-Range": f"bytes {start}-{end}/{size}"})
                if r.status_code not in (200, 201, 202):
                    raise BackupError(f"Upload of {file.name} stopped ({r.status_code}): {r.text[:200]}")
                done = r.json() if r.content else {}
                start = end + 1
                if size == 0:
                    break
        return done

    def weeks(self, drive, parent):
        kids = self._req("GET", f"/drives/{drive}/items/{parent}/children", params={"$select": "id,name,folder", "$top": 999})
        return sorted((k for k in kids.get("value", []) if "folder" in k and WEEK.match(k["name"])),
                      key=lambda k: k["name"])

    def remove(self, drive, item):
        """Moves the old week to the SharePoint recycle bin (it can be restored from there for 93 days)."""
        self._req("DELETE", f"/drives/{drive}/items/{item}")


def run(cfg, env, files, today=None, http=None):
    """Upload the backup files; returns lines for the job summary."""
    b = cfg["backup"]
    today = today or date.today()
    files = [Path(f) for f in files if Path(f).exists()]
    if not files:
        raise BackupError("Nothing to back up: the backup files weren't made.")
    try:
        s = mailer.settings(env)
    except mailer.MailError as e:
        raise BackupError(str(e))
    if not s:
        raise BackupError("Microsoft 365 isn't set up (the M365_* secrets), so there's nowhere to save the backup.")
    sp = SharePoint(s, http)
    drive = sp.drive(b["site"])
    root = sp.folder(drive, b["folder"])
    week = sp.folder(drive, f"{b['folder']}/{today:%Y-%m-%d}")
    lines = []
    for f in files:
        sp.upload(drive, week, f)
        lines.append(f"- ✅ Saved **{f.name}** ({f.stat().st_size / 1_048_576:.1f} MB)")
    old = sp.weeks(drive, root)[:-int(b["keep"])] if int(b["keep"]) > 0 else []
    for w in old:
        sp.remove(drive, w["id"])
    if old:
        lines.append(f"- 🗑️ Moved {len(old)} older backup(s) to the SharePoint recycle bin: "
                     + ", ".join(w["name"] for w in old))
    lines.append(f"Backups are in {b['site']} → Documents → {b['folder']}.")
    return lines
