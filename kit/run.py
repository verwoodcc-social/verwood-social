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
RUN_LOG = ".kit-run-log.md"


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
            with open(RUN_LOG, "a") as f:  # read back by 'alert' if a later step fails
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
    if cfg["matchday"]["enabled"] and only in (None, "matchday"):
        jobs.append("matchday")
    from .leaderboards import due as lb_due
    if only == "leaderboards" or (not only and lb_due(cfg, today)):
        jobs.append("leaderboards")
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
        cm = cfg["career_milestones"]
        if p and cm["enabled"] and cm["watch"].get("enabled", True):
            from . import careers as K
            start, end = P.week_window(today, "fixtures")
            w = K.watch_post(cfg, K.Careers(cfg, root), P.fixture_rows(cfg, pc.fixtures(start, end)), today,
                             p["data"]["date_range"])
            (made.append(w) if w else notes.append("Nobody is close to a career milestone this week."))
    if "roundup" in jobs:
        p = P.roundup_post(cfg, pc, today)
        (made.append(p) if p else notes.append("No results in the last 7 days."))
    if "matches" in jobs:
        from .milestones import PhotoStore
        photos = PhotoStore(root / "player-photos")
        ms, skipped = P.match_posts(cfg, pc, today, state["posted"], photos=photos)
        made += ms
        if cfg["career_milestones"]["enabled"]:
            from . import careers as K
            car = K.Careers(cfg, root)
            try:
                filled = K.backfill_softball(cfg, pc, car, today)
                if filled:
                    notes.append(f"Added {filled} past Women's Softball games to the softball career totals.")
                made += K.career_posts(cfg, K.new_games(cfg, pc, today, car), photos=photos)
            except PlayCricketError as e:
                notes.append(f"Career totals not updated today: {e}")
            car.save()
        notes += [f"Not posted: {s}" for s in skipped]
        if not ms and not skipped:
            notes.append("No new match results.")
    if "matchday" in jobs:
        p = P.matchday_post(cfg, pc, today)
        (made.append(p) if p else notes.append("No matchday story today (no games, or outside the matchday months)."))
    if "leaderboards" in jobs:
        from .leaderboards import leaderboards_post
        p = leaderboards_post(cfg, pc, today, root)
        (made.append(p) if p else notes.append("No adult scorecards this season yet, so no leaderboards."))
    made = [p for p in made if p["key"] not in state["posted"]]
    if made:
        from .matchphotos import MatchPhotos, add_backgrounds
        used = state.setdefault("match_photos_used", {})
        add_backgrounds(cfg, made, MatchPhotos(root / "player-photos", used), today)
        save_state(root, state)

    out_dir = Path("posts") / today.isoformat()
    pending = []
    if made:
        from .render import Renderer
        with (renderer or Renderer()) as r:
            for p in made:
                stories_only = p.get("stories_only")
                files = [] if stories_only else r.render(cfg, p["data"], root / out_dir, p["key"])
                story = (r.render(cfg, p["data"], root / out_dir, p["key"], story=True)
                         if stories_only or cfg.stories_for(p["kind"]) else [])
                pending.append({**strip_private({k: v for k, v in p.items() if k != "data"}),
                                "bg": bool(p["data"].get("bg_photo")),
                                "files": [str(f.relative_to(root)) for f in files],
                                "story_files": [str(f.relative_to(root)) for f in story]})
    (root / PENDING).write_text(json.dumps(pending, indent=2))
    rep.add("")
    for p in pending:
        extra = f" + {len(p['story_files'])} story" if p.get("story_files") else ""
        extra += " · match photo background" if p.get("bg") else ""
        n = len(p["files"])
        rep.add(f"- 🖼️ **{p['title']}** ({n} image{'s' if n != 1 else ''}{extra})")
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
        story_urls = [raw_url(gh.repo, args.sha, f) for f in p.get("story_files", [])]
        reminder_url = raw_url(gh.repo, args.sha, p["reminder_file"]) if p.get("reminder_file") else ""
        body = issue_body(p, urls, nets, story_urls=story_urls, reminder_url=reminder_url)
        issue = gh.create_issue(p["title"], body)
        if p.get("source_issue"):
            news_link_back(gh, state, p["source_issue"], issue)
        if auto and not p.get("review"):
            links, error = post_all(cfg, gh, issue["number"], meta, targets(nets, urls, story_urls), p["caption"], set())
            if error:
                rep.add(f"- ❌ **{p['title']}**: {error} · {issue['html_url']}")
            else:
                rep.add(f"- ✅ Posted **{p['title']}** · {issue['html_url']}")
        else:
            rep.add(f"- 👀 **{p['title']}** is waiting for approval · {issue['html_url']}")
        state["posted"][p["key"]] = {"issue": issue["number"], "made": date.today().isoformat()}
        save_state(root, state)  # after each, so a failure part-way doesn't repeat earlier posts
        opened.append(issue["number"])
    (root / PENDING).unlink(missing_ok=True)
    rep.write()
    return opened


