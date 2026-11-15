from datetime import date

from kit import debuts as D
from kit import posts as P


def detail(mid, d, team, ids):
    """A small scorecard: our side is home; players given as (id, name, runs)."""
    return {"id": mid, "match_date": d, "home_club_id": "8472", "home_club_name": "Verwood CC",
            "home_team_name": team, "home_team_id": "1", "away_club_id": "9", "away_club_name": "Poole CC",
            "away_team_name": "1st XI", "away_team_id": "2", "result": "W", "result_applied_to": "1",
            "batted_first": "1", "no_of_innings": "1",
            "innings": [{"team_batting_id": "1", "runs": "150", "wickets": "5", "overs": "40",
                         "bat": [{"batsman_name": n, "batsman_id": i, "how_out": "b", "runs": str(r), "balls": "30"}
                                 for i, n, r in ids], "bowl": []},
                        {"team_batting_id": "2", "runs": "120", "wickets": "10", "overs": "38",
                         "bat": [], "bowl": []}]}


def test_club_and_adult_debuts(verwood, club_root):
    verwood["debuts"].update(enabled=True)
    data = D.load(club_root)
    # history: Jo has played for the U15s, Sam for the 1st XI already
    D.record(verwood, data, detail(1, "10/07/2025", "Under 15", [("11", "Jo Bloggs", 5)]))
    D.record(verwood, data, detail(2, "12/07/2025", "1st XI", [("22", "Sam Smith", 40)]))
    data["built"] = True
    det = detail(3, "16/05/2026", "2nd XI", [("11", "Jo Bloggs", 23), ("22", "Sam Smith", 50), ("33", "Kim New", 7)])
    card = P.match_card(verwood, det)
    posts = D.debut_posts(verwood, club_root, data, det, card)
    by = {p["key"]: p for p in posts}
    assert set(by) == {"debut-11", "debut-33"}                     # Sam has played adult cricket before
    assert by["debut-11"]["data"]["label"] == "Adult debut" and "From our juniors" in by["debut-11"]["caption"]
    assert by["debut-33"]["data"]["label"] == "Club debut" and "23" not in by["debut-33"]["caption"]
    assert by["debut-11"]["data"]["detail"] == "23 on debut"
    # remade on a later run the same morning: same posts
    assert {p["key"] for p in D.debut_posts(verwood, club_root, data, det, card)} == {"debut-11", "debut-33"}
    # next week: no longer a debut
    det2 = detail(4, "23/05/2026", "2nd XI", [("33", "Kim New", 12)])
    assert D.debut_posts(verwood, club_root, data, det2, P.match_card(verwood, det2)) == []


def test_no_posts_until_history_built_and_none_for_junior_games(verwood, club_root):
    verwood["debuts"].update(enabled=True)
    data = D.load(club_root)
    det = detail(5, "16/05/2026", "1st XI", [("44", "New Person", 3)])
    assert D.debut_posts(verwood, club_root, data, det, P.match_card(verwood, det)) == []   # not built yet
    data["built"] = True
    det = detail(6, "17/05/2026", "Under 11", [("55", "Little One", 3)])
    assert D.debut_posts(verwood, club_root, data, det, P.match_card(verwood, det)) == []   # junior game
