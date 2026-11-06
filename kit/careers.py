"""Career milestones: 500 runs (and every 500), 50 wickets / matches / catches / keeping catches (and every 50).

Two separate pools:
- club: Saturday, midweek and Sunday sides. Starting totals come from CricketStatz (careers/baseline.csv,
  up to the end of the baseline season); every outdoor Play-Cricket game after that is added.
- softball: Women's Softball (pairs). Play-Cricket only: the kit adds up every outdoor season on
  Play-Cricket once (backfill), then adds each new game.

A milestone post is made the morning after the game in which a player passes the mark. Players are
matched between CricketStatz ("Gajic C") and Play-Cricket ("Chris Gajic") by surname and first initial;
names that match more than one CricketStatz player go in careers/links.csv (set by hand).
"""
import csv
import json
import logging
import re
from datetime import date

from .playcricket import PlayCricketError, parse_date
from .posts import NO_NAME, Side, _innings_by_team, _int, _norm, _other, _tags, person_name

log = logging.getLogger(__name__)
STATE = "state/careers.json"
BASELINE = "careers/baseline.csv"
LINKS = "careers/links.csv"
STATS = ("matches", "runs", "wickets", "catches", "keeper_catches")
CAUGHT = {"ct", "c", "caught"}
CAUGHT_BOWLED = {"ct & b", "c & b", "c&b", "ct&b", "caught and bowled", "ct and b"}
WORDS = {"runs": ("career runs", "runs"), "wickets": ("career wickets", "wickets"),
         "matches": ("appearances", "matches"), "catches": ("career catches", "catches"),
         "keeper_catches": ("catches behind the stumps", "catches as wicketkeeper")}
EMOJI = {"runs": "🏏", "wickets": "🎯", "matches": "🙌", "catches": "🧤", "keeper_catches": "🧤"}


def cs_key(name):
    """'Gajic C' / 'McLeonards S' -> 'gajic|c'."""
    parts = (name or "").replace(".", " ").split()
    if len(parts) < 2:
        return _norm(name)
    initial, surname = parts[-1], " ".join(parts[:-1])
    if len(initial) > 2:  # 'Chris Gajic' style: first name first
        return pc_key(name)
    return f"{_norm(surname)}|{initial[0].lower()}"


def pc_key(full_name):
    """'Chris Gajic' / 'Tom Stainer-Reid' -> 'gajic|c' / 'stainerreid|t'."""
    parts = (full_name or "").replace(".", " ").split()
    if len(parts) < 2:
        return _norm(full_name)
    return f"{_norm(parts[-1])}|{parts[0][0].lower()}"


def load_baseline(root):
    """{cs_id: {name, key, matches, runs, ...}} from careers/baseline.csv."""
    path = root / BASELINE
    if not path.exists():
        return {}
    out = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = (row.get("id") or row.get("name") or "").strip()
            if not cid:
                continue
            out[cid] = {"name": row["name"].strip(), "key": cs_key(row["name"]),
                        **{s: _int(row.get(s)) for s in STATS}}
    return out


def load_links(root):
    """Hand-made links: Play-Cricket player id or full name -> CricketStatz id (or 'new')."""
    path = root / LINKS
    out = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pc, cs = (row.get("play_cricket") or "").strip(), (row.get("cricketstatz") or "").strip()
                if pc and cs:
                    out[pc] = cs  # by Play-Cricket player id
    return out


def load_links_rows(root):
    path = root / LINKS
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def ambiguous(baseline):
    by = {}
    for cid, b in baseline.items():
        by.setdefault(b["key"], []).append(cid)
    return {k: v for k, v in by.items() if len(v) > 1}


def _keeper(players):
    for p in players:
        if str(p.get("wicket_keeper")).lower() in ("true", "1", "yes"):
            return p
    return None


def _team_players(detail, side):
    for block in detail.get("players") or []:
        if isinstance(block, dict) and f"{side}_team" in block:
            return block[f"{side}_team"] or []
    return []


def match_figures(cfg, detail):
    """{player: {name, pid, matches, runs, wickets, catches, keeper_catches}} for our side, or None."""
    side = Side(cfg).of(detail)
    if not side:
        return None
    us, them = str(detail.get(f"{side}_team_id")), str(detail.get(f"{_other(side)}_team_id"))
    by = _innings_by_team(detail)
    if not by:
        return None
    figs = {}

    def who(pid, name):
        name = str(name or "").strip()
        if _norm(name) in NO_NAME:
            return None
        k = f"id:{pid}" if pid and str(pid) not in ("0", "None", "") else f"n:{_norm(name)}"
        return figs.setdefault(k, {"name": name, "pid": str(pid or ""), **{s: 0 for s in STATS}})

    players = _team_players(detail, side)
    for p in players:
        f = who(p.get("player_id"), p.get("player_name"))
        if f:
            f["matches"] = 1
    for b in (by.get(us) or {}).get("bat") or []:
        f = who(b.get("batsman_id"), b.get("batsman_name"))
        if f:
            f["matches"] = 1
            if str(b.get("how_out") or "").strip().lower() != "did not bat":
                f["runs"] += _int(b.get("runs"))
    for b in (by.get(them) or {}).get("bowl") or []:
        f = who(b.get("bowler_id"), b.get("bowler_name"))
        if f:
            f["matches"] = 1
            f["wickets"] += _int(b.get("wickets"))
    keeper = _keeper(players)
    kid = str((keeper or {}).get("player_id") or "")
    kname = _norm((keeper or {}).get("player_name"))
    for b in (by.get(them) or {}).get("bat") or []:
        how = str(b.get("how_out") or "").strip().lower()
        if how in CAUGHT_BOWLED:
            f = who(b.get("bowler_id"), b.get("bowler_name"))
            if f:
                f["catches"] += 1
        elif how in CAUGHT:
            f = who(b.get("fielder_id"), b.get("fielder_name"))
            if f:
                f["catches"] += 1
                if keeper and ((kid and f["pid"] == kid) or (not kid and _norm(f["name"]) == kname)):
                    f["keeper_catches"] += 1
    return figs


