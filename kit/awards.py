"""Player of the Week and Player of the Month (club.yml → awards), across every team, juniors included.

Points from the scorecards of the week (Monday to Sunday) or the calendar month:
    1 a run, +15 for a fifty, +30 for a hundred (each innings)
    20 a wicket (5 in pairs-style junior cricket, where every dismissal counts), +20 for five in an innings
    10 a catch or stumping, +5 a win
The highest total wins, if it reaches min_points. Ties: fewer balls faced, then fewer runs conceded.
One weekly win per player per calendar month (a week counts in its Sunday's month); the monthly award can go
to anyone, including a weekly winner.
Names follow the usual rules (juniors: first name and initial); a junior's photo is never used.
"""
import calendar
import re
from datetime import date, timedelta

from . import posts as P
from .careers import CAUGHT, CAUGHT_BOWLED, _norm
from .playcricket import PlayCricketError

STUMPED = {"st", "stumped"}


def _pid(pid, name):
    return f"id:{pid}" if pid and str(pid) not in ("0", "None", "") else f"n:{_norm(name)}"


def match_points(cfg, detail, card):
    """{player key: entry} for one match card."""
    aw = cfg["awards"]
    low = re.search(aw.get("low_wicket_teams") or "$^", card["team"], re.I)
    per_wicket = int(aw["points"]["wicket_low" if low else "wicket"])
    pts = aw["points"]
    out = {}
    rule = cfg["juniors"]["names"]

    def who(pid, full, shown=None):
        full = str(full or "").strip()
        if _norm(full) in P.NO_NAME:
            return None
        k = _pid(pid, full)
        return out.setdefault(k, {"full_name": full, "name": shown or P.person_name(full, card["names_shortened"], rule),
                                  "team": card["team"], "junior": card["junior"], "points": 0, "balls": 0,
                                  "conceded": 0, "bits": [], "wins": 0})

    vs = f"v {card['opponent']}"
    for b in card["all_batting"]:
        e = who(b["player_id"], b["full_name"], b["name"])
        if not e or b["runs"] <= 0:
            continue
        e["points"] += b["runs"] + (pts["hundred"] if b["runs"] >= 100 else pts["fifty"] if b["runs"] >= 50 else 0)
        e["balls"] += b["balls"] if b["balls"] != 999 else 0
        e["bits"].append((b["runs"], f"{b['figures']} {vs}"))
    for b in card["all_bowling"]:
        e = who(b["player_id"], b["full_name"], b["name"])
        if not e or b["w"] <= 0:
            continue
        e["points"] += b["w"] * per_wicket + (pts["five_for"] if b["w"] >= 5 else 0)
        e["conceded"] += b["r"]
        e["bits"].append((b["w"] * per_wicket, f"{b['figures']} {vs}"))
    side = P.Side(cfg).of(detail)
    them = str(detail.get(f"{P._other(side)}_team_id"))
    catches = {}
    for b in (P._innings_by_team(detail).get(them) or {}).get("bat") or []:
        how = str(b.get("how_out") or "").strip().lower()
        if how in CAUGHT_BOWLED:
            pid, name = b.get("bowler_id"), b.get("bowler_name")
        elif how in CAUGHT or how in STUMPED:
            pid, name = b.get("fielder_id"), b.get("fielder_name")
        else:
            continue
        e = who(pid, name)
        if e:
            catches[id(e)] = catches.get(id(e), 0) + 1
            e["points"] += pts["catch"]
    for e in out.values():
        n = catches.get(id(e), 0)
        if n:
            e["bits"].append((n * pts["catch"], f"{n} catch{'es' if n != 1 else ''} {vs}"))
        if card["outcome"] == "W" and (e["bits"] or n):
            e["points"] += pts["win"]
            e["wins"] += 1
    return out


