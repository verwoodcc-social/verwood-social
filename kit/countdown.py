"""Countdown to the new season (club.yml → countdown): a post on set days before the first outdoor senior game.

The first game is read from Play-Cricket's fixtures, so nothing needs setting each year. Until the fixtures are
on Play-Cricket there's nothing to count down to, and no post is made.
"""
import re
from datetime import timedelta

from . import posts as P


def first_day(cfg, pc, today):
    """(date, rows) for the first day with outdoor senior games, from today on, or (None, [])."""
    cd = cfg["countdown"]
    exclude = cd.get("exclude_teams") or ""
    rows = [r for r in P.fixture_rows(cfg, pc.fixtures(today, today + timedelta(days=int(cd["look_ahead_days"]))))
            if not cfg.is_junior(r["team"]) and not (exclude and re.search(exclude, r["team"], re.I))]
    if not rows:
        return None, []
    d = min(r["date_obj"] for r in rows)
    return d, sorted((r for r in rows if r["date_obj"] == d), key=lambda r: (r["time"], r["team"]))


def due(cfg, today):
    cd = cfg["countdown"]
    return bool(cd["enabled"]) and today.month in cd["months"]


def countdown_post(cfg, pc, today):
    cd = cfg["countdown"]
    d, rows = first_day(cfg, pc, today)
    if not d:
        return None
    left = (d - today).days
    if left not in cd["days"]:
        return None
    shown = rows[:4]
    words = "DAY TO GO" if left == 1 else "DAYS TO GO"
    data = {"kind": "countdown", "kicker": cd["title"].replace("{year}", str(d.year)), "days": left, "words": words,
            "first": P.long_date(d), "date_obj": d, "matches": shown, "more": len(rows) - len(shown),
            "cta": cd.get("cta", "")}
    lines = [f"⏳ {left} {words.lower()} until the {d.year} season!", "",
             f"Our first game{'s are' if len(rows) > 1 else ' is'} on {P.long_date(d)}:"]
    lines += [f"🏏 {r['team']} v {r['opponent']} ({'H' if r['home'] else 'A'}){' · ' + r['time'] if r['time'] != 'TBC' else ''}"
              for r in shown]
    if len(rows) > len(shown):
        lines.append(f"…and {len(rows) - len(shown)} more")
    if cd.get("cta"):
        lines += ["", cd["cta"]]
    return {"key": f"countdown-{d.isoformat()}-{left}", "kind": "countdown",
            "title": f"Countdown: {left} {words.lower()} ({P.short_date(d)})", "data": data,
            "caption": "\n".join(lines) + P._tags(cfg),
            "alt": f"{cfg['club']['name']}: {left} {words.lower()} until the first game of the {d.year} season, "
                   f"{P.long_date(d)}."}
