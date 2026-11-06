"""Season leaderboards: runs, wickets and catches for adult teams, season to date."""
import json
from argparse import Namespace
from datetime import date

from test_meta_review_run import FakeRenderer
from kit import config as C, leaderboards as L, run as R


def bat(name, pid, runs, how="b", fielder="", fid="", bowler="", bid=""):
    return {"batsman_name": name, "batsman_id": pid, "runs": str(runs), "how_out": how, "balls": "10",
            "fielder_name": fielder, "fielder_id": fid, "bowler_name": bowler, "bowler_id": bid}


def bowl(name, pid, w, r):
    return {"bowler_name": name, "bowler_id": pid, "wickets": str(w), "runs": str(r), "overs": "6.0"}


def match(mid, team, our_bat, our_bowl, their_bat, result="W", day="10/05/2027"):
    return {"id": mid, "match_date": day, "result": result, "status": "New",
            "home_club_id": "8472", "home_club_name": "Verwood CC", "home_team_name": team, "home_team_id": f"T{team}",
            "away_club_id": "1", "away_club_name": "Opp CC", "away_team_name": "1st XI", "away_team_id": "O1",
            "innings": [{"team_batting_id": f"T{team}", "bat": our_bat, "bowl": []},
                        {"team_batting_id": "O1", "bat": their_bat, "bowl": our_bowl}]}


MATCHES = [
    match(1, "1st XI", [bat("Ben Taylor", "11", 87, "not out"), bat("Sam Cole", "12", 20)],
          [bowl("Joe Wild", "13", 4, 30), bowl("Sam Cole", "12", 1, 20)],
          [bat("X", "", 0, "ct", "Ben Taylor", "11"), bat("Y", "", 3, "c & b", bowler="Joe Wild", bid="13"),
           bat("Z", "", 1, "st", "Sam Cole", "12")]),
    match(2, "1st XI", [bat("Ben Taylor", "11", 40), bat("Sam Cole", "12", 55)], [bowl("Joe Wild", "13", 2, 10)],
          [bat("X", "", 0, "ct", "Ben Taylor", "11")]),
    match(3, "2nd XI", [bat("Amy Ross", "21", 30)], [bowl("Amy Ross", "21", 5, 12)], []),
    match(4, "Indoor A", [bat("Ben Taylor", "11", 99)], [], []),          # indoor: left out
    match(5, "Under 13 A", [bat("Kid One", "31", 50)], [], []),          # junior: left out
    match(6, "1st XI", [], [], [], result="A"),                           # abandoned
]


class PC:
    def __init__(self):
        self.detail_calls = []

    def results(self, start, end):
        self.range = (start, end)
        return MATCHES

    def match_detail(self, mid):
        self.detail_calls.append(mid)
        return next(m for m in MATCHES if str(m["id"]) == str(mid))


def setup(root, extra=""):
    (root / "club.yml").write_text((root / "club.yml").read_text() +
                                   "\nleaderboards:\n  enabled: true\n  min_matches: 1\n" + extra)
    return C.load(root / "club.yml")


def test_boards_club_wide_then_each_team(club_root):
    cfg = setup(club_root)
    pc = PC()
    p = L.leaderboards_post(cfg, pc, date(2027, 6, 7), club_root)
    assert pc.range == (date(2027, 4, 1), date(2027, 6, 6))
    club, *teams = p["data"]["boards"]
    assert club["title"] == "All adult teams" and club["matches"] == 3
    assert [(x["name"], x["value"]) for x in club["bat"]] == [("Ben T.", 127), ("Sam C.", 75), ("Amy R.", 30)]
    assert club["bat"][0]["detail"] == "2 inns · HS 87*"
    assert [(x["name"], x["value"], x["detail"]) for x in club["bowl"]][:2] == [("Joe W.", 6, "Best 4-30"), ("Amy R.", 5, "Best 5-12")]
    assert {x["name"]: x["detail"] for x in club["field"]} == {"Ben T.": "2 ct", "Joe W.": "1 ct", "Sam C.": "1 st"}
    assert [t["title"] for t in teams] == ["1st XI", "2nd XI"]
    assert "Most runs: Ben T. (127)" in p["caption"] and "Swipe" in p["caption"]


def test_cache_means_scorecards_are_read_once(club_root):
    cfg = setup(club_root)
    pc = PC()
    L.leaderboards_post(cfg, pc, date(2027, 6, 7), club_root)
    first = list(pc.detail_calls)
    L.leaderboards_post(cfg, pc, date(2027, 7, 5), club_root)
    assert sorted(first) == ["1", "2", "3"] and pc.detail_calls == first
    assert set(json.loads((club_root / L.CACHE).read_text())) == {"1", "2", "3"}


def test_min_matches_and_schedule(club_root):
    cfg = setup(club_root, "  months: [5, 6, 7, 8, 9, 10]\n")
    cfg2 = C.load(club_root / "club.yml")
    cfg2["leaderboards"]["min_matches"] = 2
    p = L.leaderboards_post(cfg2, PC(), date(2027, 6, 7), club_root)
    assert [b["title"] for b in p["data"]["boards"]] == ["All adult teams", "1st XI"]
    assert L.due(cfg, date(2027, 6, 7))          # first Monday of June
    assert not L.due(cfg, date(2027, 6, 14))     # second Monday
    assert not L.due(cfg, date(2026, 11, 2))     # winter


def test_made_as_one_carousel(club_root):
    setup(club_root)
    (p,) = R.cmd_make(Namespace(today="2027-06-08", only="leaderboards"), root=club_root, pc=PC(),
                      renderer=FakeRenderer())
    assert p["kind"] == "leaderboards" and p["files"]