_META = {}

LABEL = {"facebook": "Facebook", "instagram": "Instagram",
         "facebook_story": "Facebook Stories", "instagram_story": "Instagram Stories"}


def targets(networks, urls, story_urls):
    """Everything to post, in order: feed posts first, then each story frame.
    Each has its own key so a retry only redoes what hasn't gone out yet."""
    out = [(n, n, urls) for n in networks]
    for n in networks:
        for i, u in enumerate(story_urls, 1):
            out.append((f"{n}_story:{i}", f"{n}_story", [u]))
    return out


def post_one(meta, kind, urls, caption):
    if kind == "facebook":
        return meta.post_facebook(urls, caption)
    if kind == "instagram":
        return meta.post_instagram(urls, caption)
    if kind == "facebook_story":
        return meta.post_facebook_story(urls[0])
    return meta.post_instagram_story(urls[0])


def post_all(cfg, gh, number, meta, todo, caption, done):
    """Post each target not already done, recording progress on the issue. Returns (links, error)."""
    if meta is None:  # reuse one connection across posts in a run
        meta = _META.setdefault("m", Meta(os.environ.get("META_TOKEN"), cfg["facebook"].get("page_id")))
    links = []
    for key, kind, urls in todo:
        if key in done:
            continue
        frame = f" (frame {key.split(':')[1]})" if ":" in key and len([t for t in todo if t[1] == kind]) > 1 else ""
        try:
            link = post_one(meta, kind, urls, caption)
        except MetaError as e:
            error = f"Couldn't post to {LABEL[kind]}{frame}: {e}"
            gh.comment(number, f"❌ {error}\n\nOnce it's fixed, add the **approved** label to retry. "
                               f"Anything already posted won't be posted twice.")
            gh.add_labels(number, ["failed"])
            gh.remove_label(number, "approved")
            from . import alerts
            title = ""
            try:
                title = gh.get_issue(number).get("title", "")
            except Exception:
                pass
            alerts.problem(gh, f"post:{number}", f"A post didn't go out: {title or f'#{number}'}", error,
                           f"https://github.com/{gh.repo}/issues/{number}", club=cfg.short_name_upper)
            return links, error
        links.append(link)
        gh.comment(number, f"✅ Posted to {LABEL[kind]}{frame}: {link['url']}\n{DONE_MARK}{json.dumps({'network': key})} -->")
    gh.remove_label(number, "failed")
    gh.add_labels(number, ["published"])
    gh.close(number)
    from . import alerts
    alerts.resolved(gh, f"post:{number}", club=cfg.short_name_upper)
    return links, None


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
    story_urls = meta_info.get("stories", [])
    if not (urls or story_urls) or any(not u.startswith(prefix) for u in urls + story_urls):
        gh.comment(args.issue, "⚠️ The images in this issue don't come from this repository, so I won't post them.")
        gh.remove_label(args.issue, "approved")
        return None
    post_on = meta_info.get("post_on")
    if post_on and date.fromisoformat(post_on) > today_for(cfg, getattr(args, "today", None)):
        if "scheduled" not in labels:
            gh.add_labels(args.issue, ["scheduled"])
            gh.comment(args.issue, f"✅ Approved. This will be posted on **{P.long_date(date.fromisoformat(post_on))}** "
                                   f"with the morning run (about 6:20am). To stop it, remove the **approved** label "
                                   f"or close this issue.")
        return None
    nets = [n for n in meta_info.get("networks", []) if n in cfg["posts"]["networks"]]
    if "scheduled" in labels:
        gh.remove_label(args.issue, "scheduled")
    links, error = post_all(cfg, gh, args.issue, meta, targets(nets, urls, story_urls), caption,
                            already_done(gh, args.issue))
    return False if error else links


