"""Career milestones: CricketStatz starting totals + Play-Cricket games; softball from Play-Cricket only."""
import csv
from datetime import date

from kit import careers as K, config as C


def bat(name, pid, runs, how="b", fielder="", fid="", bowler="", bid=""):
    return {"batsman_name": name, "batsman_id": pid, "runs": str(runs), "how_out": how,
            "fielder_name": fielder, "fielder_id": fid, "bowler_name": bowler, "bowler_id": bid}


def game(mid, team, ours, bowl, theirs, players=(), day="15/05/2027", result="W"):
    return {"id": mid, "match_date": day, "result": result,
            "home_club_id": "8472", "home_club_name": "Verwood CC", "home_team_name": team, "home_team_id": "T1",
            "away_club_id": "9", "away_club_name": "Opp CC", "away_team_name": "1st XI", "away_team_id": "O1",
            "players": [{"home_team": [{"player_name": n, "player_id": i, "wicket_keeper": k} for n, i, k in players]},
                        {"away_team": []}],
            "innings": [{"team_batting_id": "T1", "bat": ours, "bowl": []},
                        {"team_batting_id": "O1", "bat": theirs,
                         "bowl": [{"bowler_name": n, "bowler_id": i, "wickets": str(w), "runs": "20"} for n, i, w in bowl]}]}


