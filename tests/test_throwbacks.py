from datetime import date

from kit import posts as P
from kit import throwbacks as T


def card(**kw):
    c = {"outcome": "W", "summary": "Verwood won by 6 wickets", "us_score": "180-4", "all_batting": [],
         "all_bowling": [], "top_batting": [], "top_bowling": [], "show_names": True, "team": "1st XI"}
    c.update(kw)
    return c


def test_best_moment():
    assert T.best_moment(card()) == (0, "")
    assert T.best_moment(card(all_batting=[{"runs": 112}]))[1] == "century"
    assert T.best_moment(card(all_bowling=[{"w": 6, "r": 20}]))[1] == "five-for"
    assert T.best_moment(card(summary="Verwood won by 2 runs"))[1] == "thriller"
    assert T.best_moment(card(summary="Verwood won by 10 wickets"))[1] == "ten-wicket win"
    assert T.best_moment(card(outcome="T", summary="Match tied"))[1] == "tie"
    assert T.best_moment(card(us_score="312-6", summary="Verwood won by 40 runs"))[1] == "big total"
    # a century beats a ten-wicket win
    assert T.best_moment(card(all_batting=[{"runs": 101}], summary="Verwood won by 10 wickets"))[1] == "century"


def test_pick_varies_team_and_season(verwood):
    data = {"used": {"1": "2026-11-05"}, "checked": [], "moments": [
        {"id": "1", "date": "2019-06-01", "team": "1st XI", "score": 150, "why": "century"},
        {"id": "2", "date": "2019-07-01", "team": "2nd XI", "score": 140, "why": "century"},
        {"id": "3", "date": "2021-07-01", "team": "1st XI", "score": 130, "why": "century"},
        {"id": "4", "date": "2022-07-01", "team": "3rd XI", "score": 90, "why": "five-for"}]}
    assert T.pick(verwood, data, date(2026, 11, 12))["id"] == "4"   # 2 is the same season, 3 the same team
    data["moments"] = data["moments"][:3]
    assert T.pick(verwood, data, date(2026, 11, 12))["id"] == "2"   # nothing else: rules relaxed


def test_due(verwood):
    verwood["throwback"]["enabled"] = True
    assert T.due(verwood, date(2026, 11, 12))           # a Thursday in November
    assert not T.due(verwood, date(2026, 11, 13))
    assert not T.due(verwood, date(2026, 7, 2))         # summer


def test_build_and_post(verwood, pc, tmp_path):
    verwood["throwback"].update(enabled=True, first_season=2026)
    looked, added = T.build(verwood, pc, tmp_path, date(2026, 11, 12), pause=0)
    data = T.load(tmp_path)
    assert looked >= 1 and set(data["checked"])
    assert "7700003" in data["checked"]   # abandoned: checked without reading the scorecard
    # one archive game, to make a post from
    data["moments"] = [{"id": "7700001", "date": "2026-10-26", "team": "1st XI", "score": 100, "why": "thriller"}]
    T.save(tmp_path, data)
    p = T.throwback_post(verwood, pc, tmp_path, date(2026, 11, 12))
    assert p["key"] == "throwback-7700001" and p["kind"] == "throwback"
    assert p["data"]["throwback"]["verdict"] == "Thriller" and "#ThrowbackThursday" in p["caption"]
    assert T.load(tmp_path)["used"]["7700001"] == "2026-11-12"
    assert T.throwback_post(verwood, pc, tmp_path, date(2026, 11, 12)) is None   # once a day
