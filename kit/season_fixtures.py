"""Season fixture lists: in the first week of April, one post per team (senior and youth) with all of
its outdoor summer fixtures. The teams are spread across the week (a few posts each morning) rather
than all at once. The plan is made on the first day and kept in state, so a team never posts twice.
"""
import re
from datetime import date, timedelta

from . import posts as P

ROWS_PER_PAGE = 13
JUNIOR_ORDER = re.compile(r"(\d+)")


def due(cfg, today):
    sf = cfg["season_fixtures"]
    start = date(today.year, int(sf["month"]), int(sf["first_day"]))
    return sf["enabled"] and start <= today < start + timedelta(days=int(sf["days"]))


def _sort_key(cfg, team):
    order = cfg["league_tables"].get("order") or []
    if team in order:
        return (0, order.index(team), team)
    if cfg.is_junior(team):
        m = JUNIOR_ORDER.search(team)
        return (2, -int(m.group(1)) if m else 0, team)  # oldest juniors first
    return (1, 0, team)


def team_fixtures(cfg, pc, year):
    """{team: [fixture rows]} for this summer's outdoor fixtures."""
    sf = cfg["season_fixtures"]
    start, end = date(year, int(sf["season_start_month"]), 1), date(year, int(sf["season_end_month"]) + 1, 1) - timedelta(days=1)
    ex = sf.get("exclude") or ""
    by = {}
    matches = {str(m["id"]): m for m in pc.fixtures(start, end)}
    for r in P.fixture_rows(cfg, matches.values()):
        league = str(matches[r["id"]].get("league_name") or "")
        if ex and re.search(ex, f"{r['team']} {league}", re.I):
            continue
        by.setdefault(r["team"], []).append(r)
    for rows in by.values():
        rows.sort(key=lambda r: (r["date_obj"], r["time"]))
    return by


def plan(cfg, teams, today, state):
    """Which day of the week each team posts on, kept in state so it never changes part-way."""
    sf = cfg["season_fixtures"]
    key = str(today.year)
    p = state.setdefault("season_fixtures_plan", {}).setdefault(key, {})
    days = int(sf["days"])
    start = date(today.year, int(sf["month"]), int(sf["first_day"]))
    left = days - (today - start).days
    new = [t for t in sorted(teams, key=lambda t: _sort_key(cfg, t)) if t not in p]
    if new:
        # spread unplanned teams over the days that are left, earliest days first
        left = max(left, 1)
        for i, t in enumerate(new):  # spread evenly: e.g. 11 teams over 7 days -> 2,2,1,2,1,2,1
            p[t] = (start + timedelta(days=(today - start).days + i * left // len(new))).isoformat()
    return [t for t, d in p.items() if d == today.isoformat() and t in teams]


def season_fixture_posts(cfg, pc, today, state):
    by = team_fixtures(cfg, pc, today.year)
    if not by:
        return []
    out = []
    for team in sorted(plan(cfg, list(by), today, state), key=lambda t: _sort_key(cfg, t)):
        rows = by[team]
        home = sum(1 for r in rows if r["home"])
        first = rows[0]
        data = {"kind": "season_fixtures", "title": team, "sub": f"{today.year} fixtures · {len(rows)} games",
                "matches": rows}
        caption = (f"📅 {team}: our {today.year} fixtures\n\n{len(rows)} games, {home} at home. First up: "
                   f"{first['date']} v {first['opponent']} ({'home' if first['home'] else 'away'}).\n\n"
                   f"Come and support! Full details on our Play-Cricket site.") + P._tags(cfg)
        slug = re.sub(r"[^a-z0-9]+", "-", team.lower()).strip("-")
        out.append({"key": f"season-fixtures-{today.year}-{slug}", "kind": "season_fixtures",
                    "title": f"{team} {today.year} fixtures", "data": data, "caption": caption,
                    "alt": f"{cfg['club']['name']} {team} fixtures for {today.year}: " +
                           "; ".join(f"{r['date']} v {r['opponent']} ({'H' if r['home'] else 'A'})" for r in rows)})
    return out