# --- club news: the form, scheduled posts and event reminders ----------------

def news_link_back(gh, state, source, issue):
    """Point the form at its preview, and close any earlier preview it replaces."""
    news = state.setdefault("news", {})
    old = news.get(str(source))
    if old and old != issue["number"]:
        try:
            prev = gh.get_issue(old)
            names = {l["name"] for l in prev.get("labels", [])}
            if prev.get("state") == "open" and "published" not in names:
                gh.comment(old, f"Replaced by #{issue['number']} because the form was edited.")
                gh.close(old)
        except GitHubError:
            pass
    news[str(source)] = issue["number"]
    gh.comment(source, f"👀 Here's the preview: #{issue['number']}\n\nCheck the graphic and caption there, then add "
                       f"the **approved** label to post it. To change anything, edit this form and a new preview "
                       f"will replace that one.")


def cmd_news(args, root=C.ROOT, gh=None, renderer=None, session=None):
    """Turn a filled-in 'Club news or event' form into a post waiting for approval."""
    from . import news as N
    from .matchphotos import MatchPhotos
    import requests

    cfg = C.load(root / "club.yml")
    gh = gh or GitHub()
    rep = Report("Club news")
    issue = gh.get_issue(args.issue)
    names = {l["name"] for l in issue.get("labels", [])}
    if "club-news" not in names:
        print("Not a club news form; nothing to do.")
        return None
    if issue.get("author_association") not in N.TRUSTED:
        print("Form opened by someone without access to this repository; ignored.")
        return None
    if not cfg["news"]["enabled"]:
        gh.comment(args.issue, "Club news posts are switched off in club.yml (news → enabled).")
        return None
    today = today_for(cfg, getattr(args, "today", None))
    form = N.parse_form(issue.get("body", ""))
    photo = None
    url = N.photo_url(N.field(form, "photo"))
    tmp = root / "player-photos" / ".news"
    if url:
        try:
            photo = N.download_photo(url, session or requests.Session(), tmp)
        except Exception:
            photo = None
        if not photo:
            gh.comment(args.issue, "⚠️ I couldn't open the attached photo, so the graphic uses a club photo instead.")
    if not photo and "news" in cfg["match_photos"]["use_for"]:
        state = load_state(root)
        photo = MatchPhotos(root / "player-photos", state.setdefault("match_photos_used", {})).pick(
            cfg, "", f"news-{args.issue}", today, any_folder=True)
        save_state(root, state)
    try:
        post = N.build(cfg, form, args.issue, today, photo)
    except N.FormError as e:
        gh.comment(args.issue, f"⚠️ {e}\n\nEdit the form to fix it and I'll try again.")
        rep.add(f"❌ {e}")
        rep.write()
        return None
    out_dir = Path("posts") / "news"
    from .render import Renderer
    with (renderer or Renderer()) as r:
        files = r.render(cfg, post["data"], root / out_dir, post["key"])
        story = r.render(cfg, post["data"], root / out_dir, post["key"], story=True) if cfg.stories_for("news") else []
        rem = []
        if post.get("reminder_data"):
            rem = r.render(cfg, post["reminder_data"], root / out_dir, post["key"] + "-reminder", story=True)
    pending = [{**strip_private({k: v for k, v in post.items() if k not in ("data", "reminder_data")}),
                "files": [str(f.relative_to(root)) for f in files],
                "story_files": [str(f.relative_to(root)) for f in story],
                "reminder_file": str(rem[0].relative_to(root)) if rem else ""}]
    (root / PENDING).write_text(json.dumps(pending, indent=2))
    rep.add(f"- 🖼️ **{post['title']}** ready for approval")
    rep.write()
    return pending


