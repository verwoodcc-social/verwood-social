"""Command-line entry points used by the GitHub workflows.

  python -m kit make     [--today YYYY-MM-DD] [--only fixtures|roundup|matches]
  python -m kit announce --sha <commit>      # after the images are committed and pushed
  python -m kit publish  --issue <number>    # when an issue gets the 'approved' label
  python -m kit check                        # test the setup and render sample graphics
  python -m kit preview  --sha <commit>      # open an issue showing the sample graphics
"""
import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from . import config as C
from . import posts as P
from .meta import Meta, MetaError
from .playcricket import PlayCricket, PlayCricketError
from .review import GitHub, GitHubError, issue_body, parse_issue, raw_url

log = logging.getLogger("kit")
PENDING = ".kit-pending.json"
STATE = "state/posted.json"
DONE_MARK = "<!-- csk-done "


# --- small utilities ---------------------------------------------------------

class Report:
    """Collects lines for the job summary page in GitHub Actions, and prints them."""

    def __init__(self, title):
        self.lines = [f"## {title}", ""]

    def add(self, line=""):
        print(line)
        self.lines.append(line)

    def write(self):
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if path:
            with open(path, "a") as f:
                f.write("\n".join(self.lines) + "\n")


def load_state(root):
    p = root / STATE
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, ValueError):
        return {"posted": {}}


def save_state(root, state):
    p = root / STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def today_for(cfg, override=None):
    return date.fromisoformat(override) if override else datetime.now(cfg.tz).date()


def due_jobs(cfg, today, only=None):
    p = cfg["posts"]
    wd = C.DAYS[today.weekday()]
    jobs = []
    if p["fixtures"]["enabled"] and (only == "fixtures" or (not only and p["fixtures"]["day"].lower() == wd)):
        jobs.append("fixtures")
    if p["results_roundup"]["enabled"] and (only == "roundup" or (not only and p["results_roundup"]["day"].lower() == wd)):
        jobs.append("roundup")
    if p["match_results"]["enabled"] and only in (None, "matches"):
        jobs.append("matches")
    return jobs


def strip_private(data):
    """date objects can't go into JSON."""
    if isinstance(data, dict):
        return {k: strip_private(v) for k, v in data.items() if k != "date_obj"}
    if isinstance(data, list):
        return [strip_private(v) for v in data]
    return data


KEEP_IMAGES_DAYS = 60


def clear_old_images(root, today):
    """Delete post images older than KEEP_IMAGES_DAYS (they're already on Facebook / Instagram)."""
    import shutil
    for d in (root / "posts").glob("????-??-??"):
        try:
            if (today - date.fromisoformat(d.name)).days > KEEP_IMAGES_DAYS:
                shutil.rmtree(d)
        except ValueError:
            pass


# --- make --------------------------------------------------------------------

def cmd_make(args, root=C.ROOT, pc=None, renderer=None):
    rep = Report("Make posts")
    cfg = C.load(root / "club.yml")
    today = today_for(cfg, args.today)
    only = args.only or os.environ.get("KIT_ONLY") or None
    if only in ("", "all-due"):
        only = None
    jobs = due_jobs(cfg, today, only)
    rep.add(f"**{cfg['club']['name']}** · {today:%A %d %B %Y} · checking: {', '.join(jobs) or 'nothing due today'}")
    clear_old_images(root, today)
    state = load_state(root)
    pc = pc or PlayCricket(os.environ.get("PLAYCRICKET_API_TOKEN"), cfg.site_id)
    made, notes = [], []
    if "fixtures" in jobs:
        p = P.fixtures_post(cfg, pc, today)
        (made.append(p) if p else notes.append("No fixtures in the next 7 days."))
    if "roundup" in jobs:
        p = P.roundup_post(cfg, pc, today)
        (made.append(p) if p else notes.append("No results in the last 7 days."))
    if "matches" in jobs:
        ms, skipped = P.match_posts(cfg, pc, today, state["posted"])
        made += ms
        notes += [f"Not posted: {s}" for s in skipped]
        if not ms and not skipped:
            notes.append("No new match results.")
    made = [p for p in made if p["key"] not in state["posted"]]

    out_dir = Path("posts") / today.isoformat()
    pending = []
    if made:
        from .render import Renderer
        with (renderer or Renderer()) as r:
            for p in made:
                files = r.render(cfg, p["data"], root / out_dir, p["key"])
                pending.append({**strip_private({k: v for k, v in p.items() if k != "data"}),
                                "files": [str(f.relative_to(root)) for f in files]})
    (root / PENDING).write_text(json.dumps(pending, indent=2))
    rep.add("")
    for p in pending:
        rep.add(f"- 🖼️ **{p['title']}** ({len(p['files'])} image{'s' if len(p['files']) > 1 else ''})")
    for n in notes:
        rep.add(f"- {n}")
    rep.write()
    return pending


