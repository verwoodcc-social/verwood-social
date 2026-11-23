"""Results of the same day grouped into one carousel post (club.yml → group_results).

When min_matches or more results from the same day are ready at the same time, they go out as one post:
slide 1 is a summary of every result (like the Monday round-up), then each game's result card (or its photo-led
version). Instagram allows 10 slides, so a busy day is split into posts of up to 8 games (a summary slide
holds 6 results, so 7 or 8 games need two). Milestones and
debuts stay as their own posts. Captain's reports go into the caption, cut to their first couple of sentences.
"""
import re
from datetime import date

from . import posts as P

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _short(text, n=2, limit=240):
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    out = " ".join(parts[:n])
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0] + "…"


def _row(card):
    return {"outcome": card["outcome"], "date": P.short_date(card["date_obj"]), "home": card.get("home", True),
            "team": card["team"], "opponent": f"{card['opponent']} {card['opponent_team']}".strip(),
            "us_score": card["us_score"] or "–", "opp_score": card["opp_score"] or "–", "summary": card["summary"]}


def _line(card):
    icon = {"W": "🏆", "L": "🏏", "D": "🤝", "T": "🤝"}.get(card["outcome"], "🏏")
    return f"{icon} {card['team']} v {card['opponent']}: {card['summary']} ({card['us_score']} · {card['opp_score']})"


def group(cfg, made):
    """Replace same-day result posts with grouped posts when there are enough. Returns the new list."""
    g = cfg["group_results"]
    if not g["enabled"]:
        return made
    by_day = {}
    for p in made:
        if p["kind"] == "match" and p["key"].startswith("match-") and p["data"].get("date_obj"):
            by_day.setdefault(p["data"]["date_obj"], []).append(p)
    out = [p for p in made if not (p["kind"] == "match" and p["key"].startswith("match-")
                                   and len(by_day.get(p["data"].get("date_obj"), [])) >= int(g["min_matches"]))]
    for day, ps in sorted(by_day.items()):
        if len(ps) < int(g["min_matches"]):
            continue
        ps.sort(key=lambda p: (p["data"]["team"]))
        chunks = [ps[i:i + 8] for i in range(0, len(ps), 8)]  # up to 2 summary slides + 8 cards = 10
        for n, chunk in enumerate(chunks, 1):
            cards = [p["data"] for p in chunk]
            part = f" ({n} of {len(chunks)})" if len(chunks) > 1 else ""
            title = f"{DAYS[day.weekday()]}'s results"
            wins = sum(1 for c in cards if c["outcome"] == "W")
            lines = [f"🏏 {title} · {P.long_date(day)}{part}", ""] + [_line(c) for c in cards]
            lines += ["", "Swipe for the scorecards 👉"]
            reps = [(p["data"]["team"], p["report"]) for p in chunk if p.get("report")]
            for team, r in reps:
                who = f" ({r['captain']})" if r.get("captain") else ""
                lines += ["", f"🗣️ {team}{who}: “{_short(r['text'])}”"]
                if r.get("potm"):
                    lines.append(f"⭐ Player of the match: {r['potm']}")
            caption = "\n".join(lines) + P._tags(cfg)
            if len(caption) > 2150:  # Instagram's limit is 2,200 characters: drop the reports if needed
                caption = "\n".join(lines[:len(cards) + 4]) + P._tags(cfg)
            data = {"kind": "results_day", "title": title, "date_range": P.long_date(day) + part,
                    "matches": [_row(c) for c in cards], "cards": cards, "date_obj": day}
            out.append({"key": f"results-{day.isoformat()}-" + "-".join(sorted(str(c["id"]) for c in cards)),
                        "kind": "results_day", "title": f"{title}{part}: {len(cards)} games, {wins} won ({P.short_date(day)})",
                        "data": data, "caption": caption,
                        "alt": f"{cfg['club']['name']} {title.lower()}, {P.long_date(day)}: "
                               + "; ".join(f"{c['team']} v {c['opponent']}, {c['summary']}" for c in cards),
                        "also_keys": [p["key"] for p in chunk],
                        "report_issues": [p["report_issue"] for p in chunk if p.get("report_issue")]})
    return out