def cmd_due(args, root=C.ROOT, gh=None, meta=None):
    """Morning run: post approved news whose date has come, and today's event reminder Stories."""
    cfg = C.load(root / "club.yml")
    gh = gh or GitHub()
    rep = Report("Scheduled posts and reminders")
    today = today_for(cfg, getattr(args, "today", None))
    for issue in gh.open_issues("scheduled"):
        names = {l["name"] for l in issue.get("labels", [])}
        if {"social-post", "approved"} <= names:
            result = cmd_publish(argparse.Namespace(issue=issue["number"], today=getattr(args, "today", None)),
                                 root=root, gh=gh, meta=meta)
            if result:
                rep.add(f"- ✅ Posted scheduled **{issue['title']}**")
    nets = cfg["posts"]["networks"]
    recent = gh._req("GET", "issues", params={"state": "closed", "labels": "social-post,published",
                                              "sort": "updated", "per_page": 100})
    for issue in recent:
        try:
            info, _ = parse_issue(issue.get("body", ""))
        except GitHubError:
            continue
        r = info.get("reminder") or {}
        if r.get("date") != today.isoformat() or not r.get("story", "").startswith(
                f"https://raw.githubusercontent.com/{gh.repo}/"):
            continue
        if (issue.get("closed_at") or "")[:10] == today.isoformat():
            continue  # posted today anyway: no need to remind
        done = already_done(gh, issue["number"])
        if meta is None:
            meta = _META.setdefault("m", Meta(os.environ.get("META_TOKEN"), cfg["facebook"].get("page_id")))
        for n in nets:
            key = f"{n}_story:reminder"
            if key in done:
                continue
            try:
                link = post_one(meta, f"{n}_story", [r["story"]], "")
            except MetaError as e:
                gh.comment(issue["number"], f"❌ Couldn't post the reminder to {LABEL[n + '_story']}: {e}")
                rep.add(f"- ❌ Reminder for **{issue['title']}**: {e}")
                continue
            gh.comment(issue["number"], f"⏰ Reminder posted to {LABEL[n + '_story']}: {link['url']}\n"
                                        f"{DONE_MARK}{json.dumps({'network': key})} -->")
            rep.add(f"- ⏰ Reminder Story for **{issue['title']}** on {LABEL[n + '_story']}")
    rep.write()


# --- monthly sponsor report --------------------------------------------------

def insights_check(meta, today, cfg):
    """One line for the setup check: can the token read the figures the sponsor report needs?"""
    from .meta import Insights
    from datetime import timedelta as _td
    ins = Insights(meta)
    end = datetime(today.year, today.month, today.day, tzinfo=cfg.tz)
    fb = ins.page_totals(end - _td(days=7), end)
    ig = ins.ig_totals(end - _td(days=7), end) if meta.ig_id else {"views": 0}
    if fb.get("views") is not None and ig:
        return f"✅ **Sponsor report** can read the figures (Facebook: {fb['views']:,} views in the last 7 days)."
    return ("ℹ️ **Sponsor report**: Meta isn't sharing the view figures yet. Regenerate the Meta token with three extra "
            "permissions, `read_insights`, `pages_read_user_content` and `instagram_manage_insights` (setup guide, step 4c), and update the "
            "META_TOKEN secret. Details: " + "; ".join(ins.problems[:2]))

