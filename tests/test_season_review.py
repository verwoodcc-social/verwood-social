"""End-of-season review carousel."""
from datetime import date

from test_leaderboards import PC as LBPC, MATCHES
from test_tables import PC as TPC
from kit import config as C, review_season as SR


class PC(LBPC, TPC):
    def results(self, start, end):
        return [dict(m, result_applied_to=m["home_team_id"] if m["result"] == "W" else "") for m in MATCHES]


def test_season_review(club_root):
    (club_root / "club.yml").write_text((club_root / "club.yml").read_text() + "\nseason_review:\n  enabled: true\n")
    cfg = C.load(club_root / "club.yml")
    assert SR.due(cfg, date(2027, 10, 4)) and not SR.due(cfg, date(2027, 10, 11))
    p = SR.season_post(cfg, PC(), date(2027, 10, 4), club_root)
    kinds = [s["type"] for s in p["data"]["slides"]]
    assert kinds[0] == "summary" and "team" in kinds
    summary = p["data"]["slides"][0]["rows"]
    assert {r["team"] for r in summary} == {"1st XI"}  # indoor, junior and one-off (2nd XI: 1 game) left out
    first = next(s for s in p["data"]["slides"] if s["type"] == "team" and s["title"] == "1st XI")
    assert first["bat"][0]["name"] == "Ben T." and first["record"]["P"] == 3
    assert "1st XI: played 3" in p["caption"]
