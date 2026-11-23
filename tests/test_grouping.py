from datetime import date

from kit import grouping as G


def card(i, team, outcome="W", day=date(2026, 11, 21)):
    return {"kind": "match", "id": str(i), "team": team, "opponent": "Poole CC", "opponent_team": "1st XI",
            "outcome": outcome, "summary": "Verwood won by 6 wickets", "us_score": "150/4", "opp_score": "149",
            "date_obj": day, "date": "Saturday 21 November 2026", "home": True}


def post(c, report=None):
    p = {"key": f"match-{c['id']}", "kind": "match", "title": c["team"], "data": c, "caption": "x"}
    if report:
        p.update(report=report, report_issue=99)
    return p


def test_groups_three_or_more_same_day(verwood):
    verwood["group_results"].update(enabled=True, min_matches=3)
    made = [post(card(1, "1st XI"), {"captain": "Sam", "text": "Great game. We won. Then more. And more.", "potm": "Jo B."}),
            post(card(2, "2nd XI", "L")), post(card(3, "3rd XI")),
            post(card(4, "4th XI", day=date(2026, 11, 22))),
            {"key": "milestone-1", "kind": "milestone", "data": {}, "caption": "m"}]
    out = G.group(verwood, made)
    keys = [p["key"] for p in out]
    assert "milestone-1" in keys and "match-4" in keys                     # milestone separate; Sunday alone
    g = next(p for p in out if p["kind"] == "results_day")
    assert g["also_keys"] == ["match-1", "match-2", "match-3"] and g["report_issues"] == [99]
    assert "Saturday's results" in g["caption"] and "“Great game. We won.”" in g["caption"]
    assert len(g["data"]["cards"]) == 3 and g["title"].startswith("Saturday's results: 3 games, 2 won")


def test_busy_day_split_and_two_left_alone(verwood):
    verwood["group_results"].update(enabled=True, min_matches=3)
    out = G.group(verwood, [post(card(i, f"Team {i:02d}")) for i in range(10)])
    assert [len(p["data"]["cards"]) for p in out] == [8, 2] and "(1 of 2)" in out[0]["caption"]
    two = [post(card(1, "1st XI")), post(card(2, "2nd XI"))]
    assert G.group(verwood, two) == two
