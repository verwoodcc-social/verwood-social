"""Captain's match reports, from a Microsoft Form via Power Automate.

The flow checks the club code (so the code never reaches GitHub), then opens an issue here titled
"Captain's report: <team> <date>" with the answers as '### Question' sections. Each morning run:
- a report that matches yesterday's (or a recent) result is added to that result post's caption;
- the result post waits until captain_reports → wait_until (local time) for a report, then posts anyway;
- a report that arrives after its result was posted, or matches no game, is closed with a note.
Only issues opened by people with access to this repository (the Power Automate GitHub connection) count.
"""
import re
from datetime import date, datetime, timedelta

from .news import NO_ANSWER, FormError, parse_day, parse_form
from .posts import _norm

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
TITLE = re.compile(r"^\s*captain'?s report", re.I)
Q = {"team": "Team", "date": "Match date", "captain": "Captain", "report": "Report", "potm": "Player of the match"}


def _field(form, key):
    v = (form.get(Q[key]) or "").strip()
    return "" if v.lower() in NO_ANSWER else v


def tidy(text, limit):
    text = re.sub(r"https?://\S+|www\.\S+", "", text or "")  # no links in reports
    text = re.sub(r"[ \t]+", " ", text.replace("\r", ""))
    text = re.sub(r" *\n *", "\n", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > limit:
        cut = text[:limit]
        stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[:stop + 1] if stop > limit * 0.6 else cut.rsplit(" ", 1)[0] + "…"
    return text


def load(cfg, gh, today):
    """Open captain's report issues as dicts (bad ones are returned with an 'error')."""
    out = []
    limit = int(cfg["captain_reports"]["max_length"])
    issues = [i for i in gh._req("GET", "issues", params={"state": "open", "per_page": 100}) if "pull_request" not in i]
    for i in issues:
        labels = {l["name"] for l in i.get("labels", [])}
        if "captain-report" not in labels and not TITLE.match(i.get("title") or ""):
            continue
        if i.get("author_association") not in TRUSTED:
            continue
        form = parse_form(i.get("body") or "")
        r = {"issue": i["number"], "team": _field(form, "team"), "captain": _field(form, "captain"),
             "text": tidy(_field(form, "report"), limit), "potm": _field(form, "potm")[:60],
             "opened": (i.get("created_at") or "")[:10]}
        try:
            r["date"] = parse_day(_field(form, "date"), today - timedelta(days=400))
        except FormError as e:
            r["error"] = str(e)
        if not r.get("error") and not (r["team"] and r["text"] and r.get("date")):
            r["error"] = "The team, match date or report was missing."
        out.append(r)
    return out


def caption_extra(r):
    who = f" – {r['captain']}" if r["captain"] else ""
    lines = ["", f"🗣️ Captain's report{who}:", f"“{r['text']}”"]
    if r["potm"]:
        lines.append(f"⭐ Player of the match: {r['potm']}")
    return "\n".join(lines)


def same_team(a, b):
    return _norm(a) == _norm(b)


def attach(cfg, gh, made, reports, state, now):
    """Add reports to result posts; hold back results still waiting; close late or unmatched reports.
    Returns (made, notes)."""
    cr = cfg["captain_reports"]
    notes, used = [], set()
    h, m = (int(x) for x in str(cr["wait_until"]).split(":"))
    waiting_ok = now.time() < now.replace(hour=h, minute=m).time()
    kept = []
    for p in made:
        if p.get("kind") != "match":
            kept.append(p)
            continue
        card = p["data"]
        rep = next((r for r in reports if not r.get("error") and r["issue"] not in used
                    and r["date"] == card.get("date_obj") and same_team(r["team"], card["team"])), None)
        if rep:
            used.add(rep["issue"])
            cut = p["caption"].find("\n\n#") if "\n\n#" in p["caption"] else len(p["caption"])
            tags_at = p["caption"].rfind("\n\nSupported by") if "\n\nSupported by" in p["caption"] else cut
            at = min(cut, tags_at)
            p["caption"] = p["caption"][:at] + "\n" + caption_extra(rep) + p["caption"][at:]
            p["report_issue"] = rep["issue"]
            kept.append(p)
        elif cr.get("wait") and waiting_ok and re.search(cr["teams"], card["team"] or "", re.I) \
                and card.get("date_obj") == now.date() - timedelta(days=1):
            notes.append(f"Waiting until {cr['wait_until']} for a captain's report: {p['title']}")
        else:
            kept.append(p)
    # Reports that can't be used
    posted = state.get("posted", {})
    for r in reports:
        if r["issue"] in used:
            continue
        if r.get("error"):
            gh.comment(r["issue"], f"⚠️ This report couldn't be used: {r['error']} Please send it again with the form.")
            gh.close(r["issue"])
            continue
        stale = r["date"] < now.date() - timedelta(days=3)
        if stale:
            gh.comment(r["issue"], "This report didn't match a result in time (check the team and date), or its "
                                   "result had already been posted, so it wasn't added. Closing.")
            gh.close(r["issue"])
    return kept, notes


def close_used(gh, number, post_issue, url=""):
    gh.comment(number, f"✅ Added to the result post: #{post_issue}")
    gh.close(number)
