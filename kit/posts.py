"""Turn Play-Cricket API data into post data (for the templates) and captions."""
import logging
import re
from datetime import timedelta

from .playcricket import parse_date

log = logging.getLogger("kit")

WIN_CODES = {"W", "WT", "TW", "DLW", "W-", "WCN"}
LOSS_CODES = {"L", "LT", "TL", "LOL", "DLL"}
DRAW_CODES = {"D", "WD", "LD", "ED"}
NEUTRAL = {"T": ("T", "Match tied"), "A": ("A", "Abandoned"), "C": ("C", "Cancelled"),
           "CON": ("N", "Conceded"), "N": ("N", "No result"), "NR": ("N", "No result"),
           "ABN": ("A", "Abandoned")}
NOT_OUT = {"not out", "retired not out", "retired hurt", "retired", "absent hurt"}
NO_NAME = {"", "unsure", "unknown", "extras"}


# --- helpers -----------------------------------------------------------------

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _int(x, default=0):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def short_date(d):
    return d.strftime("%a ") + str(d.day) + d.strftime(" %b")


def long_date(d):
    return d.strftime("%A ") + str(d.day) + d.strftime(" %B %Y")


def date_range(dates):
    dates = sorted(d for d in dates if d)
    if not dates:
        return ""
    a, b = dates[0], dates[-1]
    if a == b:
        return f"{a.day} {a:%B %Y}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day} – {b.day} {b:%B %Y}"
    if a.year == b.year:
        return f"{a.day} {a:%b} – {b.day} {b:%b %Y}"
    return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"


def person_name(name, junior, rule):
    name = re.sub(r"\s+", " ", (name or "").replace("*", "")).strip()
    if not junior or rule == "full":
        return name
    parts = name.split(" ")
    if rule == "first" or len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


class Side:
    """Which side of a Play-Cricket match is 'us'."""

    def __init__(self, cfg):
        self.ids = {str(cfg["club"].get("play_cricket_club_id") or cfg.site_id)}
        self.name = _norm(cfg["club"]["play_cricket_name"])

    def of(self, m):
        for side in ("home", "away"):
            if str(m.get(f"{side}_club_id", "")) in self.ids or (self.name and _norm(m.get(f"{side}_club_name")) == self.name):
                return side
        return None


def _other(side):
    return "away" if side == "home" else "home"


def opponent_label(m, side):
    o = _other(side)
    return " ".join(x for x in (m.get(f"{o}_club_name", "").strip(), m.get(f"{o}_team_name", "").strip()) if x)


# --- fixtures ----------------------------------------------------------------

def clean_ground(name):
    """Play-Cricket uses 'Add New Ground' as a placeholder when no ground is set."""
    name = (name or "").strip()
    return "" if name.lower() in ("add new ground", "tbc", "tba") else name


def fixture_rows(cfg, matches):
    side_of = Side(cfg)
    rows = []
    for m in matches:
        side = side_of.of(m)
        if not side:
            continue
        d = parse_date(m["match_date"])
        rows.append({"id": str(m["id"]), "date_obj": d, "date": short_date(d),
                     "time": (m.get("match_time") or "").strip() or "TBC",
                     "team": m.get(f"{side}_team_name", "").strip(), "opponent": opponent_label(m, side),
                     "home": side == "home", "ground": clean_ground(m.get("ground_name"))})
    return rows


# --- results -----------------------------------------------------------------

def score_text(inn, team_name, cfg):
    if not inn or (str(inn.get("runs", "")) == "" and str(inn.get("wickets", "")) == ""):
        return "–", ""
    runs, wkts = _int(inn.get("runs")), _int(inn.get("wickets"))
    overs = str(inn.get("overs") or "").strip()
    wpi = int(cfg["scoring"]["wickets_per_innings"])
    if wkts >= wpi and not cfg.no_wicket_margin(team_name):
        s = f"{runs} all out"
    else:
        s = f"{runs}/{wkts}" + ("d" if inn.get("declared") in (True, "true", "True") else "")
    return s, overs


def _innings_by_team(m):
    out = {}
    for inn in m.get("innings") or []:
        out.setdefault(str(inn.get("team_batting_id")), inn)
    return out