# --- announce: open issues (review) or post straight away (automatic) ---------

def cmd_announce(args, root=C.ROOT, gh=None, meta=None):
    rep = Report("Posts ready")
    cfg = C.load(root / "club.yml")
    pending = json.loads((root / PENDING).read_text()) if (root / PENDING).exists() else []
    if not pending:
        rep.add("Nothing new to post.")
        rep.write()
        return []
    gh = gh or GitHub()
    gh.ensure_labels()
    state = load_state(root)
    nets = cfg["posts"]["networks"]
    auto = cfg["posts"]["approval"] == "automatic"
    opened = []
    for p in pending:
        urls = [raw_url(gh.repo, args.sha, f) for f in p["files"]]
        body = issue_body(p, urls, nets)
        if auto:
            issue = gh.create_issue(p["title"], body)
            links, error = [], None
            for n in nets:
                try:
                    links.append(publish_to(cfg, meta, urls, p["caption"], [n])[0])
                except MetaError as e:
                    error = f"Couldn't post to {n.capitalize()}: {e}"
                    break
                gh.comment(issue["number"], f"✅ Posted to {n.capitalize()}: {links[-1]['url']}\n"
                                            f"{DONE_MARK}{json.dumps({'network': n})} -->")
            if error:
                gh.comment(issue["number"], f"❌ {error}\n\nOnce it's fixed, add the **approved** label to retry. "
                                            f"Anything already posted won't be posted twice.")
                gh.add_labels(issue["number"], ["failed"])
                rep.add(f"- ❌ **{p['title']}**: {error} · {issue['html_url']}")
            else:
                gh.add_labels(issue["number"], ["published"])
                gh.close(issue["number"])
                rep.add(f"- ✅ Posted **{p['title']}** · {issue['html_url']}")
        else:
            issue = gh.create_issue(p["title"], body)
            rep.add(f"- 👀 **{p['title']}** is waiting for approval · {issue['html_url']}")
        state["posted"][p["key"]] = {"issue": issue["number"], "made": date.today().isoformat()}
        save_state(root, state)  # after each, so a failure part-way doesn't repeat earlier posts
        opened.append(issue["number"])
    (root / PENDING).unlink(missing_ok=True)
    rep.write()
    return opened


_META = {}


def publish_to(cfg, meta, urls, caption, networks, skip=()):
    if meta is None:  # reuse one connection across posts in a run
        meta = _META.setdefault("m", Meta(os.environ.get("META_TOKEN"), cfg["facebook"].get("page_id")))
    links = []
    for n in networks:
        if n in skip:
            continue
        links.append(meta.post_facebook(urls, caption) if n == "facebook" else meta.post_instagram(urls, caption))
    return links


# --- publish one approved issue ----------------------------------------------

def cmd_publish(args, root=C.ROOT, gh=None, meta=None):
    cfg = C.load(root / "club.yml")
    gh = gh or GitHub()
    issue = gh.get_issue(args.issue)
    labels = {l["name"] for l in issue.get("labels", [])}
    if "social-post" not in labels or "approved" not in labels:
        print("Not an approved social post; nothing to do.")
        return None
    if issue.get("user", {}).get("login") != "github-actions[bot]":
        gh.comment(args.issue, "⚠️ Only posts opened by the kit itself can be published.")
        return None
    if "published" in labels or issue.get("state") != "open":
        print("Already published or closed.")
        return None
    try:
        meta_info, caption = parse_issue(issue.get("body", ""))
    except GitHubError as e:
        gh.comment(args.issue, f"⚠️ {e}")
        gh.remove_label(args.issue, "approved")
        return None
    if meta_info.get("sample"):
        gh.comment(args.issue, "This is a sample preview, so it can't be posted. Close it whenever you like.")
        gh.remove_label(args.issue, "approved")
        return None
    prefix = f"https://raw.githubusercontent.com/{gh.repo}/"
    urls = meta_info.get("images", [])
    if not urls or any(not u.startswith(prefix) for u in urls):
        gh.comment(args.issue, "⚠️ The images in this issue don't come from this repository, so I won't post them.")
        gh.remove_label(args.issue, "approved")
        return None
    nets = [n for n in meta_info.get("networks", []) if n in cfg["posts"]["networks"]]
    done = already_done(gh, args.issue)
    meta = meta or Meta(os.environ.get("META_TOKEN"), cfg["facebook"].get("page_id"))
    links, error = [], None
    for n in nets:
        if n in done:
            continue
        try:
            link = meta.post_facebook(urls, caption) if n == "facebook" else meta.post_instagram(urls, caption)
        except MetaError as e:
            error = (n, str(e))
            break
        links.append(link)
        gh.comment(args.issue, f"✅ Posted to {n.capitalize()}: {link['url']}\n{DONE_MARK}{json.dumps({'network': n})} -->")
    if error:
        n, msg = error
        gh.comment(args.issue, f"❌ Couldn't post to {n.capitalize()}: {msg}\n\nOnce it's fixed, add the **approved** "
                               f"label again to retry. Anything already posted won't be posted twice.")
        gh.add_labels(args.issue, ["failed"])
        gh.remove_label(args.issue, "approved")
        return False
    gh.remove_label(args.issue, "failed")
    gh.add_labels(args.issue, ["published"])
    gh.close(args.issue)
    return links


