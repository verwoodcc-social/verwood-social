"""League tables: on the last day of each month in the outdoor season, one carousel post with the table
for each adult team's league (from Play-Cricket), Verwood's row highlighted.

Leagues are found from this season's fixtures: league competitions (not cups) for adult outdoor teams.
Junior teams, indoor leagues and indoor teams are left out.
"""
import calendar
import html
import logging
import re
from datetime import date

from .playcricket import PlayCricketError
from .posts import Side, _tags

log = logging.getLogger(__name__)
SHOW = ("p", "w", "l", "pts")  # columns shown, if the league has them (matched ignoring case)


def due(cfg, today):
    lt = cfg["league_tables"]
    last = calendar.monthrange(today.year, today.month)[1]
    return lt["enabled"] and today.month in (lt.get("months") or []) and today.day == last


def divisions(cfg, pc, season):
    """{division id: {league, name, team, team_id}} for our adult outdoor league sides."""
    side_of = Side(cfg)
    ex = cfg["league_tables"].get("exclude") or ""
    out = {}
    for m in pc.season_matches(season):
        side = side_of.of(m)
        if not side or str(m.get("competition_type") or "").lower() != "league" or not m.get("competition_id"):
            continue
        team = str(m.get(f"{side}_team_name") or "").strip()
        league = str(m.get("league_name") or "").strip()
        if cfg.is_junior(team) or re.search(ex, f"{team} {league}", re.I):
            continue
        out.setdefault(str(m["competition_id"]), {"league": league, "name": str(m.get("competition_name") or "").strip(),
                                                  "team": team, "team_id": str(m.get(f"{side}_team_id") or "")})
    return out


def tidy_team(name, cfg):
    """'South Wilts CC - 2nd XI' -> 'South Wilts 2nd XI'."""
    n = re.sub(r"\s*-\s*", " ", str(name or "")).strip()
    n = re.sub(r",\s*[A-Za-z]+\b", "", n)        # 'Winton CC, Dorset 1st XI' -> 'Winton CC 1st XI'
    return re.sub(r"\s+(CC|C\.C\.|Cricket Club)\b", "", n).strip() or n


def table_data(cfg, div, t):
    heads = t.get("headings") or {}
    col = {v.strip().lower(): k for k, v in heads.items()}
    shown = [c for c in SHOW if c in col]
    rows = []
    for v in t.get("values") or []:
        ours = str(v.get("team_id")) == div["team_id"]
        rows.append({"pos": str(v.get("position") or ""), "team": tidy_team(v.get(col.get("team", "column_1")), cfg),
                     "ours": ours, "cells": [str(v.get(col[c]) or "0") for c in shown]})
    us = next((r for r in rows if r["ours"]), None)
    played = int(us["cells"][shown.index("p")]) if us and "p" in shown and us["cells"][shown.index("p")].isdigit() else 0
    return {"title": div["team"], "league": f"{div['league']} · {html.unescape(t.get('name') or div['name'])}",
            "columns": [c.upper() if c != "pts" else "Pts" for c in shown], "rows": rows, "us": us, "played": played}


def tables_post(cfg, pc, today):
    """The monthly carousel, or None if no tables (or no games played yet)."""
    try:
        divs = divisions(cfg, pc, today.year)
    except PlayCricketError as e:
        log.warning("League tables: %s", e)
        return None
    boards = []
    for did, div in divs.items():
        try:
            boards.append(table_data(cfg, div, pc.league_table(did)))
        except PlayCricketError as e:
            log.warning("League table %s: %s", did, e)
    order = cfg["league_tables"].get("order") or []
    boards = [b for b in boards if b["us"] and b["played"] > 0]
    boards.sort(key=lambda b: (order.index(b["title"]) if b["title"] in order else 99, b["title"]))
    if not boards:
        return None
    boards = boards[:10]
    month = f"{calendar.month_name[today.month]} {today.year}"
    data = {"kind": "tables", "title": cfg["league_tables"]["title"], "sub": f"End of {calendar.month_name[today.month]}",
            "boards": boards}
    lines = [f"📋 {cfg['league_tables']['title']}: where our teams stand at the end of {calendar.month_name[today.month]}", ""]
    for b in boards:
        n = len(b["rows"])
        pos = b["us"]["pos"]
        lines.append(f"{b['title']}: {pos}{_ord(pos)} of {n} in {b['league'].split(' · ')[-1]}")
    if len(boards) > 1:
        lines += ["", "Swipe for each table 👉"]
    return {"key": f"tables-{today:%Y-%m}", "kind": "tables", "title": f"League tables {month}", "data": data,
            "caption": "\n".join(lines) + _tags(cfg),
            "alt": f"{cfg['club']['name']} league tables at the end of {month}: " +
                   "; ".join(f"{b['title']} {b['us']['pos']}{_ord(b['us']['pos'])} of {len(b['rows'])}" for b in boards)}


def _ord(p):
    try:
        n = int(p)
    except ValueError:
        return ""
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