def outcome(m, side, cfg):
    """(code, text) from our point of view. code: W L D T A C N P(=to follow)."""
    us, them = str(m.get(f"{side}_team_id")), str(m.get(f"{_other(side)}_team_id"))
    r = str(m.get("result") or "").strip().upper()
    applied = str(m.get("result_applied_to") or "").strip()
    if r in NEUTRAL:
        return NEUTRAL[r]
    if r in DRAW_CODES:
        return "D", "Match drawn"
    if r in WIN_CODES | LOSS_CODES:
        if applied not in (us, them):
            return "P", "Result to follow"
        winner = applied if r in WIN_CODES else (them if applied == us else us)
        code = "W" if winner == us else "L"
        return code, ("Won" if code == "W" else "Lost") + margin(m, winner, us, them, side, cfg)
    return "P", "Result to follow"


def margin(m, winner, us, them, side, cfg):
    inns = m.get("innings") or []
    if str(m.get("no_of_innings") or "1") not in ("", "1") or len(inns) < 2:
        return ""
    if any(str(i.get("revised_target_runs") or "").strip() for i in inns):
        return " (revised target)"
    first_id = str(m.get("batted_first") or inns[0].get("team_batting_id"))
    by = _innings_by_team(m)
    first, second = by.get(first_id), by.get(them if first_id == us else us)
    if not first or not second:
        return ""
    if winner == first_id:
        diff = _int(first.get("runs")) - _int(second.get("runs"))
        return f" by {diff} run{'s' if diff != 1 else ''}" if diff > 0 else ""
    team_name = m.get(f"{side}_team_name", "")
    if cfg.no_wicket_margin(team_name):
        return ""
    left = int(cfg["scoring"]["wickets_per_innings"]) - _int(second.get("wickets"))
    return f" by {left} wicket{'s' if left != 1 else ''}" if left > 0 else ""


def result_row(cfg, m, side):
    d = parse_date(m["match_date"])
    us_id, them_id = str(m.get(f"{side}_team_id")), str(m.get(f"{_other(side)}_team_id"))
    team = m.get(f"{side}_team_name", "").strip()
    by = _innings_by_team(m)
    us_score, us_overs = score_text(by.get(us_id), team, cfg)
    op_score, op_overs = score_text(by.get(them_id), team, cfg)
    code, text = outcome(m, side, cfg)
    return {"id": str(m["id"]), "date_obj": d, "date": short_date(d), "team": team,
            "opponent": opponent_label(m, side), "home": side == "home",
            "us_score": us_score + (f" ({us_overs})" if us_overs else ""),
            "opp_score": op_score + (f" ({op_overs})" if op_overs else ""),
            "us_runs": us_score, "us_overs": f"{us_overs} overs" if us_overs else "",
            "opp_runs": op_score, "opp_overs": f"{op_overs} overs" if op_overs else "",
            "outcome": code, "summary": text,
            "opp_club": m.get(f"{_other(side)}_club_name", "").strip(),
            "opp_team": m.get(f"{_other(side)}_team_name", "").strip()}


def result_rows(cfg, matches):
    side_of = Side(cfg)
    rows = []
    for m in matches:
        side = side_of.of(m)
        if side:
            rows.append(result_row(cfg, m, side))
    return rows


# --- single match card from match_detail -------------------------------------