def already_done(gh, number):
    done = set()
    for c in gh._req("GET", f"issues/{number}/comments", params={"per_page": 100}):
        body = c.get("body", "")
        if DONE_MARK in body and c.get("user", {}).get("login") == "github-actions[bot]":
            try:
                done.add(json.loads(body.split(DONE_MARK, 1)[1].split("-->", 1)[0])["network"])
            except (ValueError, KeyError):
                pass
    return done


# --- check setup -------------------------------------------------------------

def customisations(cfg):
    """Plain-English list of the uploads and changes a club has made, for the setup check."""
    b, out = cfg["branding"], []
    general = b.get("background_image")
    per = {k: b.get(f"{k}_background") for k in ("fixtures", "results", "match")}
    if general:
        out.append(f"Background photo: {general}" + (" (some post types use their own, below)" if any(per.values()) else ""))
    for k, v in per.items():
        if v:
            out.append(f"{k.capitalize()} background photo: {v}")
    if general or any(per.values()):
        out.append(f"Colour over photos: {b.get('background_darkness', 'medium')}")
    if b.get("sponsor_logo") or b.get("sponsor_text"):
        what = b.get("sponsor_logo") or b.get("sponsor_text")
        out.append(f"Sponsor: {what}" + (" (also named in captions)" if b.get("sponsor_in_captions") else ""))
    changed = [k for k, v in cfg["wording"].items() if v != C.DEFAULTS["wording"][k]]
    if changed:
        out.append("Your own wording for: " + ", ".join(k.replace("_", " ") for k in changed))
    hidden = [k.replace("_", " ") for k, v in cfg["show"].items() if v != C.DEFAULTS["show"][k]]
    if hidden:
        out.append("Changed show settings: " + ", ".join(hidden))
    own = cfg.root / "my-templates"
    if own.is_dir() and any(own.iterdir()):
        out.append("Your own designs from my-templates: " + ", ".join(sorted(p.name for p in own.iterdir())))
    return out


