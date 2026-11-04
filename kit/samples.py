"""Made-up example posts in the club's branding, for the setup check preview."""
from datetime import timedelta

from . import posts as P


def sample_posts(cfg, today):
    s = cfg.short_name
    d = lambda n: today + timedelta(days=n)
    fixtures = {"kind": "fixtures", "title": "This Week's Fixtures", "date_range": P.date_range([today, d(6)]),
                "matches": [
                    {"date": P.short_date(d(1)), "time": "13:00", "team": "1st XI", "opponent": "Example Town CC 1st XI", "home": True},
                    {"date": P.short_date(d(1)), "time": "13:30", "team": "2nd XI", "opponent": "Sample Park CC 2nd XI", "home": False},
                    {"date": P.short_date(d(2)), "time": "10:00", "team": "Under 13", "opponent": "Demo Vale CC Under 13", "home": True},
                ]}
    results = {"kind": "results", "title": "Last Week's Results", "date_range": P.date_range([d(-2), d(-1)]),
               "matches": [
                   {"date": P.short_date(d(-2)), "team": "1st XI", "opponent": "Example Town CC 1st XI", "home": True,
                    "us_score": "212/7 (45.0)", "opp_score": "168 all out (38.2)", "outcome": "W", "summary": "Won by 44 runs"},
                   {"date": P.short_date(d(-2)), "team": "2nd XI", "opponent": "Sample Park CC 2nd XI", "home": False,
                    "us_score": "141/9 (40.0)", "opp_score": "142/3 (31.4)", "outcome": "L", "summary": "Lost by 7 wickets"},
                   {"date": P.short_date(d(-1)), "team": "Under 13", "opponent": "Demo Vale CC Under 13", "home": True,
                    "us_score": "–", "opp_score": "–", "outcome": "A", "summary": "Abandoned"},
               ]}
    match = {"kind": "match", "id": "sample", "date": P.long_date(d(-2)), "team": "1st XI",
             "opponent": "Example Town CC", "opponent_team": "1st XI", "outcome": "W",
             "summary": f"{s} won by 44 runs", "us_score": "212/7", "us_overs": "45.0 overs",
             "opp_score": "168 all out", "opp_overs": "38.2 overs", "toss": f"{s} won the toss and elected to bat",
             "top_batting": [{"name": "A. Batter", "figures": "87", "detail": "96 balls"},
                             {"name": "B. Opener", "figures": "45*", "detail": "51 balls"}],
             "top_bowling": [{"name": "C. Seamer", "figures": "4-31", "detail": "8 overs"},
                             {"name": "D. Spinner", "figures": "3-22", "detail": "9 overs"}]}
    return [
        {"key": "sample-fixtures", "kind": "fixtures", "title": "Sample fixtures", "data": fixtures,
         "caption": P.caption_fixtures(cfg, fixtures), "alt": "Sample fixtures graphic"},
        {"key": "sample-roundup", "kind": "roundup", "title": "Sample results round-up", "data": results,
         "caption": P.caption_roundup(cfg, results), "alt": "Sample results graphic"},
        {"key": "sample-match", "kind": "match", "title": "Sample match result", "data": match,
         "caption": P.caption_match(cfg, match), "alt": "Sample match result graphic"},
    ]
