"""Throwback Thursday (club.yml → throwback): a standout game from a past season, posted each Thursday in winter,
oldest first.

`build` looks through every season from first_season on Play-Cricket and keeps a short note of each standout
game in state/throwbacks.json: a century, a five-wicket haul, a big or very close win, a tie or a big total.
It saves the match id, date, team and why, never player names: those are read from Play-Cricket again when
the post is made, so the usual naming rules (juniors shortened) apply. Each game is used only once.
"""
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

from . import posts as P
from .playcricket import PlayCricketError, parse_date

log = logging.getLogger(__name__)
FILE = "state/throwbacks.json"
VERDICT = {"century": "Century", "five-for": "Five-for", "big win": "Big win", "ten-wicket win": "10-wicket win",
           "thriller": "Thriller", "tie": "Tied!", "big total": "Big total"}
MIN_SCORE = 70


def load(root):
    try:
        data = json.loads((Path(root) / FILE).read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    data.setdefault("checked", [])
    data.setdefault("moments", [])
    data.setdefault("used", {})
    return data


def save(root, data):
    p = Path(root) / FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    data["checked"] = sorted(set(data["checked"]))
    data["moments"].sort(key=lambda m: m["date"])
    p.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def _lead_int(s):
    m = re.match(r"\s*(\d+)", str(s or ""))
    return int(m.group(1)) if m else 0


def best_moment(card):
    """(score, why) for one match card: the best reason to look back on it, or (0, "")."""
    options = [(0, "")]
    win = card["outcome"] == "W"
    bat = card["all_batting"][0] if card.get("all_batting") else None
    if bat and bat["runs"] >= 100:
        options.append((100 + (bat["runs"] - 100) * 2 + (10 if win else 0), "century"))
    bowl = card["all_bowling"][0] if card.get("all_bowling") else None
    if bowl and bowl["w"] >= 5:
        options.append((90 + (bowl["w"] - 5) * 25 - bowl["r"] // 5 + (10 if win else 0), "five-for"))
    if win:
        s = card["summary"]
        runs = re.search(r"by (\d+) runs?", s)
        wkts = re.search(r"by (\d+) wickets?", s)
        if runs and int(runs.group(1)) >= 150:
            options.append((80 + (int(runs.group(1)) - 150) // 5, "big win"))
        if wkts and int(wkts.group(1)) >= 10:
            options.append((85, "ten-wicket win"))
        if (runs and int(runs.group(1)) <= 3) or (wkts and int(wkts.group(1)) == 1):
            options.append((85, "thriller"))
        if _lead_int(card["us_score"]) >= 300:
            options.append((75 + (_lead_int(card["us_score"]) - 300) // 5, "big total"))
    if card["outcome"] == "T":
        options.append((80, "tie"))
    return max(options)


def build(cfg, pc, root, today, limit=None, pause=0.3, sleep=time.sleep):
    """Add standout games from new matches to the archive. Returns (matches checked, moments added)."""
    tb = cfg["throwback"]
    data = load(root)
    checked = set(data["checked"])
    have = {m["id"] for m in data["moments"]}
    looked = added = 0
    side_of = P.Side(cfg)
    for season in range(int(tb["first_season"]), today.year + 1):
        try:
            matches = pc.season_results(season)
        except PlayCricketError as e:
            log.warning("season %s: %s", season, e)
            continue
        for m in matches:
            mid = str(m["id"])
            d = parse_date(m.get("match_date"))
            if mid in checked or not d or d >= today:
                continue
            side = side_of.of(m)
            if not side or P.outcome(m, side, cfg)[0] not in ("W", "L", "D", "T"):
                checked.add(mid)
                continue
            if limit is not None and looked >= limit:
                data["checked"] = list(checked)
                save(root, data)
                return looked, added
            looked += 1
            try:
                card = P.match_card(cfg, pc.match_detail(mid))
            except PlayCricketError as e:
                log.warning("match %s: %s", mid, e)
                continue  # try again next time
            checked.add(mid)
            if card:
                score, why = best_moment(card)
                if score >= MIN_SCORE and mid not in have:
                    data["moments"].append({"id": mid, "date": d.isoformat(), "team": card["team"],
                                            "score": score, "why": why})
                    have.add(mid)
                    added += 1
            if pause:
                sleep(pause)
        data["checked"] = list(checked)
        save(root, data)
    data["checked"] = list(checked)
    save(root, data)
    return looked, added


def due(cfg, today):
    tb = cfg["throwback"]
    from .config import DAYS
    return bool(tb["enabled"]) and DAYS[today.weekday()] == tb["day"].lower() and today.month in tb["months"]


def pick(cfg, data, today):
    """The next game to look back on: the oldest one not used yet, so the posts work forward in time and the
    most recent seasons (freshest in people's minds) come last. Where it can, it skips a team used in the
    last three weeks, taking the next oldest game instead."""
    used = data["used"]
    last = sorted((kv for kv in used.items() if kv[1][:1].isdigit()), key=lambda kv: kv[1])[-3:]
    by_id = {m["id"]: m for m in data["moments"]}
    recent_teams = {by_id[i]["team"] for i, _ in last if i in by_id}
    exclude = cfg["throwback"].get("exclude_teams") or ""
    pool = [m for m in data["moments"] if m["id"] not in used and m["date"] < today.isoformat()
            and not (exclude and re.search(exclude, m["team"], re.I))]
    for strict in (True, False):
        c = [m for m in pool if not strict or m["team"] not in recent_teams]
        if c:
            return min(c, key=lambda m: (m["date"], -m["score"]))
    return None

def _years_ago(d, today):
    n = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return "last season" if n < 1 else ("a year ago" if n == 1 else f"{n} years ago")


def headline(card, why):
    if why == "century" and card["show_names"] and card["top_batting"]:
        b = card["top_batting"][0]
        return f"{b['name']} hit {b['figures']}"
    if why == "five-for" and card["show_names"] and card["top_bowling"]:
        b = card["top_bowling"][0]
        return f"{b['name']} took {b['figures']}"
    return {"century": "A century", "five-for": "A five-wicket haul", "big total": f"{card['us_score']} on the board"
            }.get(why, card["summary"])


def throwback_post(cfg, pc, root, today):
    """The Throwback Thursday post, or None when there's nothing left to look back on."""
    data = load(root)
    if today.isoformat() in data["used"].values():
        return None  # already looked back today
    for _ in range(5):  # a game that can no longer be read is skipped
        m = pick(cfg, data, today)
        if not m:
            return None
        try:
            card = P.match_card(cfg, pc.match_detail(m["id"]))
        except PlayCricketError as e:
            log.warning("throwback %s: %s", m["id"], e)
            card = None
        if card:
            break
        data["used"][m["id"]] = f"skipped {today.isoformat()}"
        save(root, data)
    else:
        return None
    data["used"][m["id"]] = today.isoformat()
    save(root, data)
    tb = cfg["throwback"]
    ago = _years_ago(card["date_obj"], today)
    head = headline(card, m["why"])
    card["throwback"] = {"label": tb["title"], "verdict": VERDICT.get(m["why"], "Throwback"), "ago": ago,
                         "headline": head, "why": m["why"]}
    us_ov = f" ({card['us_overs']})" if card["us_overs"] else ""
    op_ov = f" ({card['opp_overs']})" if card["opp_overs"] else ""
    lines = [f"📸 {tb['title']}: {card['date']} ({ago})", "",
             f"{head} for our {card['team']} v {card['opponent']} {card['opponent_team']}.".replace("  ", " ")
             if head != card["summary"] else f"Our {card['team']} v {card['opponent']} {card['opponent_team']}.".replace("  ", " "),
             f"{card['summary']}. {cfg.short_name} {card['us_score']}{us_ov} · {card['opponent']} {card['opp_score']}{op_ov}",
             "", tb["question"]]
    return {"key": f"throwback-{m['id']}", "kind": "throwback", "match_id": m["id"],
            "title": f"{tb['title']}: {card['team']} v {card['opponent']} ({card['date']})",
            "data": card, "caption": "\n".join(l for l in lines if l is not None).rstrip() + P._tags(cfg) + " #ThrowbackThursday",
            "alt": f"{tb['title']}: {P.alt_match(cfg, card)} {head}."}

