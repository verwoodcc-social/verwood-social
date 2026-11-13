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
              "milestone": "Milestones", "matchday": "Matchday Stories", "news": "Club news and events",
              "throwback": "Throwback Thursday", "watch": "Milestone watch", "career": "Career milestones",
              "leaderboards": "Leaderboards", "tables": "League tables", "season": "Season review",
              "season_fixtures": "Season fixture lists", "gameoff": "Game off", "countdown": "Season countdown", "award": "Player of the week / month"}
BY_HAND = "Posted by hand"
OLDER = "Automatic (earlier Metricool version)"


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


def _key_text(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:80]


def kit_captions(issues):
    """{caption fingerprint: kind} for the kit's posts, so a post on Facebook or Instagram can be matched to it."""
    from .review import parse_issue, GitHubError
    out = {}
    for i in issues:
        try:
            info, cap = parse_issue(i.get("body") or "")
        except (GitHubError, ValueError):
            continue
        if not info.get("sample") and _key_text(cap):
            out[_key_text(cap)] = info.get("kind", "other")
    return out


def post_type(p, captions, tags=""):
    k = captions.get(_key_text(p.get("text")))
    if k is None:  # the caption was edited on the issue or on the post: try its first line
        first = _key_text((p.get("text") or "").split("\n", 1)[0])
        k = next((v for c, v in captions.items() if first and len(first) >= 15 and c.startswith(first)), None)
    if k is None:
        # Before 11 November 2026 the automatic posts came from the older Metricool version, which left no
        # record here. They end with the kit's hashtag line, which hand-written posts rarely copy exactly.
        old = tags and tags in (p.get("text") or "") and (p.get("when") or "")[:10] < "2026-11-11"
        return OLDER if old else BY_HAND
    return KIND_NAMES.get(k, k.replace("_", " ").capitalize())


def committee(posts, captions, n=10, tags=""):
    """Every post of the month (kit and by hand), ranked, plus averages by type: for the committee email."""
    rows = []
    for p in posts:
        rows.append({"network": p["network"], "title": first_line(p.get("text"), 70) or "(no caption)",
                     "type": post_type(p, captions, tags), "views": p.get("views"), "engagement": engagement(p),
                     "url": p.get("url", ""), "when": (p.get("when") or "")[:10]})
    rows.sort(key=lambda r: (r["views"] or 0, r["engagement"]), reverse=True)
    groups = {}
    for r in rows:
        groups.setdefault(r["type"], []).append(r)

    def avg(rs, k):
        vals = [r[k] for r in rs if r[k] is not None]
        return round(sum(vals) / len(vals)) if vals else None
    types = sorted(({"type": t, "posts": len(rs), "views": avg(rs, "views"), "engagement": avg(rs, "engagement")}
                    for t, rs in groups.items()), key=lambda x: ((x["views"] or 0), x["engagement"] or 0), reverse=True)
    kit = [r for r in rows if r["type"] != BY_HAND]  # automatic, including the earlier version
    hand = [r for r in rows if r["type"] == BY_HAND]
    return {"top": rows[:n], "types": types, "total": len(rows),
            "kit": {"posts": len(kit), "views": avg(kit, "views"), "engagement": avg(kit, "engagement")},
            "hand": {"posts": len(hand), "views": avg(hand, "views"), "engagement": avg(hand, "engagement")}}


def committee_text(c):
    """Plain text for the committee email (not part of the sponsor report)."""
    if not c or not c["total"]:
        return ""
    lines = [f"How the posts did ({c['total']} posts on Facebook and Instagram, including any posted by hand; "
             f"Stories aren't included):", "", "Top posts (views · likes, comments and shares):"]
    for i, r in enumerate(c["top"], 1):
        lines.append(f"{i}. {r['title']} ({r['network']}, {r['when']}, {r['type']}): "
                     f"{fmt(r['views'])} views · {r['engagement']}" + (f"\n   {r['url']}" if r["url"] else ""))
    lines += ["", "Average per post, by type:"]
    for t in c["types"]:
        lines.append(f"- {t['type']}: {t['posts']} post{'s' if t['posts'] != 1 else ''}, "
                     f"{fmt(t['views'])} views, {fmt(t['engagement'])} likes/comments/shares")
    k, h = c["kit"], c["hand"]
    if h["posts"] and k["posts"]:
        lines += ["", f"Automatic posts averaged {fmt(k['views'])} views and {fmt(k['engagement'])} interactions; posts "
                      f"made by hand averaged {fmt(h['views'])} views and {fmt(h['engagement'])}."]
    return "\n".join(lines)


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

    board = committee(fb_posts + ig_posts, kit_captions(issues), tags=(cfg["club"].get("hashtags") or "").strip())
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
            "networks": networks, "kit": kit_posts(issues, start, end), "top": top, "committee": board,
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