REPORT_PENDING = ".kit-report.json"


def published_issues(gh, since):
    out = []
    for page in range(1, 6):
        batch = gh._req("GET", "issues", params={"state": "closed", "labels": "social-post,published",
                                                 "since": since.isoformat(), "per_page": 100, "page": page})
        out += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            break
    return out


def cmd_report(args, root=C.ROOT, gh=None, meta=None, render=None):
    """Make the sponsor report for a month (default: last month): PDF + preview image."""
    from . import report as RP
    from .meta import Insights
    cfg = C.load(root / "club.yml")
    gh = gh or GitHub()
    today = today_for(cfg, getattr(args, "today", None))
    if getattr(args, "month", None):
        y, m = (int(x) for x in args.month.split("-"))
        month = (y, m)
    else:
        month = RP.previous_month(today)
    meta = meta or Meta(os.environ.get("META_TOKEN"), cfg["facebook"].get("page_id"))
    ins = Insights(meta)
    start, end = RP.month_bounds(month, cfg.tz)
    state = load_state(root)
    prev_key = f"{RP.previous_month(date(*month, 1))[0]}-{RP.previous_month(date(*month, 1))[1]:02d}"
    r = RP.gather(cfg, ins, published_issues(gh, start), month,
                  (state.get("report_followers") or {}).get(prev_key))
    state.setdefault("report_followers", {})[r["month_key"]] = r["followers"]
    save_state(root, state)
    if render is None:
        from .render import render_report as render
    pdf, jpg = render(cfg, r, root / "posts" / "reports", f"{cfg.short_name.lower()}-social-report-{r['month_key']}")
    out = {"month": r["month"], "month_key": r["month_key"], "pdf": str(pdf.relative_to(root)),
           "jpg": str(jpg.relative_to(root)), "summary": RP.caption(r), "problems": r["problems"]}
    (root / REPORT_PENDING).write_text(json.dumps(out, indent=2))
    rep = Report(f"Sponsor report: {r['month']}")
    rep.add("```\n" + out["summary"] + "\n```")
    for prob in r["problems"]:
        rep.add(f"- ⚠️ {prob}")
    rep.write()
    return out


def cmd_report_issue(args, root=C.ROOT, gh=None):
    """Open the issue holding the report (label 'report': it can't be posted)."""
    cfg = C.load(root / "club.yml")
    pending = root / REPORT_PENDING
    if not pending.exists():
        return None
    r = json.loads(pending.read_text())
    gh = gh or GitHub()
    gh.ensure_labels()
    sponsor = (cfg["branding"].get("sponsor_text") or "your sponsor").strip()
    pdf = f"https://github.com/{gh.repo}/raw/{args.sha}/{r['pdf']}"
    img = raw_url(gh.repo, args.sha, r["jpg"])
    notes = ""
    if r["problems"]:
        notes = ("\n\n<details><summary>Figures Meta didn't provide</summary>\n\n" +
                 "\n".join(f"- {p}" for p in r["problems"]) +
                 "\n\nIf these mention permissions, the Meta token needs `read_insights`, "
                 "`pages_read_user_content` and `instagram_manage_insights` (setup guide, step 4c).\n</details>")
    body = (f"Here's the {r['month']} social media report for {sponsor}.\n\n"
            f"**[⬇️ Download the PDF]({pdf})** to send to {sponsor}. This report is never posted publicly.\n\n"
            f"![{r['month']} report]({img})\n\n### Summary (to paste into an email)\n\n```text\n{r['summary']}\n```"
            f"{notes}\n\nClose this issue once it's been sent.")
    issue = gh.create_issue(f"{sponsor} report: {r['month']}", body, labels=("report",))
    pending.unlink()
    rep = Report("Sponsor report ready")
    rep.add(f"📄 {issue['html_url']}")
    from . import mailer
    try:
        m = mailer.settings()
        if m:
            text = (f"Hello,\n\nAttached is the {r['month']} social media report for {sponsor}, ready to "
                    f"forward.\n\n{r['summary']}\n\nThe report is also here: {issue['html_url']}\n\n"
                    f"(Sent automatically by the Verwood social media kit.)")
            subject = (cfg.get("report") or {}).get("email_subject") or f"{sponsor} social media report: {r['month']}"
            sent = mailer.send(m, subject.replace("{month}", r["month"]), text, [root / r["pdf"]])
            gh.comment(issue["number"], f"📧 Emailed to {len(sent)} committee member{'s' if len(sent) != 1 else ''}.")
            rep.add(f"📧 Emailed to {len(sent)} people.")
    except mailer.MailError as e:
        gh.comment(issue["number"], f"⚠️ The email wasn't sent: {e}")
        rep.add(f"⚠️ Email not sent: {e}")
    rep.write()
    return issue["number"]


