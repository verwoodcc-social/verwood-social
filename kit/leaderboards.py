"""Season leaderboards: top run scorers, wicket takers and fielders, season to date.

One carousel post, first Monday of each month in the outdoor season: a club-wide board for all adult
teams, then one board per adult team. Junior and indoor teams are left out (club.yml → leaderboards).
Names follow the same rule as every other post (first name and initial).

Scorecards are summarised once per match and kept in state/leaderboard-cache.json, so each run only
asks Play-Cricket about new matches.
"""
import json
import logging
import re
from datetime import date, timedelta

from .playcricket import PlayCricketError, parse_date
from .posts import NO_NAME, NOT_OUT, Side, _innings_by_team, _int, _norm, _other, _tags, person_name

log = logging.getLogger(__name__)
CACHE = "state/leaderboard-cache.json"
CAUGHT = {"ct", "c", "caught"}
CAUGHT_BOWLED = {"ct & b", "c & b", "c&b", "ct&b", "caught and bowled", "ct and b"}
STUMPED = {"st", "stumped"}


def _key(pid, name):
    return f"id:{pid}" if pid and str(pid) not in ("0", "None") else f"n:{_norm(name)}"


def summarise(cfg, detail):
    """Per-player figures for our side in one match, or None if it has no usable scorecard."""
    side = Side(cfg).of(detail)
    if not side:
        return None
    us, them = str(detail.get(f"{side}_team_id")), str(detail.get(f"{_other(side)}_team_id"))
    by = _innings_by_team(detail)
    bat, bowl, field = [], [], {}
    for b in (by.get(us) or {}).get("bat") or []:
        how = str(b.get("how_out") or "").strip().lower()
        name = str(b.get("batsman_name") or "").strip()
        runs = _int(b.get("runs"), None)
        if how == "did not bat" or _norm(name) in NO_NAME or runs is None:
            continue
        bat.append({"k": _key(b.get("batsman_id"), name), "name": person_name(name, True, "initial"), "runs": runs,
                    "out": how not in NOT_OUT})
    for b in (by.get(them) or {}).get("bowl") or []:
        name = str(b.get("bowler_name") or "").strip()
        if _norm(name) in NO_NAME:
            continue
        bowl.append({"k": _key(b.get("bowler_id"), name), "name": person_name(name, True, "initial"), "w": _int(b.get("wickets")),
                     "r": _int(b.get("runs")), "overs": str(b.get("overs") or "")})
    for b in (by.get(them) or {}).get("bat") or []:  # their batting = our fielding
        how = str(b.get("how_out") or "").strip().lower()
        if how in CAUGHT_BOWLED:
            who, pid, kind = b.get("bowler_name"), b.get("bowler_id"), "ct"
        elif how in CAUGHT:
            who, pid, kind = b.get("fielder_name"), b.get("fielder_id"), "ct"
        elif how in STUMPED:
            who, pid, kind = b.get("fielder_name"), b.get("fielder_id"), "st"
        else:
            continue
        who = str(who or "").strip()
        if not who or _norm(who) in NO_NAME:
            continue
        f = field.setdefault(_key(pid, who), {"k": _key(pid, who), "name": person_name(who, True, "initial"), "ct": 0, "st": 0})
        f[kind] += 1
    if not bat and not bowl:
        return None
    return {"team": str(detail.get(f"{side}_team_name") or "").strip(), "date": detail.get("match_date"),
            "bat": bat, "bowl": bowl, "field": list(field.values())}


def season_range(cfg, today):
    lb = cfg["leaderboards"]
    y = today.year
    start = date(y, int(lb["season_start_month"]), 1)
    end_m = int(lb["season_end_month"])
    end = date(y + (end_m == 12), end_m % 12 + 1, 1) - timedelta(days=1)
    return start, min(end, today - timedelta(days=1))


def included(cfg, team):
    lb = cfg["leaderboards"]
    if cfg.is_junior(team):
        return False
    ex = lb.get("exclude_teams") or ""
    return not (ex and re.search(ex, team or "", re.I))


def collect(cfg, pc, today, cache):
    """Match summaries for this season's adult games (using and updating the cache)."""
    start, end = season_range(cfg, today)
    if end < start:
        return []
    out = []
    for m in pc.results(start, end):
        mid = str(m["id"])
        side = Side(cfg).of(m)
        if not side or not included(cfg, str(m.get(f"{side}_team_name") or "")):
            continue
        if str(m.get("result") or "").upper() in ("", "A", "C", "M"):
            continue  # abandoned, cancelled or no result yet: nothing to count
        if mid not in cache:
            try:
                s = summarise(cfg, pc.match_detail(mid))
            except PlayCricketError as e:
                log.warning("Skipping match %s: %s", mid, e)
                continue
            if s is None:
                continue  # no scorecard yet: try again next time
            cache[mid] = s
        out.append(cache[mid])
    return out


