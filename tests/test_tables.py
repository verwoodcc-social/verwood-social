"""Monthly league tables from Play-Cricket."""
from datetime import date

from kit import config as C, tables as T

HEAD = {"column_1": "Team", "column_2": "p", "column_3": "w", "column_4": "l", "column_5": "t", "column_13": "Pts"}


def row(pos, tid, team, p, w, l, pts):
    return {"position": str(pos), "team_id": str(tid), "column_1": team, "column_2": str(p), "column_3": str(w),
            "column_4": str(l), "column_5": "0", "column_13": str(pts)}


class PC:
    def season_matches(self, season):
        base = {"home_club_id": "8472", "home_club_name": "Verwood CC", "away_club_id": "9", "away_club_name": "X",
                "away_team_name": "1st XI", "away_team_id": "9"}
        return [
            {**base, "competition_type": "League", "competition_id": 1, "league_name": "Hampshire Cricket League",
             "competition_name": "Division 2A", "home_team_name": "1st XI", "home_team_id": "501"},
            {**base, "competition_type": "Cup", "competition_id": 2, "league_name": "Hampshire Cricket League",
             "competition_name": "Cup", "home_team_name": "1st XI", "home_team_id": "501"},
            {**base, "competition_type": "League", "competition_id": 3, "league_name": "Dorset Indoor League",
             "competition_name": "Women's Softball Div 2", "home_team_name": "Women's Softball", "home_team_id": "777"},
            {**base, "competition_type": "League", "competition_id": 4, "league_name": "Dorset Junior Club Competitions",
             "competition_name": "U13", "home_team_name": "Under 13 A", "home_team_id": "888"},
            {**base, "competition_type": "League", "competition_id": 5, "league_name": "Wimborne Evening League",
             "competition_name": "Division 1", "home_team_name": "Wednesday 1st XI", "home_team_id": "601"},
        ]

    def league_table(self, did):
        if did == "1":
            return {"name": "Division 2A", "headings": HEAD, "values": [
                row(1, 29325, "South Wilts CC - 2nd XI", 18, 14, 1, 338),
                row(2, 106575, "Winton CC, Dorset - 1st XI", 18, 12, 2, 282),
                row(3, 501, "Verwood CC - 1st XI", 18, 9, 6, 250)]}
        return {"name": "Division 1", "headings": HEAD, "values": [row(1, 601, "Verwood CC", 0, 0, 0, 0)]}


def test_due_last_day_of_season_months(club_root):
    (club_root / "club.yml").write_text((club_root / "club.yml").read_text() + "\nleague_tables:\n  enabled: true\n")
    cfg = C.load(club_root / "club.yml")
    assert T.due(cfg, date(2027, 6, 30)) and T.due(cfg, date(2027, 9, 30))
    assert not T.due(cfg, date(2027, 6, 29)) and not T.due(cfg, date(2027, 10, 31))


def test_tables_post(club_root):
    cfg = C.load(club_root / "club.yml")
    divs = T.divisions(cfg, PC(), 2027)
    assert set(divs) == {"1", "5"}  # no cups, indoor leagues or juniors
    p = T.tables_post(cfg, PC(), date(2027, 6, 30))
    (b,) = p["data"]["boards"]  # Wednesday side hasn't played yet: left out
    assert b["title"] == "1st XI" and b["columns"] == ["P", "W", "L", "Pts"]
    assert [r["team"] for r in b["rows"]] == ["South Wilts 2nd XI", "Winton 1st XI", "Verwood 1st XI"]
    assert b["rows"][2]["ours"] and b["rows"][2]["cells"] == ["18", "9", "6", "250"]
    assert "1st XI: 3rd of 3 in Division 2A" in p["caption"]
