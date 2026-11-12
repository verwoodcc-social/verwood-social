"""Word copies of the kit's documents in the club SharePoint (club.yml → word_docs).

Claude saves each document as Markdown in <folder>/Markdown. This turns every one of them into a Word
document of the same name in <folder>, replacing the Word copy when the Markdown has changed. The text
never passes through the (public) repository: it's read from SharePoint and written back there.
"""
import logging
import subprocess
import tempfile
from pathlib import Path

from . import mailer
from .backup import BackupError, SharePoint

log = logging.getLogger(__name__)


def _sp(env, http=None):
    try:
        s = mailer.settings(env)
    except mailer.MailError as e:
        raise BackupError(str(e))
    if not s:
        raise BackupError("Microsoft 365 isn't set up (the M365_* secrets).")
    return SharePoint(s, http)


def _pandoc():
    try:
        import pypandoc
        return pypandoc.get_pandoc_path()
    except Exception:
        return "pandoc"


def convert(md_bytes, out, title):
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.md"
        src.write_bytes(md_bytes)
        subprocess.run([_pandoc(), str(src), "-f", "gfm", "-t", "docx", "-o", str(out)],
                       check=True, capture_output=True, timeout=120)
    return out


def run(cfg, env, http=None, convert_fn=convert):
    """Make or refresh the Word copies. Returns lines for the job summary."""
    wd = cfg["word_docs"]
    sp = _sp(env, http)
    drive = sp.drive(wd["site"])
    folder = sp.folder(drive, wd["folder"])
    source = sp.folder(drive, f"{wd['folder']}/Markdown")
    words = {k["name"]: k for k in sp._req("GET", f"/drives/{drive}/items/{folder}/children",
                                            params={"$top": 999}).get("value", []) if "file" in k}
    lines = []
    for k in sp._req("GET", f"/drives/{drive}/items/{source}/children", params={"$top": 999}).get("value", []):
        if "file" not in k or not k["name"].lower().endswith(".md"):
            continue
        name = k["name"][:-3] + ".docx"
        have = words.get(name)
        if have and have.get("lastModifiedDateTime", "") >= k.get("lastModifiedDateTime", ""):
            continue  # Word copy is newer than the Markdown
        r = sp.http.get(f"https://graph.microsoft.com/v1.0/drives/{drive}/items/{k['id']}/content",
                        headers={"Authorization": f"Bearer {sp.token}"}, timeout=120)
        if r.status_code != 200:
            lines.append(f"- ⚠️ Couldn't read {k['name']} ({r.status_code})")
            continue
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / name
            convert_fn(r.content, out, k["name"][:-3])
            sp.upload(drive, folder, out)
        lines.append(f"- ✅ {name}")
    return lines or ["- ✅ All Word copies are up to date."]