# --- problem alerts ------------------------------------------------------------

def cmd_alert(args, root=C.ROOT, gh=None):
    """A workflow failed: record the problem and email the committee."""
    from . import alerts
    cfg = C.load(root / "club.yml")
    gh = gh or GitHub()
    log = (root / RUN_LOG).read_text() if (root / RUN_LOG).exists() else ""
    details = alerts.problem_lines(log) or "The job stopped part-way. The link below shows where."
    gh.ensure_labels()
    return alerts.problem(gh, args.key, args.title, details, args.link or "", quiet_first=args.quiet_first,
                          club=cfg.short_name_upper)


def cmd_resolved(args, root=C.ROOT, gh=None):
    from . import alerts
    cfg = C.load(root / "club.yml")
    gh = gh or GitHub()
    return alerts.resolved(gh, args.key, club=cfg.short_name_upper)


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
    pc_ok = False
    try:
        pc = pc or PlayCricket(os.environ.get("PLAYCRICKET_API_TOKEN"), cfg.site_id)
        from datetime import timedelta
        fx = pc.fixtures(today, today + timedelta(days=30))
        rs = pc.results(today - timedelta(days=60), today - timedelta(days=1))
        ours_f, ours_r = P.fixture_rows(cfg, fx), P.result_rows(cfg, rs)
        rep.add(f"✅ **Play-Cricket** connected: {len(ours_f)} fixtures in the next 30 days, "
                f"{len(ours_r)} results in the last 60 days.")
        pc_ok = True
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
        rep.add(insights_check(meta, today_for(cfg, getattr(args, "today", None)), cfg))
    except MetaError as e:
        ok = False
        rep.add(f"❌ **Facebook / Instagram**: {e}")

    # Player photos (optional, private store)
    from .milestones import PhotoStore
    store_dir = root / "player-photos"
    if store_dir.is_dir():
        ph = PhotoStore(store_dir)
        groups = {"adults": 0, "juniors": 0}
        for _, g in ph.index.values():
            groups[g] += 1
        rule = ("juniors' photos are used without names" if cfg["milestones"]["junior_photos"] == "photo_no_name"
                else "juniors are named but their photos aren't used")
        rep.add(f"✅ **Player photos** connected: {groups['adults']} adults, {groups['juniors']} juniors ({rule}).")
        if cfg["match_photos"]["enabled"]:
            from .matchphotos import MatchPhotos
            mp = MatchPhotos(store_dir)
            if len(mp):
                folders = ", ".join(f"{k} ({v})" for k, v in mp.counts().items())
                rep.add(f"✅ **Match photos** for backgrounds: {len(mp)} — {folders}.")
            else:
                rep.add("ℹ️ **Match photos**: none yet. Posts use the plain club colours until some are added to "
                        "the match-photos folders in the photo store.")
    elif os.environ.get("PHOTOS_KEY"):
        ok = False
        rep.add("❌ **Player photos**: the photo key is saved but the photo store couldn't be read. The key may have "
                "expired or lost access: make a new one and update the PLAYER_PHOTOS_TOKEN secret.")
    elif cfg["milestones"]["enabled"]:
        rep.add("ℹ️ **Player photos**: not connected (optional). Milestone posts use the club badge design instead.")

    # Career milestones
    if cfg["career_milestones"]["enabled"]:
        from . import careers as K
        car = K.Careers(cfg, root)
        linked = len([1 for v in car.links.values() if v])
        todo = [r for r in K.load_links_rows(root) if not r["cricketstatz"]]
        line = (f"✅ **Career milestones**: {len(car.baseline)} CricketStatz starting totals, {linked} Play-Cricket "
                f"players linked.")
        if todo:
            line += (f" {len(todo)} still to check in careers/links.csv ({', '.join(r['name'] for r in todo[:9])}); "
                     f"no career posts for them until they're filled in.")
        rep.add(line)

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
            if cfg.stories_for(p["kind"]):
                files += r.render(cfg, p["data"], root / "posts/samples", p["key"], story=True)
            pending.append({**{k: v for k, v in p.items() if k != "data"},
                            "files": [str(f.relative_to(root)) for f in files]})
        if cfg["leaderboards"]["enabled"] and pc_ok:
            # Real leaderboards from the latest outdoor season, as a preview (can't be posted from here)
            from .leaderboards import leaderboards_post
            lb = cfg["leaderboards"]
            y = today.year if today.month > int(lb["season_end_month"]) else today.year - 1
            as_of = date(y + (int(lb["season_end_month"]) == 12), int(lb["season_end_month"]) % 12 + 1, 1)
            try:
                lp = leaderboards_post(cfg, pc, as_of, root)
            except PlayCricketError as e:
                lp = None
                rep.add(f"ℹ️ **Leaderboards** preview skipped: {e}")
            if lp:
                files = r.render(cfg, lp["data"], root / "posts/samples", "sample-leaderboards")
                pending.append({**{k: v for k, v in lp.items() if k != "data"}, "key": "sample-leaderboards",
                                "title": f"Leaderboards ({y} season, real data)",
                                "files": [str(f.relative_to(root)) for f in files]})
                rep.add(f"✅ **Leaderboards**: previewed from the {y} season ({lp['data']['boards'][0]['matches']} "
                        f"adult matches, {len(lp['data']['boards']) - 1} team boards).")
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
    m.add_argument("--only", choices=["fixtures", "roundup", "matches", "matchday", "leaderboards", "all-due"])
    a = sub.add_parser("announce")
    a.add_argument("--sha", required=True)
    pub = sub.add_parser("publish")
    pub.add_argument("--issue", type=int, required=True)
    nw = sub.add_parser("news")
    nw.add_argument("--issue", type=int, required=True)
    nw.add_argument("--today")
    du = sub.add_parser("due")
    du.add_argument("--today")
    al = sub.add_parser("alert")
    al.add_argument("--key", required=True)
    al.add_argument("--title", required=True)
    al.add_argument("--link")
    al.add_argument("--quiet-first", action="store_true")
    rs = sub.add_parser("resolved")
    rs.add_argument("--key", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--month", help="YYYY-MM (default: last month)")
    rp.add_argument("--today")
    ri = sub.add_parser("report-issue")
    ri.add_argument("--sha", required=True)
    ch = sub.add_parser("check")
    ch.add_argument("--today")
    pv = sub.add_parser("preview")
    pv.add_argument("--sha", required=True)
    args = ap.parse_args(argv)
    try:
        result = {"make": cmd_make, "announce": cmd_announce, "publish": cmd_publish,
                  "check": cmd_check, "preview": cmd_preview,
                  "news": cmd_news, "due": cmd_due,
                  "report": cmd_report, "report-issue": cmd_report_issue,
                  "alert": cmd_alert, "resolved": cmd_resolved}[args.cmd](args)
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