def match_card(cfg, detail):
    """Post data for one match, or None if there's no usable scorecard."""
    side = Side(cfg).of(detail)
    if not side:
        return None
    row = result_row(cfg, detail, side)
    if row["outcome"] == "P":
        return None
    us, them = str(detail.get(f"{side}_team_id")), str(detail.get(f"{_other(side)}_team_id"))
    junior = cfg.is_junior(row["team"])
    rule = cfg["juniors"]["names"]
    by = _innings_by_team(detail)
    batting, bowling = [], []
    for b in (by.get(us) or {}).get("bat") or []:
        how = str(b.get("how_out") or "").strip().lower()
        name = str(b.get("batsman_name") or "").strip()
        if how == "did not bat" or _norm(name) in NO_NAME:
            continue
        runs = _int(b.get("runs"), None)
        if runs is None:
            continue
        balls = str(b.get("balls") or "").strip()
        batting.append({"name": person_name(name, junior, rule), "runs": runs, "balls": _int(balls, 999),
                        "figures": f"{runs}{'*' if how in NOT_OUT else ''}",
                        "detail": f"{balls} balls" if balls not in ("", "0") else ""})
    for b in (by.get(them) or {}).get("bowl") or []:
        name = str(b.get("bowler_name") or "").strip()
        if _norm(name) in NO_NAME:
            continue
        w, r = _int(b.get("wickets")), _int(b.get("runs"))
        overs = str(b.get("overs") or "").strip()
        bowling.append({"name": person_name(name, junior, rule), "w": w, "r": r, "figures": f"{w}-{r}",
                        "detail": f"{overs.removesuffix('.0')} overs" if overs else ""})
    if not batting and not bowling:
        return None  # result entered but no scorecard
    batting.sort(key=lambda p: (-p["runs"], p["balls"]))
    bowling.sort(key=lambda p: (-p["w"], p["r"]))
    show_names = not (junior and rule == "none")
    return {
        "kind": "match", "id": row["id"], "date": long_date(row["date_obj"]), "date_obj": row["date_obj"],
        "team": row["team"], "opponent": row["opp_club"], "opponent_team": row["opp_team"],
        "outcome": row["outcome"],
        "summary": f"{cfg.short_name} {row['summary'][0].lower()}{row['summary'][1:]}" if row["outcome"] in "WL" else row["summary"],
        "us_score": row["us_runs"], "us_overs": row["us_overs"],
        "opp_score": row["opp_runs"], "opp_overs": row["opp_overs"],
        "toss": tidy_toss(detail.get("toss"), cfg, side, detail),
        "top_batting": [p for p in batting if p["runs"] > 0][:3] if show_names else [],
        "top_bowling": [p for p in bowling if p["w"] > 0][:3] if show_names else [],
        "junior": junior,
    }


def tidy_toss(toss, cfg, side, m):
    toss = (toss or "").strip()
    if not toss:
        return ""
    ours = f"{m.get(f'{side}_club_name', '')} - {m.get(f'{side}_team_name', '')}".strip(" -")
    return toss.replace(ours, cfg.short_name, 1) if ours and ours in toss else ""


# --- captions ----------------------------------------------------------------

ICON = {"W": "✅", "L": "❌", "D": "🤝", "T": "🤝", "A": "🌧️", "C": "🚫", "N": "➖"}


def _tags(cfg):
    """Sponsor line (if switched on) and hashtags, added to the end of every caption."""
    b = cfg["branding"]
    extra = []
    if b.get("sponsor_in_captions") and (b.get("sponsor_text") or "").strip():
        extra.append(f"{(b.get('sponsor_label') or 'Supported by').strip()} {b['sponsor_text'].strip()}")
    t = (cfg["club"].get("hashtags") or "").strip()
    if t:
        extra.append(t)
    return ("\n\n" + "\n".join(extra)) if extra else ""


def caption_fixtures(cfg, data):
    lines = [f"📅 Fixtures · {data['date_range']}", ""]
    for m in data["matches"]:
        lines.append(f"{m['date']} {m['time']} · {m['team']} v {m['opponent']} ({'H' if m['home'] else 'A'})")
    site = cfg["club"].get("website")
    lines += ["", cfg["wording"]["fixtures_sign_off"]] + ([f"Full fixtures: {site}"] if site else [])
    return "\n".join(lines) + _tags(cfg)


def caption_roundup(cfg, data):
    lines = [f"🏏 Results round-up · {data['date_range']}", ""]
    for m in data["matches"]:
        lines.append(f"{ICON.get(m['outcome'], '⏳')} {m['team']} v {m['opponent']}: "
                     f"{m['us_score']} v {m['opp_score']} · {m['summary']}")
    site = cfg["club"].get("website")
    return "\n".join(lines + ([f"\nFull scorecards: {site}"] if site else [])) + _tags(cfg)