def setup(root, links=()):
    (root / "careers").mkdir()
    with open(root / "careers/baseline.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "last_team", "matches", "runs", "wickets", "catches", "keeper_catches"])
        w.writerow(["Gajic C", "Gajic C", "1st XI", 349, 9480, 10, 49, 0])
        w.writerow(["Hancock L", "Hancock L", "1st XI", 325, 6590, 0, 136, 99])
        w.writerow(["Driscoll J #1", "Driscoll J", "1st XI", 287, 3354, 126, 106, 25])
        w.writerow(["Driscoll J #2", "Driscoll J", "1st XI", 241, 4170, 349, 71, 0])
    with open(root / "careers/links.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["play_cricket", "name", "cricketstatz", "notes"])
        for row in links:
            w.writerow(row)
    (root / "club.yml").write_text((root / "club.yml").read_text() + "\ncareer_milestones:\n  enabled: true\n")
    return C.load(root / "club.yml")


def test_crossings():
    assert K.crossings(480, 530, 500) == [500]
    assert K.crossings(990, 1010, 500) == [1000]
    assert K.crossings(10, 120, 50) == [50, 100]
    assert K.crossings(500, 500, 500) == []


def test_names_match_between_sites():
    assert K.cs_key("Gajic C") == K.pc_key("Charlie Gajic") == "gajic|c"
    assert K.cs_key("McLeonards S") == K.pc_key("Scott McLeonards")
    assert K.cs_key("Stainer-Reid T") == K.pc_key("Tom Stainer-Reid")


def test_club_milestones_from_starting_totals(club_root):
    cfg = setup(club_root)
    car = K.Careers(cfg, club_root)
    g = game(1, "1st XI", [bat("Charlie Gajic", "47", 25), bat("Luke Hancock", "70", 3)],
             [("Charlie Gajic", "47", 1)],
             [bat("X", "", 0, "ct", "Luke Hancock", "70"), bat("Y", "", 0, "ct", "Charlie Gajic", "47")],
             players=[("Charlie Gajic", "47", False), ("Luke Hancock", "70", True)])
    events = car.add_match(g)
    got = sorted((e["name"], e["stat"], e["value"]) for e in events)
    assert got == [("Charlie Gajic", "catches", 50), ("Charlie Gajic", "matches", 350),
                   ("Charlie Gajic", "runs", 9500), ("Luke Hancock", "keeper_catches", 100)]
    assert car.add_match(g) == []  # never counted twice
    posts = K.career_posts(cfg, events)
    runs = next(p for p in posts if p["data"]["type"] == "runs")
    assert runs["data"]["figures"] == "9,500" and "Charlie Gajic" in runs["caption"] and "9,500 career runs" in runs["caption"]
    cfg["career_milestones"]["names"] = "initial"
    assert "Charlie G." in K.career_posts(cfg, events)[0]["caption"]


def test_shared_names_wait_for_a_link(club_root):
    cfg = setup(club_root)
    car = K.Careers(cfg, club_root)
    g = game(2, "1st XI", [bat("Jack Driscoll", "67", 10)], [("Jack Driscoll", "67", 0)], [])
    assert car.add_match(g) == []  # Driscoll J #1 or #2? Not announced
    assert car.needs_linking()[0]["could_be"] == ["Driscoll J #1", "Driscoll J #2"]
    (club_root / "careers/links.csv").write_text("play_cricket,name,cricketstatz,notes\n67,Jack Driscoll,Driscoll J #2,\n")
    car2 = K.Careers(cfg, club_root)
    car2.state = car.state
    ev = car2.add_match(game(3, "1st XI", [], [("Jack Driscoll", "67", 1)], []))
    assert [(e["stat"], e["value"]) for e in ev] == [("wickets", 350)]  # Driscoll J #2's 349 + 1


def test_softball_is_play_cricket_only_and_indoor_ignored(club_root):
    cfg = setup(club_root)
    car = K.Careers(cfg, club_root)
    assert K.pool_for(cfg, "Women's Softball") == "softball"
    assert K.pool_for(cfg, "Women's Softball Indoor B") is None
    assert K.pool_for(cfg, "Indoor A") is None and K.pool_for(cfg, "Under 13 A") is None
    for i in range(10):
        ev = car.add_match(game(100 + i, "Women's Softball", [bat("Clare Cook", "5", 50)], [], []), announce=(i == 9))
    assert [(e["pool"], e["stat"], e["value"]) for e in ev] == [("softball", "runs", 500)]


def test_new_games_only_counts_summer_after_baseline(club_root):
    cfg = setup(club_root)
    car = K.Careers(cfg, club_root)
    games = [game(10, "1st XI", [bat("Charlie Gajic", "47", 30)], [], [], day="20/05/2027"),
             game(11, "1st XI", [bat("Charlie Gajic", "47", 30)], [], [], day="20/11/2027")]

    class PC:
        def results(self, a, b):
            assert a == date(2027, 1, 1)
            return games

        def match_detail(self, mid):
            return next(g for g in games if g["id"] == mid)

    ev = K.new_games(cfg, PC(), date(2027, 5, 21), car)
    assert sorted((e["stat"], e["value"]) for e in ev) == [("matches", 350), ("runs", 9500)]
    assert "11" not in car.state["counted"]  # November: not an outdoor summer game


def test_juniors_get_full_name_but_never_their_photo(club_root, tmp_path):
    from kit.milestones import PhotoStore
    cfg = setup(club_root)
    (tmp_path / "juniors").mkdir()
    (tmp_path / "juniors" / "Charlie Gajic.jpg").write_bytes(b"x")
    car = K.Careers(cfg, club_root)
    ev = car.add_match(game(5, "1st XI", [bat("Charlie Gajic", "47", 25)], [], []))
    post = K.career_posts(cfg, ev, photos=PhotoStore(tmp_path))[0]
    assert "Charlie Gajic" in post["caption"] and not post["data"]["photo_path"]


def test_one_player_split_across_two_records(club_root):
    cfg = setup(club_root, links=[("67", "", "Driscoll J #1+Driscoll J #2", "")])
    car = K.Careers(cfg, club_root)
    rec = {"pid": "67", "key": "driscoll|j", **{s: 0 for s in K.STATS}}
    totals, ok = car.career("club", rec)
    assert ok and totals["runs"] == 3354 + 4170 and totals["matches"] == 287 + 241


def test_milestone_watch(club_root):
    cfg = setup(club_root)
    car = K.Careers(cfg, club_root)
    car.add_match(game(20, "1st XI", [bat("Charlie Gajic", "47", 0)], [], [], players=[("Charlie Gajic", "47", False)],
                       day="01/05/2027"))
    # Charlie: 9480 runs, 350 matches (349 + 1), 49 catches -> 20 runs and 1 catch away
    fixtures = [{"team": "1st XI", "opponent": "Opp CC 1st XI", "date": "Sat 8 May", "time": "13:00", "home": True,
                 "date_obj": date(2027, 5, 8)},
                {"team": "Indoor A", "opponent": "X", "date": "Sun 9 May", "time": "18:00", "home": False,
                 "date_obj": date(2027, 5, 9)}]
    w = K.watch_list(cfg, car, fixtures, date(2027, 5, 7))
    assert [(x["name"], x["stat"], x["needs"], x["target"]) for x in w] == [
        ("Charlie Gajic", "runs", 20, 9500), ("Charlie Gajic", "catches", 1, 50)]
    post = K.watch_post(cfg, car, fixtures, date(2027, 5, 7), "8 – 14 May")
    assert "Charlie Gajic (1st XI) needs 20 runs for 9,500 career runs" in post["caption"]
    assert K.watch_list(cfg, car, fixtures, date(2027, 6, 30)) == []  # not played for weeks: left out
    assert K.need_text({"stat": "matches", "needs": 1, "target": 100, "pool": "club"}) == "next game is their 100th appearance"