def pool_for(cfg, team):
    cm = cfg["career_milestones"]
    if re.search(r"\bIndoor\b", team or "", re.I) or cfg.is_junior(team):
        return None
    if re.search(cm["softball_teams"], team or "", re.I):
        return "softball"
    if re.search(cm["club_teams"], team or "", re.I):
        return "club"
    return None


def crossings(before, after, every):
    """Milestones passed going from before to after, e.g. (480, 530, 500) -> [500]."""
    if every <= 0 or after <= before:
        return []
    return list(range((before // every + 1) * every, after + 1, every))


class Careers:
    """Running career totals. Play-Cricket figures are kept per Play-Cricket player (state/careers.json);
    a club player's career = their CricketStatz starting totals + their Play-Cricket figures since."""

    def __init__(self, cfg, root):
        self.cfg, self.root = cfg, root
        self.baseline = load_baseline(root)
        self.links = load_links(root)
        self.ambiguous = ambiguous(self.baseline)
        self.by_key = {b["key"]: cid for cid, b in self.baseline.items() if b["key"] not in self.ambiguous}
        try:
            self.state = json.loads((root / STATE).read_text())
        except (FileNotFoundError, ValueError):
            self.state = {}
        self.state.setdefault("counted", {})      # match id -> pool
        self.state.setdefault("players", {})      # "pool|pid" -> {name, pid, Play-Cricket totals}

    def save(self):
        p = self.root / STATE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.state, indent=1, sort_keys=True) + "\n")

    def link(self, pid, key):
        """CricketStatz id for a Play-Cricket player (by id and surname|initial key): 'new', an id, or None
        if it needs deciding by hand."""
        hand = self.links.get(pid)
        if hand:
            ids = [h.strip() for h in hand.split("+")]
            return hand if all(h in self.baseline for h in ids) else "new"
        if key in self.ambiguous:
            return None
        cid = self.by_key.get(key)
        if not cid:
            return "new"
        # Two different Play-Cricket players with the same surname and initial: decide by hand
        others = [r for k, r in self.state["players"].items()
                  if k.startswith("club|") and r["pid"] != pid and r.get("key") == key and not self.links.get(r["pid"])]
        return None if others else cid

    def career(self, pool, rec):
        """Full career totals for a player record, and whether milestones can be announced."""
        if pool == "softball":
            return {s: rec[s] for s in STATS}, True
        cid = self.link(rec["pid"], rec.get("key", ""))
        bases = [self.baseline[c.strip()] for c in cid.split("+")] if cid not in (None, "new") else []
        return {s: rec[s] + sum(b[s] for b in bases) for s in STATS}, cid is not None

    def needs_linking(self):
        """Play-Cricket club players that can't be matched to CricketStatz automatically."""
        out = []
        for k, r in self.state["players"].items():
            if k.startswith("club|") and self.link(r["pid"], r.get("key", "")) is None:
                out.append({"play_cricket": r["pid"], "name": r.get("short", ""),
                            "could_be": [c for c, b in self.baseline.items() if b["key"] == r.get("key")]})
        return out

    def add_match(self, detail, announce=True):
        """Add one game. Returns milestone events if announce."""
        mid = str(detail.get("id"))
        if mid in self.state["counted"]:
            return []
        side = Side(self.cfg).of(detail)
        team = str(detail.get(f"{side}_team_name") or "").strip() if side else ""
        pool = pool_for(self.cfg, team)
        if not pool:
            return []
        figs = match_figures(self.cfg, detail)
        if figs is None:
            return []  # no scorecard yet: try again another day
        every = self.cfg["career_milestones"]["every"]
        events = []
        for f in figs.values():
            pkey = f"{pool}|{f['pid'] or 'n:' + pc_key(f['name'])}"
            short = person_name(f["name"], True, "initial")
            rec = self.state["players"].setdefault(pkey, {"key": pc_key(f["name"]), "short": short, "pid": f["pid"],
                                                          **{s: 0 for s in STATS}})
            rec["key"], rec["short"] = pc_key(f["name"]), short
            before, ok = self.career(pool, rec)
            for s in STATS:
                rec[s] += f[s]
            after, _ = self.career(pool, rec)
            if announce and ok:
                for s in STATS:
                    for v in crossings(before[s], after[s], int(every.get(s) or 0)):
                        events.append({"pool": pool, "stat": s, "value": v, "name": f["name"], "pid": rec["pid"],
                                       "pkey": pkey, "team": team, "match": detail})
        self.state["counted"][mid] = pool
        return events


def _opponent(detail, side):
    o = _other(side)
    return f"{detail.get(f'{o}_club_name', '')} {detail.get(f'{o}_team_name', '')}".strip()


def career_posts(cfg, events, photos=None):
    """Post dicts for career milestone events."""
    from .milestones import presentation
    out = []
    rule = cfg["juniors"]["names"]
    for e in events:
        d = e["match"]
        side = Side(cfg).of(d)
        when = parse_date(d.get("match_date"))
        if cfg["career_milestones"].get("names") == "full":
            name = e["name"].strip()  # career stats: always the full name
        else:
            name = person_name(e["name"], True, rule)
        card = {"show_names": rule != "none" or cfg["career_milestones"].get("names") == "full", "junior": False}
        shown, photo, why = presentation(cfg, card, {"full_name": e["name"], "name": name}, photos)
        if why.startswith("junior"):
            shown, photo, why = name, None, "junior: full name, no photo"  # ECB: never a junior's photo with their name
        big, small = WORDS[e["stat"]]
        where = "in Women's Softball" if e["pool"] == "softball" else f"for {cfg.short_name}"
        label = ("Softball " + big) if e["pool"] == "softball" else big.capitalize()
        context = f"Reached for our {e['team']} v {_opponent(d, side)}"
        data = {"kind": "milestone", "type": e["stat"], "label": label, "figures": f"{e['value']:,}",
                "detail": where, "name": shown, "photo_path": str(photo) if photo else "",
                "team": e["team"], "opponent": _opponent(d, side),
                "date": f"{when:%A} {when.day} {when:%B %Y}" if when else "", "context": context, "career": True}
        who = shown or f"one of our {e['team']} players"
        noun = {"runs": "career runs", "wickets": "career wickets", "matches": "appearances",
                "catches": "career catches", "keeper_catches": "catches as wicketkeeper"}[e["stat"]]
        caption = (f"{EMOJI[e['stat']]} Congratulations to {who} on {e['value']:,} {noun} {where}!\n"
                   f"Reached in our {e['team']} game v {_opponent(d, side)}.") + _tags(cfg)
        out.append({"key": f"career-{e['pool']}-{e['stat']}-{e['value']}-{re.sub(r'[^a-z0-9]', '', e['pkey'].lower())}",
                    "kind": "milestone", "title": f"Career milestone: {who}, {e['value']:,} {noun}",
                    "data": data, "caption": caption,
                    "alt": f"{cfg['club']['name']} career milestone: {who}, {e['value']:,} {noun} {where}.",
                    "photo_rule": why})
    return out


def backfill_softball(cfg, pc, careers, today):
    """One-time: add every past outdoor Women's Softball game on Play-Cricket (no posts)."""
    cm = cfg["career_milestones"]
    done_to = careers.state.get("softball_backfilled_to")
    first = int(cm["softball_history_from"])
    if done_to and int(done_to) >= today.year - 1:
        return 0
    n = 0
    for season in range(int(done_to or first - 1) + 1, today.year):
        try:
            rs = pc.results(date(season, 4, 1), date(season, 9, 30))
        except PlayCricketError as e:
            log.warning("Softball history %s: %s", season, e)
            return n
        for m in rs:
            side = Side(cfg).of(m)
            if not side or pool_for(cfg, str(m.get(f"{side}_team_name") or "")) != "softball":
                continue
            if str(m["id"]) in careers.state["counted"]:
                continue
            try:
                careers.add_match(pc.match_detail(m["id"]), announce=False)
                n += 1
            except PlayCricketError as e:
                log.warning("Softball match %s: %s", m["id"], e)
        careers.state["softball_backfilled_to"] = season
    return n


def new_games(cfg, pc, today, careers):
    """Milestone events from outdoor games since the baseline, not yet counted (posts only for recent ones)."""
    cm = cfg["career_milestones"]
    start = date(int(cm["baseline_until"]) + 1, 1, 1)
    end = today
    if end < start:
        return []
    events = []
    look_from = today.toordinal() - int(cm.get("announce_within_days", 7))
    for m in pc.results(start, end):
        side = Side(cfg).of(m)
        if not side or not pool_for(cfg, str(m.get(f"{side}_team_name") or "")):
            continue
        if str(m["id"]) in careers.state["counted"] or str(m.get("result") or "").upper() in ("", "A", "C"):
            continue
        d = parse_date(m.get("match_date"))
        if not d or not (4 <= d.month <= 9):
            continue  # outdoor summer games only
        try:
            detail = pc.match_detail(m["id"])
        except PlayCricketError as e:
            log.warning("Career totals: match %s: %s", m["id"], e)
            continue
        events += careers.add_match(detail, announce=d.toordinal() >= look_from)
    return events
