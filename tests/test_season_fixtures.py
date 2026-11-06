"""Season fixture lists, spread across the first week of April."""
from datetime import date, timedelta

from kit import config as C, season_fixtures as SF


def fx(i, team, d, home=True, league="Dorset Cricket League"):
    us = {"club_name": "Verwood CC", "club_id": "8472", "team_name": team}
    them = {"club_name": "Opp CC", "club_id": "1", "team_name": "1st XI"}
    h, a = (us, them) if home else (them, us)
    m = {"id": i, "match_date": d.strftime("%d/%m/%Y"), "match_time": "13:00", "league_name": league}
    m.update({f"home_{k}": v for k, v in h.items()})
    m.update({f"away_{k}": v for k, v in a.items()})
    return m


TEAMS = ["1st XI", "2nd XI", "3rd XI", "4th XI", "Wednesday 1st XI", "Women's Softball", "Under 15 A",
         "Under 13 A", "Under 11", "Girls Under 11 A", "Under 9", "Indoor A"]


class PC:
    def fixtures(self, a, b):
        out, i = [], 0
        for t in TEAMS:
            for w in range(6):
                i += 1
                out.append(fx(i, t, date(2027, 4, 17) + timedelta(days=7 * w), home=w % 2 == 0))
        return out


def cfg(root):
    (root / "club.yml").write_text((root / "club.yml").read_text() + "\nseason_fixtures:\n  enabled: true\n")
    return C.load(root / "club.yml")


def test_spread_over_the_week_each_team_once(club_root):
    c = cfg(club_root)
    state, seen = {}, []
    for day in range(1, 8):
        today = date(2027, 4, day)
        assert SF.due(c, today)
        posts = SF.season_fixture_posts(c, PC(), today, state)
        assert 1 <= len(posts) <= 2
        seen += [p["data"]["title"] for p in posts]
    assert not SF.due(c, date(2027, 4, 8))
    assert sorted(seen) == sorted(t for t in TEAMS if t != "Indoor A") and len(seen) == len(set(seen))
    assert seen[0] == "1st XI" and seen[-1] in ("Under 9", "Girls Under 11 A")  # seniors first, then oldest juniors


def test_post_contents(club_root):
    c = cfg(club_root)
    (p, *_) = SF.season_fixture_posts(c, PC(), date(2027, 4, 1), {})
    assert p["data"]["sub"] == "2027 fixtures · 6 games" and "6 games, 3 at home" in p["caption"]
    assert "First up: Sat 17 Apr v Opp CC 1st XI (home)" in p["caption"]