def caption_match(cfg, m):
    head = {"W": "🏆 Win for our", "L": "Result for our", "D": "Draw for our", "T": "Tie for our"}.get(m["outcome"], "Update from our")
    perf = []
    if m["top_batting"]:
        perf.append(f"{m['top_batting'][0]['name']} top-scored with {m['top_batting'][0]['figures']}")
    if m["top_bowling"]:
        perf.append(f"{m['top_bowling'][0]['name']} took {m['top_bowling'][0]['figures']}")
    us_ov = f" ({m['us_overs']})" if m["us_overs"] else ""
    op_ov = f" ({m['opp_overs']})" if m["opp_overs"] else ""
    lines = [f"{head} {m['team']}! {m['summary']} v {m['opponent']} {m['opponent_team']}.".replace("  ", " "),
             f"{cfg.short_name} {m['us_score']}{us_ov} · {m['opponent']} {m['opp_score']}{op_ov}"]
    if perf:
        lines.append(" · ".join(perf) + ".")
    return "\n".join(lines) + _tags(cfg)


def alt_match(cfg, m):
    return (f"{cfg['club']['name']} {m['team']} v {m['opponent']} {m['opponent_team']}, {m['date']}: "
            f"{m['summary']}. {cfg.short_name} {m['us_score']}, {m['opponent']} {m['opp_score']}.")


# --- the three post types ----------------------------------------------------

def week_window(today, kind):
    if kind == "fixtures":
        return today, today + timedelta(days=6)
    return today - timedelta(days=7), today - timedelta(days=1)


def fixtures_post(cfg, pc, today):
    start, end = week_window(today, "fixtures")
    rows = fixture_rows(cfg, pc.fixtures(start, end))
    if not rows:
        return None
    data = {"kind": "fixtures", "title": cfg["wording"]["fixtures_title"], "date_range": date_range([start, end]), "matches": rows}
    return {"key": f"fixtures-{today.isoformat()}", "kind": "fixtures", "title": f"Fixtures {data['date_range']}",
            "data": data, "caption": caption_fixtures(cfg, data),
            "alt": f"{cfg['club']['name']} fixtures for {data['date_range']}: {len(rows)} matches."}


def roundup_post(cfg, pc, today):
    start, end = week_window(today, "roundup")
    rows = result_rows(cfg, pc.results(start, end))
    if not rows:
        return None
    data = {"kind": "results", "title": cfg["wording"]["results_title"], "date_range": date_range([r["date_obj"] for r in rows]), "matches": rows}
    wins = sum(r["outcome"] == "W" for r in rows)
    return {"key": f"roundup-{today.isoformat()}", "kind": "roundup", "title": f"Results round-up {data['date_range']}",
            "data": data, "caption": caption_roundup(cfg, data),
            "alt": f"{cfg['club']['name']} results for {data['date_range']}: {len(rows)} matches, {wins} won."}


def match_posts(cfg, pc, today, already_posted):
    days = int(cfg["posts"]["match_results"]["lookback_days"])
    start, end = today - timedelta(days=days), today - timedelta(days=1)
    out, skipped = [], []
    side_of = Side(cfg)
    for m in pc.results(start, end):
        key = f"match-{m['id']}"
        side = side_of.of(m)
        if key in already_posted or not side:
            continue
        label = f"{m.get(f'{side}_team_name', '')} v {opponent_label(m, side)} ({m.get('match_date')})"
        code = outcome(m, side, cfg)[0]
        if code == "P":
            skipped.append(f"{label}: no final result yet")
            continue
        if code in ("A", "C"):
            continue  # abandoned / cancelled: covered by the round-up, no scorecard to show
        try:
            card = match_card(cfg, pc.match_detail(m["id"]))
        except Exception as e:  # one bad match mustn't stop the others
            log.warning("match %s: %s", m["id"], e)
            card = None
        if not card:
            skipped.append(f"{label}: no finished scorecard yet")
            continue
        out.append({"key": key, "kind": "match", "title": f"{card['team']} v {card['opponent']} ({short_date(card['date_obj'])})",
                    "data": card, "caption": caption_match(cfg, card), "alt": alt_match(cfg, card),
                    "match_id": card["id"]})
    return out, skipped
