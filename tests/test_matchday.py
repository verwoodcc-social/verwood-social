"""Matchday: one 'Today' story listing the day's senior games, home and away."""
from argparse import Namespace
from datetime import date

from test_meta_review_run import FakeGitHub, FakeRenderer, meta
from kit import config as C, posts as P, run as R


def game(i, time, home, team, opp_club="Parley CC", opp_team="1st XI", ground=""):
    us = {"club_name": "Verwood CC", "club_id": "8472", "team_name": team, "team_id": str(500 + i)}
    them = {"club_name": opp_club, "club_id": "1201", "team_name": opp_team, "team_id": str(900 + i)}
    h, a = (us, them) if home else (them, us)
    m = {"id": 1000 + i, "match_date": "08/11/2026", "match_time": time, "ground_name": ground}
    m.update({f"home_{k}": v for k, v in h.items()})
    m.update({f"away_{k}": v for k, v in a.items()})
    return m


class StubPC:
    def __init__(self, games):
        self.games, self.asked = games, []

    def fixtures(self, start, end):
        self.asked.append((start, end))
        return self.games


GAMES = [game(1, "17:45", False, "Indoor A", ground="Dorset Indoor Cricket Centre"),
         game(2, "13:00", True, "Sunday XI"),
         game(3, "18:30", True, "Indoor B"),
         game(4, "10:00", True, "U11"),
         game(5, "10:00", True, "Daughters")]


def setup(club_root, extra=""):
    t = (club_root / "club.yml").read_text()
    t += ("\nmatchday:\n  enabled: true\n  default_home_ground: \"Potterne Park\"\n" + extra)
    t = t.replace("juniors:\n", "juniors:\n  team_pattern: '\\b(U\\s?\\d{1,2}|Daughters|Sons)\\b'\n", 1)
    (club_root / "club.yml").write_text(t)
    return C.load(club_root / "club.yml")


def test_today_story_lists_senior_games_in_time_order(club_root):
    cfg = setup(club_root)
    pc = StubPC(GAMES)
    p = P.matchday_post(cfg, pc, date(2026, 11, 8))
    assert pc.asked == [(date(2026, 11, 8), date(2026, 11, 8))]
    rows = p["data"]["matches"]
    assert [r["team"] for r in rows] == ["Sunday XI", "Indoor A", "Indoor B"]  # juniors out, sorted by time
    venues = {r["team"]: r["venue"] for r in rows}
    assert venues == {"Sunday XI": "Potterne Park", "Indoor A": "Dorset Indoor Cricket Centre", "Indoor B": ""}
    assert p["stories_only"] and p["key"] == "matchday-2026-11-08"
    assert "17:45 · Indoor A v" in p["caption"] and "(A) at Dorset Indoor Cricket Centre" in p["caption"]


def test_home_only_and_no_games(club_root):
    cfg = setup(club_root, "  include: home\n")
    rows = P.matchday_post(cfg, StubPC(GAMES), date(2026, 11, 8))["data"]["matches"]
    assert all(r["home"] for r in rows)
    assert P.matchday_post(cfg, StubPC([GAMES[3]]), date(2026, 11, 8)) is None


def test_made_daily_as_story_only_and_posted_to_stories_only(club_root):
    setup(club_root)
    t = (club_root / "club.yml").read_text().replace("  approval: review", "  approval: automatic")
    (club_root / "club.yml").write_text(t)
    pending = R.cmd_make(Namespace(today="2026-11-08", only="matchday"), root=club_root, pc=StubPC(GAMES),
                         renderer=FakeRenderer())
    (p,) = pending
    assert p["files"] == [] and p["story_files"] == ["posts/2026-11-08/matchday-2026-11-08-story.jpg"]
    gh, m = FakeGitHub(), meta()
    R.cmd_announce(Namespace(sha="abc"), root=club_root, gh=gh, meta=m)
    posted = [c[1] for c in m.http.calls if c[0] == "POST"]
    assert "PAGE1/photo_stories" in posted and "IG1/media_publish" in posted
    assert not any(c[1] == "PAGE1/photos" and c[2].get("message") for c in m.http.calls)  # no feed post
    assert gh.issues[1]["state"] == "closed" and "published" in gh.labels[1]


def test_outdoor_season_only(club_root):
    cfg = setup(club_root, "  months: [4, 5, 6, 7, 8, 9]\n  exclude_teams: '\\bIndoor\\b'\n")
    pc = StubPC(GAMES)
    assert P.matchday_post(cfg, pc, date(2026, 11, 8)) is None and pc.asked == []  # winter: nothing, no lookup
    summer = [dict(g, match_date="09/05/2027") for g in GAMES]
    rows = P.matchday_post(cfg, StubPC(summer), date(2027, 5, 9))["data"]["matches"]
    assert [r["team"] for r in rows] == ["Sunday XI"]  # indoor teams left out