def scores(cfg, pc, start, end):
    """{player key: entry} over every scorecard from start to end (dates, inclusive)."""
    exclude = cfg["awards"].get("exclude_teams") or ""
    total = {}
    for m in pc.results(start, end):
        try:
            detail = pc.match_detail(m["id"])
        except PlayCricketError:
            continue
        side = P.Side(cfg)
        if side.of({k: v for k, v in detail.items() if k.startswith("home_")}) and \
                side.of({k: v for k, v in detail.items() if k.startswith("away_")}):
            continue  # a club game (e.g. President's XI v the club): both teams are ours
        card = P.match_card(cfg, detail)
        if not card or not card["show_names"] or (exclude and re.search(exclude, card["team"], re.I)):
            continue  # no scorecard, or a youth card with initials only: nobody can be named
        for k, e in match_points(cfg, detail, card).items():
            t = total.setdefault(k, {**e, "points": 0, "balls": 0, "conceded": 0, "bits": [], "wins": 0,
                                     "teams": []})
            for f in ("points", "balls", "conceded", "wins"):
                t[f] += e[f]
            t["bits"] += e["bits"]
            if e["team"] not in t["teams"]:
                t["teams"].append(e["team"])
            t["junior"] = t["junior"] or e["junior"]
    return total


def winner(cfg, total, exclude=()):
    """The top scorer, leaving out the players in exclude (keys), or None."""
    best = [{**e, "key": k} for k, e in total.items()
            if k not in exclude and e["points"] >= int(cfg["awards"]["min_points"]) and e["bits"]]
    if not best:
        return None
    return min(best, key=lambda e: (-e["points"], e["balls"], e["conceded"]))


def week_month(start, end):
    """The month a week counts in: the month its Sunday falls in."""
    return f"{end.year}-{end.month:02d}"


def weekly_winner(cfg, total, start, end, past):
    """Player of the Week, with one weekly win per player per month. past: {week start: {player, month}},
    updated with this week's winner."""
    month, wk = week_month(start, end), start.isoformat()
    already = {v["player"] for k, v in past.items() if v.get("month") == month and k != wk}
    w = winner(cfg, total, already)
    if w:
        past[wk] = {"player": w["key"], "month": month, "name": w["name"]}
    return w


def week_window(today):
    """Monday to Sunday of last week."""
    end = today - timedelta(days=today.weekday() + 1)
    return end - timedelta(days=6), end


def month_window(today):
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def due(cfg, today):
    """Which awards are due today: a subset of ['week', 'month']."""
    aw = cfg["awards"]
    if not aw["enabled"]:
        return []
    out = []
    from .config import DAYS
    if aw["weekly"] and DAYS[today.weekday()] == aw["week_day"].lower():
        s, e = week_window(today)
        if s.month in aw["months"] or e.month in aw["months"]:
            out.append("week")
    if aw["monthly"] and today.day == int(aw["month_day"]):
        if month_window(today)[0].month in aw["months"]:
            out.append("month")
    return out


def award_post(cfg, pc, today, which, photos=None, past=None):
    """The Player of the Week ("week") or Month ("month") post, or None. past: earlier weekly winners
    (state → awards → weeks), so nobody wins two weeks in the same month. The month can go to anyone."""
    aw = cfg["awards"]
    start, end = week_window(today) if which == "week" else month_window(today)
    total = scores(cfg, pc, start, end)
    w = weekly_winner(cfg, total, start, end, past if past is not None else {}) if which == "week" else winner(cfg, total)
    if not w:
        return None
    title = aw["week_title"] if which == "week" else aw["month_title"]
    period = (P.date_range([start, end]) if which == "week" else f"{calendar.month_name[start.month]} {start.year}")
    bits = [b for _, b in sorted(w["bits"], key=lambda x: -x[0])][:4]
    photo = ""
    if photos and not w["junior"]:
        found = photos.find(w["full_name"])
        if found and found[1] == "adults":
            photo = str(found[0])  # ECB: a junior's photo is never shown with their name
    team = " & ".join(w["teams"])
    data = {"kind": "award", "label": title, "name": w["name"], "team": team, "period": period, "bits": bits,
            "points": w["points"], "photo_path": photo, "date": period, "bg_team": w["teams"][0]}
    lines = [f"🌟 {title}: {w['name']} ({team})!", "", *[f"🏏 {b}" for b in bits], "",
             f"{w['points']} points for the {'week' if which == 'week' else 'month'} ({period}). Well played!"]
    key = f"award-{which}-{start.isoformat()}"
    return {"key": key, "kind": "award", "title": f"{title}: {w['name']} ({period})", "data": data,
            "caption": "\n".join(lines) + P._tags(cfg),
            "alt": f"{cfg['club']['name']} {title.lower()} for {period}: {w['name']} of the {team}, "
                   f"{'; '.join(bits)}."}