def cmd_check(args, root=C.ROOT, pc=None, meta=None, gh=None, renderer=None):
    rep = Report("Setup check")
    ok = True
    try:
        cfg = C.load(root / "club.yml")
        rep.add(f"✅ **club.yml** looks good: {cfg['club']['name']} (Play-Cricket site {cfg.site_id})")
        for line in customisations(cfg):
            rep.add(f"   🎨 {line}")
        for w in cfg.warnings:
            rep.add(f"   ⚠️ {w}")
    except C.ConfigError as e:
        rep.add("❌ **club.yml** needs fixing:")
        rep.add("")
        rep.add(str(e))
        rep.write()
        return False
    today = today_for(cfg, getattr(args, "today", None))

    # Play-Cricket
    try:
        pc = pc or PlayCricket(os.environ.get("PLAYCRICKET_API_TOKEN"), cfg.site_id)
        from datetime import timedelta
        fx = pc.fixtures(today, today + timedelta(days=30))
        rs = pc.results(today - timedelta(days=60), today - timedelta(days=1))
        ours_f, ours_r = P.fixture_rows(cfg, fx), P.result_rows(cfg, rs)
        rep.add(f"✅ **Play-Cricket** connected: {len(ours_f)} fixtures in the next 30 days, "
                f"{len(ours_r)} results in the last 60 days.")
        if (fx or rs) and not (ours_f or ours_r):
            ok = False
            rep.add(f"   ⚠️ Matches were found but none look like yours. Check club → play_cricket_name is exactly "
                    f"how Play-Cricket writes your club (e.g. \"{(fx or rs)[0].get('home_club_name')}\").")
        if not (fx or rs):
            rep.add("   (No matches found: that's normal out of season.)")
    except PlayCricketError as e:
        ok = False
        rep.add(f"❌ **Play-Cricket**: {e}")

    # Meta
    nets = cfg["posts"]["networks"]
    try:
        meta = meta or Meta(os.environ.get("META_TOKEN"), cfg["facebook"].get("page_id"))
        info = meta.resolve()
        if "facebook" in nets:
            rep.add(f"✅ **Facebook** connected: will post to the Page \"{info['page_name']}\".")
        if "instagram" in nets:
            if info["instagram_id"]:
                rep.add(f"✅ **Instagram** connected: will post as @{info['instagram_username']}.")
            else:
                ok = False
                rep.add("❌ **Instagram**: your Facebook Page has no Instagram professional account linked. "
                        "Link them, or remove instagram from posts → networks in club.yml.")
    except MetaError as e:
        ok = False
        rep.add(f"❌ **Facebook / Instagram**: {e}")

    # Repository must be public so Instagram can fetch the images
    try:
        gh = gh or GitHub()
        info = gh.repo_info()
        if info.get("private"):
            ok = False
            rep.add("❌ **Repository** is private. Instagram can only fetch images from a public repository: "
                    "Settings → General → Danger Zone → Change visibility → Public.")
        elif info:
            rep.add("✅ **Repository** is public, so Instagram can fetch the images.")
    except GitHubError:
        pass

    # Sample graphics in the club's branding
    from .samples import sample_posts
    from .render import Renderer
    pending = []
    with (renderer or Renderer()) as r:
        for p in sample_posts(cfg, today):
            files = r.render(cfg, p["data"], root / "posts/samples", p["key"])
            pending.append({**{k: v for k, v in p.items() if k != "data"},
                            "files": [str(f.relative_to(root)) for f in files]})
    (root / PENDING).write_text(json.dumps(pending, indent=2))
    rep.add("✅ **Sample graphics** made in your colours; a preview issue will open in the Issues tab.")
    rep.add("")
    rep.add("**All set!** Posts will be made on schedule." if ok else "**Fix the ❌ items above, then run this check again.**")
    rep.write()
    return ok


def cmd_preview(args, root=C.ROOT, gh=None):
    cfg = C.load(root / "club.yml")
    pending = json.loads((root / PENDING).read_text()) if (root / PENDING).exists() else []
    if not pending:
        return None
    gh = gh or GitHub()
    gh.ensure_labels()
    for old in gh.open_issues(label="social-post"):  # only keep the newest preview open
        if old.get("title", "").startswith("Preview:"):
            gh.close(old["number"])
    urls, captions = [], []
    for p in pending:
        urls += [raw_url(gh.repo, args.sha, f) for f in p["files"]]
        captions.append(p["caption"])
    post = {"key": "sample", "kind": "sample", "title": f"Preview: {cfg['club']['name']} graphics",
            "caption": "\n\n— — —\n\n".join(captions), "alt": "Sample graphics"}
    issue = gh.create_issue(post["title"], issue_body(post, urls, cfg["posts"]["networks"], sample=True))
    (root / PENDING).unlink(missing_ok=True)
    print(issue["html_url"])
    return issue["number"]


# --- main --------------------------------------------------------------------

def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(prog="python -m kit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--today")
    m.add_argument("--only", choices=["fixtures", "roundup", "matches", "all-due"])
    a = sub.add_parser("announce")
    a.add_argument("--sha", required=True)
    pub = sub.add_parser("publish")
    pub.add_argument("--issue", type=int, required=True)
    ch = sub.add_parser("check")
    ch.add_argument("--today")
    pv = sub.add_parser("preview")
    pv.add_argument("--sha", required=True)
    args = ap.parse_args(argv)
    try:
        result = {"make": cmd_make, "announce": cmd_announce, "publish": cmd_publish,
                  "check": cmd_check, "preview": cmd_preview}[args.cmd](args)
    except (C.ConfigError, PlayCricketError, MetaError, GitHubError) as e:
        rep = Report("Something needs attention")
        rep.add(f"❌ {e}")
        rep.write()
        return 1
    if args.cmd == "check" and result is False:
        return 1
    if args.cmd == "publish" and result is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