def board(cfg, matches, title, top=5):
    """Top run scorers, wicket takers and fielders across some matches."""
    rule = cfg["juniors"]["names"]
    runs, wkts, catches = {}, {}, {}
    for m in matches:
        for b in m["bat"]:
            p = runs.setdefault(b["k"], {"name": b["name"], "runs": 0, "inns": 0, "outs": 0, "hs": -1, "hs_no": False})
            p["runs"] += b["runs"]
            p["inns"] += 1
            p["outs"] += b["out"]
            if b["runs"] > p["hs"] or (b["runs"] == p["hs"] and not b["out"]):
                p["hs"], p["hs_no"] = b["runs"], not b["out"]
        for b in m["bowl"]:
            p = wkts.setdefault(b["k"], {"name": b["name"], "w": 0, "r": 0, "best": (-1, 0)})
            p["w"] += b["w"]
            p["r"] += b["r"]
            if (b["w"], -b["r"]) > (p["best"][0], -p["best"][1]):
                p["best"] = (b["w"], b["r"])
        for f in m["field"]:
            p = catches.setdefault(f["k"], {"name": f["name"], "ct": 0, "st": 0})
            p["ct"] += f["ct"]
            p["st"] += f["st"]
    short = (lambda n: n) if rule == "initial" else (lambda n: person_name(n, True, rule))
    bat = [{"name": short(p["name"]), "value": p["runs"],
            "detail": f"{p['inns']} inns · HS {p['hs']}{'*' if p['hs_no'] else ''}"}
           for p in sorted(runs.values(), key=lambda p: (-p["runs"], p["inns"], p["name"])) if p["runs"] > 0][:top]
    bowl = [{"name": short(p["name"]), "value": p["w"], "detail": f"Best {p['best'][0]}-{p['best'][1]}"}
            for p in sorted(wkts.values(), key=lambda p: (-p["w"], p["r"], p["name"])) if p["w"] > 0][:top]
    fld = [{"name": short(p["name"]), "value": p["ct"] + p["st"],
            "detail": " · ".join(x for x in (f"{p['ct']} ct" if p["ct"] else "", f"{p['st']} st" if p["st"] else "") if x)}
           for p in sorted(catches.values(), key=lambda p: (-(p["ct"] + p["st"]), -p["ct"], p["name"]))
           if p["ct"] + p["st"] > 0][:top]
    return {"title": title, "matches": len(matches), "bat": bat, "bowl": bowl, "field": fld}


def leaderboards_post(cfg, pc, today, root):
    """The monthly carousel post, or None if there's nothing to show yet."""
    lb = cfg["leaderboards"]
    if cfg["juniors"]["names"] == "none":
        return None  # leaderboards need names
    path = root / CACHE
    try:
        cache = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        cache = {}
    matches = collect(cfg, pc, today, cache)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    if not matches:
        return None
    season = season_range(cfg, today)[0].year
    boards = [board(cfg, matches, "All adult teams", int(lb["top"]))]
    teams = {}
    for m in matches:
        teams.setdefault(m["team"], []).append(m)
    order = sorted(teams, key=lambda t: (-len(teams[t]), t))
    for t in order:
        if len(teams[t]) >= int(lb["min_matches"]):
            b = board(cfg, teams[t], t, int(lb["top"]))
            if b["bat"] or b["bowl"]:
                boards.append(b)
    boards = boards[:10]  # Instagram carousels hold 10
    club = boards[0]
    start, end = season_range(cfg, today)
    y_end = date(start.year + (int(lb["season_end_month"]) == 12), int(lb["season_end_month"]) % 12 + 1, 1)
    sub = f"{season} season" if today >= y_end else f"{season} season so far"
    data = {"kind": "leaderboards", "title": lb["title"], "sub": sub, "boards": boards}
    lines = [f"📊 {lb['title']}: {sub}", ""]
    if club["bat"]:
        lines.append(f"🏏 Most runs: {club['bat'][0]['name']} ({club['bat'][0]['value']})")
    if club["bowl"]:
        lines.append(f"🎯 Most wickets: {club['bowl'][0]['name']} ({club['bowl'][0]['value']})")
    if club["field"]:
        lines.append(f"🧤 Most catches and stumpings: {club['field'][0]['name']} ({club['field'][0]['value']})")
    if len(boards) > 1:
        lines += ["", "Swipe for each team's leaders 👉"]
    return {"key": f"leaderboards-{today:%Y-%m}", "kind": "leaderboards", "title": f"{lb['title']} {today:%B %Y}",
            "data": data, "caption": "\n".join(lines) + _tags(cfg),
            "alt": f"{cfg['club']['name']} {season} season leaderboards: top run scorers, wicket takers and "
                   f"fielders for all adult teams and for " + ", ".join(b["title"] for b in boards[1:]) + "."}


def due(cfg, today):
    lb = cfg["leaderboards"]
    from .config import DAYS
    return (lb["enabled"] and today.month in (lb.get("months") or []) and today.day <= 7
            and DAYS[today.weekday()] == str(lb["day"]).lower())
