"""End-of-season review: one carousel in early October for the outdoor season just finished.

Slides:
  1. The club's season: each adult team's record and league finishing position.
  2. One per adult team: won/lost record, league position, top 3 run scorers, wicket takers and catchers.
  3. Career milestones reached this season (if any).
  4. All-time career leaders: runs, wickets and appearances (CricketStatz totals + Play-Cricket).
Junior and indoor teams are left out. Season leaders use shortened names; career slides use full names.
"""
import logging
import re
from datetime import date

from . import leaderboards as LB
from . import posts as P
from .playcricket import PlayCricketError

log = logging.getLogger(__name__)


def due(cfg, today):
    sr = cfg["season_review"]
    from .config import DAYS
    return (sr["enabled"] and today.month == int(sr["month"]) and today.day <= 7
            and DAYS[today.weekday()] == str(sr["day"]).lower())


def team_records(cfg, results):
    rec = {}
    for r in P.result_rows(cfg, results):
        if not LB.included(cfg, r["team"]):
            continue
        t = rec.setdefault(r["team"], {"P": 0, "W": 0, "L": 0, "D": 0, "A": 0})
        o = r["outcome"]
        if o in ("P",):
            continue
        t["P"] += 1
        if o == "W":
            t["W"] += 1
        elif o == "L":
            t["L"] += 1
        elif o in ("D", "T", "N"):
            t["D"] += 1
        else:
            t["A"] += 1  # abandoned / cancelled
    return rec


def positions(cfg, pc, season):
    from .tables import divisions, table_data
    out = {}
    try:
        divs = divisions(cfg, pc, season)
    except PlayCricketError as e:
        log.warning("Season review tables: %s", e)
        return out
    for did, div in divs.items():
        try:
            b = table_data(cfg, div, pc.league_table(did))
        except PlayCricketError:
            continue
        if b["us"]:
            out[div["team"]] = {"pos": b["us"]["pos"], "of": len(b["rows"]), "league": b["league"].split(" · ")[-1]}
    return out


def _ord(p):
    from .tables import _ord as o
    return o(p)


def career_leaders(cfg, root, top=5):
    """All-time club career leaders (runs, wickets, appearances), full names where known."""
    from . import careers as K
    car = K.Careers(cfg, root)
    people = {}
    seen = set()
    for pkey, rec in car.state["players"].items():
        if not pkey.startswith("club|"):
            continue
        cid = car.link(rec["pid"], rec.get("key", ""))
        if cid is None:
            continue
        totals, _ = car.career("club", rec)
        people[pkey] = {"name": rec.get("name") or rec.get("short"), **totals}
        if cid != "new":
            seen.update(c.strip() for c in cid.split("+"))
    linked = {}
    for pid, cid in car.links.items():
        linked.setdefault(cid, pid)
    for cid, b in car.baseline.items():
        if cid in seen:
            continue
        nm = b["name"].split()
        name = f"{nm[-1]} {' '.join(nm[:-1])}" if len(nm) > 1 and len(nm[-1]) <= 2 else b["name"]
        people[f"cs|{cid}"] = {"name": name, **{s: b[s] for s in K.STATS}}
    def best(stat, unit):
        rows = sorted(people.values(), key=lambda p: (-p[stat], p["name"]))[:top]
        return [{"name": p["name"], "value": f"{p[stat]:,}", "detail": ""} for p in rows if p[stat] > 0]
    return {"title": "All-time leaders", "matches": None, "sub": "Career totals for Verwood",
            "sections": [["bat", "Career runs"], ["bowl", "Career wickets"], ["field", "Appearances"]],
            "bat": best("runs", "runs"), "bowl": best("wickets", "wkts"), "field": best("matches", "games")}


def season_post(cfg, pc, today, root):
    sr = cfg["season_review"]
    season = today.year if today.month > 3 else today.year - 1
    start, end = date(season, 4, 1), date(season, 9, 30)
    results = pc.results(start, end)
    records = {t: r for t, r in team_records(cfg, results).items() if r["P"] >= int(sr.get("min_matches", 3))}
    if not records:
        return None
    pos = positions(cfg, pc, season)
    order = cfg["league_tables"].get("order") or []
    teams = sorted(records, key=lambda t: (order.index(t) if t in order else 99, -records[t]["P"], t))

    # leaders per team (cached scorecards, same as the monthly leaderboards)
    import json
    path = root / LB.CACHE
    try:
        cache = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        cache = {}
    matches = LB.collect(cfg, pc, date(season, 10, 1), cache)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    by_team = {}
    for m in matches:
        by_team.setdefault(m["team"], []).append(m)

    extra = []  # career slides, kept even when there are many teams
    if cfg["career_milestones"]["enabled"]:
        from . import careers as K
        log_rows = [e for e in K.Careers(cfg, root).state.get("milestone_log", []) if e.get("season") == season]
        if log_rows:
            extra.append({"type": "milestones", "title": "Career milestones", "sub": f"Reached in {season}",
                          "rows": log_rows[:9]})
        cl = career_leaders(cfg, root)
        if cl["bat"]:
            extra.append({"type": "leaders", **cl, "sub": f"Career totals for {cfg.short_name}, end of {season}"})
    slides = []
    summary = []
    for t in teams:
        r, p = records[t], pos.get(t)
        summary.append({"team": t, **r, "pos": f"{p['pos']}{_ord(p['pos'])} of {p['of']}" if p else ""})
    total = {k: sum(r[k] for r in records.values()) for k in ("P", "W", "L", "D", "A")}
    slides.append({"type": "summary", "title": f"{season} season", "sub": "Season review · all adult teams",
                   "rows": summary, "total": total})
    for t in teams[:10 - 1 - len(extra)]:
        b = LB.board(cfg, by_team.get(t, []), t, top=int(sr["top"]))
        p = pos.get(t)
        slides.append({"type": "team", "title": t, "sub": f"Season review · {season}",
                       "record": records[t], "pos": f"{p['pos']}{_ord(p['pos'])} of {p['of']}" if p else "",
                       "league": p["league"] if p else "", "bat": b["bat"], "bowl": b["bowl"], "field": b["field"]})
    slides = (slides + extra)[:10]
    data = {"kind": "season", "title": sr["title"], "season": season, "slides": slides}
    lines = [f"🏏 {sr['title']}: our {season} season", ""]
    for s in summary:
        lines.append(f"{s['team']}: played {s['P']}, won {s['W']}" + (f", finished {s['pos']}" if s["pos"] else ""))
    lines += ["", "Thank you to every player, umpire, scorer, tea-maker and supporter. Swipe for each team's season 👉"]
    return {"key": f"season-review-{season}", "kind": "season", "title": f"{sr['title']} {season}", "data": data,
            "caption": "\n".join(lines) + P._tags(cfg),
            "alt": f"{cfg['club']['name']} {season} season review: " +
                   "; ".join(f"{s['team']} won {s['W']} of {s['P']}" for s in summary)}
