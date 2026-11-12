from datetime import date

from kit import countdown as CD


def fx(mid, d, team, opp, home=True, time="13:00"):
    us = {"club_id": "8472", "team_name": team, "club_name": "Verwood CC", "team_id": "1"}
    them = {"club_id": "999", "team_name": "1st XI", "club_name": opp, "team_id": "2"}
    a, b = (us, them) if home else (them, us)
    m = {"id": mid, "match_date": d, "match_time": time, "ground_name": ""}
    for side, t in (("home", a), ("away", b)):
        for k, v in t.items():
            m[f"{side}_{k}"] = v
    return m


class PC:
    def __init__(self, matches):
        self.matches = matches

    def fixtures(self, a, b):
        return self.matches


def test_counts_down_to_first_outdoor_senior_day(verwood):
    verwood["countdown"]["enabled"] = True
    pc = PC([fx(1, "18/04/2027", "1st XI", "Poole CC"), fx(2, "18/04/2027", "2nd XI", "Wimborne CC", home=False),
             fx(3, "14/03/2027", "Indoor A", "Parley CC"), fx(4, "10/04/2027", "Under 13", "Lions CC")])
    p = CD.countdown_post(verwood, pc, date(2027, 3, 28))   # 21 days before
    assert p["key"] == "countdown-2027-04-18-21" and p["data"]["days"] == 21
    assert [r["team"] for r in p["data"]["matches"]] == ["1st XI", "2nd XI"]   # indoor and youth left out
    assert "21 days to go until the 2027 season" in p["caption"]
    assert CD.countdown_post(verwood, pc, date(2027, 3, 29)) is None            # 20 days: not a countdown day
    assert CD.countdown_post(verwood, pc, date(2027, 4, 17))["data"]["words"] == "DAY TO GO"
    assert CD.countdown_post(verwood, PC([]), date(2027, 3, 28)) is None         # no fixtures yet


def test_due(verwood):
    verwood["countdown"]["enabled"] = True
    assert CD.due(verwood, date(2027, 3, 1)) and not CD.due(verwood, date(2027, 1, 5))
