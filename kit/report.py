"""Monthly sponsor report: how many people saw the club's posts, and how many carried the sponsor's logo.

On the 1st of each month: figures for the previous month from Meta (Facebook Page + Instagram), plus
the kit's own record of what it posted. Rendered as a one-page A4 PDF (and a preview image), and
opened as a GitHub issue for the club to forward to the sponsor. Nothing is posted publicly.
"""
import calendar
import json
import re
from datetime import date, datetime, timedelta

from .review import MARK

KIND_NAMES = {"match": "Match results", "roundup": "Weekly results summaries", "fixtures": "Fixture lists",
              "milestone": "Milestones", "matchday": "Matchday Stories", "news": "Club news and events"}


def month_bounds(month, tz):
    """(first day 00:00, first day of next month 00:00) in the club's time zone."""
    y, m = month
    start = datetime(y, m, 1, tzinfo=tz)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=tz)
    return start, end


def previous_month(today):
    first = today.replace(day=1)
    last = first - timedelta(days=1)
    return last.year, last.month


def month_label(month):
    return f"{calendar.month_name[month[1]]} {month[0]}"


def kit_posts(issues, start, end):
    """What the kit posted in the month, from its closed 'published' issues."""
    by_kind, feed, stories = {}, 0, 0
    for i in issues:
        closed = i.get("closed_at") or ""
        if not closed:
            continue
        when = datetime.fromisoformat(closed.replace("Z", "+00:00"))
        if not (start <= when < end):
            continue
        m = MARK.search(i.get("body") or "")
        if not m:
            continue
        info = json.loads(m.group(1))
        if info.get("sample"):
            continue
        kind = info.get("kind", "other")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        nets = len(info.get("networks") or [])
        feed += nets if info.get("images") else 0
        stories += nets * len(info.get("stories") or [])
    rows = [(KIND_NAMES.get(k, k.capitalize()), n) for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1])]
    return {"rows": rows, "items": sum(by_kind.values()), "feed": feed, "stories": stories}


def first_line(text, limit=90):
    line = next((l.strip() for l in (text or "").splitlines() if l.strip()), "")
    line = re.sub(r"#\w+", "", line).strip()
    return line if len(line) <= limit else line[:limit].rsplit(" ", 1)[0] + "…"


def engagement(p):
    return int(p.get("likes") or 0) + int(p.get("comments") or 0) + int(p.get("shares") or 0)


def gather(cfg, ins, issues, month, previous_followers=None):
    """Everything the report shows. `ins` is a meta.Insights; `issues` the kit's published issues."""
    start, end = month_bounds(month, cfg.tz)
    fb = ins.page_totals(start, end)
    ig = ins.ig_totals(start, end)
    fb_posts = ins.page_posts(start, end)
    ig_posts = ins.ig_posts(start, end)
    followers = ins.followers()
    fb_eng = sum(engagement(p) for p in fb_posts)
    ig_eng = ig.get("interactions")
    if ig_eng is None and ig_posts:
        ig_eng = sum(engagement(p) for p in ig_posts)

    def change(net):
        now, before = followers.get(net), (previous_followers or {}).get(net)
        return None if now is None or before is None else now - before

    networks = [
        {"name": "Facebook", "views": fb.get("views"), "reach": fb.get("reach"), "engagement": fb_eng,
         "followers": followers.get("facebook"), "change": change("facebook"), "posts": len(fb_posts)},
        {"name": "Instagram", "views": ig.get("views"), "reach": ig.get("reach"), "engagement": ig_eng,
         "followers": followers.get("instagram"), "change": change("instagram"), "posts": len(ig_posts)},
    ]

    def total(key):
        vals = [n[key] for n in networks if n[key] is not None]
        return sum(vals) if vals else None

    top = sorted([p for p in fb_posts + ig_posts if p.get("views") is not None or engagement(p)],
                 key=lambda p: (p.get("views") or 0, engagement(p)), reverse=True)[:3]
    for p in top:
        p["title"] = first_line(p["text"]) or "Post"
        p["engagement"] = engagement(p)
        try:
            p["date"] = datetime.fromisoformat(p["when"].replace("+0000", "+00:00")).strftime("%-d %b")
        except ValueError:
            p["date"] = ""
    b = cfg["branding"]
    return {"month": month_label(month), "month_key": f"{month[0]}-{month[1]:02d}",
            "range": f"1–{(end - timedelta(days=1)).day} {calendar.month_name[month[1]]} {month[0]}",
            "sponsor": (b.get("sponsor_text") or "our sponsor").strip(),
            "totals": {"views": total("views"), "reach": total("reach"), "engagement": total("engagement")},
            "networks": networks, "kit": kit_posts(issues, start, end), "top": top,
            "followers": followers, "first_report": not previous_followers,
            "problems": list(dict.fromkeys(ins.problems))}


def fmt(n):
    return "–" if n is None else f"{n:,}"


def caption(r):
    """Plain-text summary for the issue (and to paste into an email)."""
    t, k = r["totals"], r["kit"]
    lines = [f"Verwood Cricket Club social media, {r['month']}", ""]
    if t["views"] is not None:
        lines.append(f"- {fmt(t['views'])} views of our posts across Facebook and Instagram")
    if t["reach"] is not None:
        lines.append(f"- {fmt(t['reach'])} accounts reached")
    if t["engagement"] is not None:
        lines.append(f"- {fmt(t['engagement'])} likes, comments and shares")
    lines.append(f"- {k['feed']} posts and {k['stories']} Stories carried the {r['sponsor']} logo")
    for n in r["networks"]:
        if n["followers"] is not None:
            ch = "" if n["change"] is None else f" ({'+' if n['change'] >= 0 else ''}{n['change']} this month)"
            lines.append(f"- {n['name']} followers: {fmt(n['followers'])}{ch}")
    return "\n".join(lines)
