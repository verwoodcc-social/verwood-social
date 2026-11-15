"""Debuts (club.yml → debuts): a post when a player plays their first adult game for the club.

    Club debut   first ever game for the club, in an adult team
    Adult debut  a youth player who has only played junior cricket for the club, in their first adult game

A youngster's first junior game doesn't get a post. To know who is new, `build` reads every scorecard from
first_season on (Play-Cricket's full data starts in 2016) and keeps, per Play-Cricket player id, the date of
their first junior and first adult game in state/debuts.json (ids and dates only, no names). Players in the
CricketStatz history (careers/baseline.csv, careers/links.csv) count as having played before. Until that
first build has finished, no debut posts are made, so a half-built history can't produce false debuts.
"""
import json
import logging
import re
import time
from pathlib import Path

from . import posts as P
from .careers import _team_players, cs_key, load_baseline, load_links, pc_key
from .playcricket import PlayCricketError, parse_date

log = logging.getLogger(__name__)
FILE = "state/debuts.json"


def load(root):
    try:
        d = json.loads((Path(root) / FILE).read_text())
    except (FileNotFoundError, ValueError):
        d = {}
    d.setdefault("players", {})
    d.setdefault("checked", [])
    d.setdefault("built", False)
    return d


def save(root, d):
    p = Path(root) / FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    d["checked"] = sorted(set(d["checked"]))
    p.write_text(json.dumps(d, indent=0, sort_keys=True) + "\n")


def _adult(cfg, team):
    ex = cfg["debuts"].get("exclude_teams") or ""
    return not cfg.is_junior(team) and not (ex and re.search(ex, team or "", re.I))


def players_in(cfg, detail):
    """[(player id, full name)] for our side of a scorecard: the team list, batters and bowlers."""
    side = P.Side(cfg).of(detail)
    if not side:
        return []
    us, them = str(detail.get(f"{side}_team_id")), str(detail.get(f"{P._other(side)}_team_id"))
    by = P._innings_by_team(detail)
    seen = {}
    for p in _team_players(detail, side):
        seen.setdefault(str(p.get("player_id") or ""), p.get("player_name"))
    for b in (by.get(us) or {}).get("bat") or []:
        seen.setdefault(str(b.get("batsman_id") or ""), b.get("batsman_name"))
    for b in (by.get(them) or {}).get("bowl") or []:
        seen.setdefault(str(b.get("bowler_id") or ""), b.get("bowler_name"))
    return [(pid, str(n or "").strip()) for pid, n in seen.items()
            if pid not in ("", "0", "None") and P._norm(n) not in P.NO_NAME]


def record(cfg, data, detail):
    """Note who played in this scorecard. Returns its team and date."""
    side = P.Side(cfg).of(detail)
    d = parse_date(detail.get("match_date"))
    if not side or not d:
        return None, None
    team = detail.get(f"{side}_team_name", "").strip()
    kind = "a" if _adult(cfg, team) else ("j" if cfg.is_junior(team) else None)
    if kind:
        for pid, _ in players_in(cfg, detail):
            rec = data["players"].setdefault(pid, {})
            if not rec.get(kind) or d.isoformat() < rec[kind]:
                rec[kind] = d.isoformat()
    data["checked"].append(str(detail.get("id")))
    return team, d


def build(cfg, pc, root, today, pause=0.3, sleep=time.sleep):
    """Read every scorecard from first_season not yet read. Returns how many were read."""
    data = load(root)
    checked = set(data["checked"])
    side_of = P.Side(cfg)
    n = 0
    for season in range(int(cfg["debuts"]["first_season"]), today.year + 1):
        try:
            matches = pc.season_results(season)
        except PlayCricketError as e:
            log.warning("season %s: %s", season, e)
            return n  # try again next time; don't mark the history complete
        for m in matches:
            mid = str(m["id"])
            d = parse_date(m.get("match_date"))
            if mid in checked or not d or d >= today:
                continue
            side = side_of.of(m)
            if not side or P.outcome(m, side, cfg)[0] in ("A", "C"):
                checked.add(mid)
                data["checked"].append(mid)
                continue
            try:
                record(cfg, data, pc.match_detail(mid))
            except PlayCricketError as e:
                log.warning("match %s: %s", mid, e)
                continue
            checked.add(mid)
            n += 1
            if pause:
                sleep(pause)
        save(root, data)
    data["built"] = True
    save(root, data)
    return n


def _known_before(root):
    """Play-Cricket ids and name keys of players in the CricketStatz history (they've played before)."""
    ids = set(load_links(root))
    keys = {b["key"] for b in load_baseline(root).values()}
    return ids, keys


def debut_posts(cfg, root, data, detail, card, photos=None):
    """Debut posts for one new scorecard, recording its players. [] when the history isn't built yet."""
    if not cfg["debuts"]["enabled"]:
        return []
    side = P.Side(cfg).of(detail)
    d = parse_date(detail.get("match_date"))
    if not side or not d or not card:
        return []
    team = card["team"]
    before = {pid: dict(data["players"].get(pid, {})) for pid, _ in players_in(cfg, detail)}
    record(cfg, data, detail)
    if not data["built"] or not _adult(cfg, team):
        return []
    ids, keys = _known_before(root)
    rule = cfg["juniors"]["names"]
    out = []
    for pid, full in players_in(cfg, detail):
        rec = before.get(pid, {})
        if rec.get("a") and rec["a"] < d.isoformat():
            continue  # played adult cricket for us before
        if pid in ids or (not rec.get("j") and pc_key(full) in keys):
            continue  # in the CricketStatz history
        youth = bool(rec.get("j")) and rec["j"] < d.isoformat()
        if youth and not cfg["debuts"]["adult_debuts"]:
            continue
        if not youth and not cfg["debuts"]["club_debuts"]:
            continue
        name = P.person_name(full, card["names_shortened"], rule) if card["show_names"] else ""
        if not name:
            continue
        bat = next((b for b in card["all_batting"] if b["player_id"] == pid), None)
        bowl = next((b for b in card["all_bowling"] if b["player_id"] == pid and b["w"] > 0), None)
        figs = " & ".join(x for x in ((bat["figures"] if bat else ""), (bowl["figures"] if bowl else "")) if x)
        photo = ""
        if photos and not youth and not card["junior"]:
            found = photos.find(full)
            if found and found[1] == "adults":
                photo = str(found[0])
        label = "Adult debut" if youth else "Club debut"
        opp = f"{card['opponent']} {card['opponent_team']}".strip()
        data_ = {"kind": "milestone", "type": "debut", "label": label, "figures": "", "detail": f"{figs} on debut" if figs else "",
                 "name": name, "photo_path": photo, "team": team, "opponent": opp, "date": card["date"],
                 "date_obj": card.get("date_obj"), "kicker": "Welcome" if not youth else "From our juniors"}
        lines = ([f"🌱 From our juniors to the {team}! Congratulations to {name} on their adult debut v {opp}."]
                 if youth else [f"👋 Welcome to {cfg['club']['name']}, {name}! A debut for our {team} v {opp}."])
        if figs:
            lines.append(f"{figs} on debut.")
        out.append({"key": f"debut-{pid}", "kind": "milestone", "title": f"{label}: {name} ({team})",
                    "data": data_, "caption": "\n".join(lines) + P._tags(cfg),
                    "alt": f"{cfg['club']['name']}: {label.lower()} for {name}, {team} v {opp}, {card['date']}."})
    return out[: int(cfg["debuts"]["max_per_match"])]
