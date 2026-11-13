from datetime import date

from kit import awards as A


def test_windows():
    assert A.week_window(date(2026, 11, 3)) == (date(2026, 10, 26), date(2026, 11, 1))
    assert A.month_window(date(2026, 11, 1)) == (date(2026, 10, 1), date(2026, 10, 31))
    assert A.month_window(date(2027, 1, 1)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_due(verwood):
    verwood["awards"].update(enabled=True, months=[4, 5, 6, 7, 8, 9])
    assert A.due(verwood, date(2027, 6, 15)) == ["week"]               # a Tuesday in June
    assert A.due(verwood, date(2027, 6, 1)) == ["week", "month"]       # Tuesday 1 June: both
    assert A.due(verwood, date(2027, 10, 1)) == ["month"]              # September's award
    assert A.due(verwood, date(2027, 11, 2)) == []                     # winter


def test_player_of_the_week_from_scorecards(verwood, pc):
    verwood["awards"].update(enabled=True, months=list(range(1, 13)))
    p = A.award_post(verwood, pc, date(2026, 11, 3), "week")
    d = p["data"]
    # Alex: 87* (87 + 15 for the fifty) + 4 wickets (80) + 5 for the win = 187
    assert d["name"] == "Alex A." and d["points"] == 187 and d["team"] == "1st XI"
    assert d["bits"][0].startswith("87* v") and any(b.startswith("4-31") for b in d["bits"])
    assert p["key"] == "award-week-2026-10-26" and "Player of the Week: Alex A." in p["caption"]
    verwood["awards"]["min_points"] = 500
    assert A.award_post(verwood, pc, date(2026, 11, 3), "week") is None


def test_pairs_cricket_wickets_count_less(verwood):
    import re
    assert re.search(verwood["awards"]["low_wicket_teams"], "Under 9 Indoor")
    assert not re.search(verwood["awards"]["low_wicket_teams"], "U13 Indoor")


def test_awards_review_posts_nothing(club_root, pc, capsys):
    from types import SimpleNamespace
    from kit.run import cmd_awards_review
    y = (club_root / "club.yml").read_text() + "\nawards:\n  enabled: true\n  months: [10]\n"
    (club_root / "club.yml").write_text(y)
    assert cmd_awards_review(SimpleNamespace(season="2026"), club_root, pc=pc)
    out = capsys.readouterr().out
    assert "Alex A." in out and "| October | Alex A." in out
