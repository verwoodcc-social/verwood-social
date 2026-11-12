from datetime import date

import pytest

from conftest import ROOT
from kit import config as C
from kit import posts as P


@pytest.mark.skipif("YOUR" not in (ROOT / "club.yml").read_text(), reason="club.yml is filled in (club copy)")
def test_template_config_refuses_placeholders():
    with pytest.raises(C.ConfigError) as e:
        C.load(ROOT / "club.yml")
    msg = str(e.value)
    assert "club → name" in msg and "play_cricket_site_id" in msg


def test_verwood_example_loads(verwood):
    assert verwood.site_id == 8472 and verwood.short_name == "Verwood"
    assert verwood.is_junior("Girls U13 Indoor") and verwood.is_junior("Under 9 Indoor")
    assert not verwood.is_junior("Indoor C") and not verwood.is_junior("1st XI")


def test_light_club_colours_are_darkened_for_readable_text():
    pal = C.make_palette("#F7D417", "#FFFFFF")  # bright yellow
    assert C.luminance(pal["navy"]) <= 0.09
    assert C.contrast(pal["silver"], pal["navy-deep"]) >= 4.5
    pal2 = C.make_palette("#1A4192", "#1A4192")  # accent same as primary: unreadable, replaced
    assert pal2["silver"] == "#F2F4F7"
    pal3 = C.make_palette("#F2B705", "#0B6E4F")  # gold + green: green background, gold highlight
    r, g, b = (int(pal3["navy"][i:i + 2], 16) for i in (1, 3, 5))
    assert g > r and g > b and pal3["silver"] == "#F2B705"  # stays green, gold kept as the highlight


def test_fixtures_next_seven_days(verwood, pc):
    post = P.fixtures_post(verwood, pc, date(2026, 10, 29))  # Thursday
    rows = post["data"]["matches"]
    assert [r["team"] for r in rows] == ["Indoor D", "U13 Indoor", "Under 9 Indoor", "Indoor E",
                                         "Women's Softball Indoor B", "Women's Softball"]
    assert rows[0]["opponent"] == "Seaside CC Indoor E" and rows[0]["home"] is False
    assert rows[2]["home"] is True and rows[2]["date"] == "Sat 31 Oct" and rows[2]["time"] == "14:25"
    assert "Thu 29 Oct 19:15 · Indoor D v Seaside CC Indoor E (A)" in post["caption"]
    assert post["data"]["date_range"] == "29 Oct – 4 Nov 2026"


def test_roundup_outcomes_and_margins(verwood, pc):
    post = P.roundup_post(verwood, pc, date(2026, 10, 26))  # Monday: covers 19–25 Oct
    by_team = {r["team"]: r for r in post["data"]["matches"]}
    assert set(by_team) == {"Indoor C", "Girls U13 Indoor", "U10 A Indoor"}
    c = by_team["Indoor C"]
    assert (c["outcome"], c["summary"]) == ("W", "Won")  # indoor: no wicket margin claimed
    assert c["us_score"] == "141/2 (11.3)" and c["opp_score"] == "140/4 (12.0)" and c["home"]
    g = by_team["Girls U13 Indoor"]
    assert (g["outcome"], g["summary"]) == ("L", "Lost by 70 runs")
    u = by_team["U10 A Indoor"]
    assert (u["outcome"], u["summary"]) == ("P", "Result to follow")


def test_outdoor_margins(verwood, pc):
    post = P.roundup_post(verwood, pc, date(2026, 11, 2))  # covers 26 Oct – 1 Nov
    by_team = {r["team"]: r for r in post["data"]["matches"]}
    assert by_team["1st XI"]["summary"] == "Won by 7 wickets"
    assert by_team["1st XI"]["opp_score"] == "168 all out (38.2)"
    assert by_team["2nd XI"]["summary"] == "Lost by 44 runs"
    assert by_team["3rd XI"]["outcome"] == "A" and by_team["3rd XI"]["us_score"] == "–"


def test_match_card_from_scorecard(verwood, pc):
    card = P.match_card(verwood, pc.match_detail(7758947))
    assert card["summary"] == "Verwood won" and card["us_score"] == "141/2" and card["us_overs"] == "11.3 overs"
    # Indoor C is an adult side, but names are shortened for every team by default
    assert [(p["name"], p["figures"]) for p in card["top_batting"]] == [
        ("Alex A.", "29*"), ("Sam B.", "27*"), ("Jo C.", "26*")]
    assert [(p["name"], p["figures"]) for p in card["top_bowling"]] == [("Jo C.", "1-30")]
    assert card["toss"] == "Verwood won the toss and elected to field"
    assert "Alex Archer" not in P.caption_match(verwood, card)


def test_full_names_for_adult_teams_only_if_club_switches_it_off(verwood, pc):
    verwood["juniors"]["apply_to_all_teams"] = False
    card = P.match_card(verwood, pc.match_detail(7758947))  # Indoor C: adult team
    assert card["top_batting"][0]["name"] == "Alex Archer"
    verwood["juniors"]["team_pattern"] = r"Indoor C"  # but junior teams are still shortened
    assert P.match_card(verwood, pc.match_detail(7758947))["top_batting"][0]["name"] == "Alex A."


def test_new_setting_defaults_to_shortening_everyone(tmp_path):
    from conftest import ROOT
    import shutil
    shutil.copy(ROOT / "examples/verwood/badge.svg", tmp_path / "badge.svg")
    text = (ROOT / "examples/verwood/club.yml").read_text().replace("  apply_to_all_teams: true\n", "")
    (tmp_path / "club.yml").write_text(text)  # an older club.yml without the setting
    assert C.load(tmp_path / "club.yml").shorten_names("1st XI") is True


def test_no_scorecard_means_no_match_post(verwood, pc):
    assert P.match_card(verwood, pc.match_detail(7759960)) is None


def test_daily_match_posts_yesterday_only_and_no_repeats(verwood, pc):
    posts, skipped = P.match_posts(verwood, pc, date(2026, 10, 26), already_posted={})
    assert [p["key"] for p in posts] == ["match-7758947"] and skipped == []
    assert posts[0]["caption"].startswith("🏆 Win for our Indoor C! Verwood won v Harbour Town CC Indoor D.")
    again, _ = P.match_posts(verwood, pc, date(2026, 10, 26), already_posted={"match-7758947": {}})
    assert again == []


def test_lookback_reports_unfinished_scorecards(verwood, pc):
    verwood["posts"]["match_results"]["lookback_days"] = 2
    posts, skipped = P.match_posts(verwood, pc, date(2026, 10, 26), already_posted={})
    assert [p["key"] for p in posts] == ["match-7758947"]
    assert sorted(s.split(": ")[1] for s in skipped) == ["no final result yet", "no finished scorecard yet"]
    assert any(s.startswith("Girls U13 Indoor v Forest Edge CC") for s in skipped)


def test_outdoor_match_card_wicket_margin(verwood, pc):
    card = P.match_card(verwood, pc.match_detail(7700001))
    assert card["summary"] == "Verwood won by 7 wickets"
    assert card["top_bowling"][0]["figures"] == "4-31" and card["top_batting"][0]["figures"] == "87*"


@pytest.mark.parametrize("rule,expected", [("initial", "Alex A."), ("first", "Alex"), ("full", "Alex Archer")])
def test_junior_name_rules(rule, expected):
    assert P.person_name("Alex  Archer", True, rule) == expected
    assert P.person_name("Alex Archer", False, rule) == "Alex Archer"


def test_junior_names_applied_on_cards(verwood, pc):
    verwood["juniors"]["team_pattern"] = r"Indoor C"  # pretend Indoor C is a junior side
    card = P.match_card(verwood, pc.match_detail(7758947))
    assert card["top_batting"][0]["name"] == "Alex A."
    verwood["juniors"]["names"] = "none"
    card = P.match_card(verwood, pc.match_detail(7758947))
    assert card["top_batting"] == [] and card["top_bowling"] == []
    assert "top-scored" not in P.caption_match(verwood, card)


def test_deleted_fixtures_are_ignored(pc):
    ids = [m["id"] for m in pc.fixtures(date(2026, 10, 29), date(2026, 10, 29))]
    assert 7769999 not in ids and 7760000 in ids


def test_placeholder_ground_is_hidden():
    assert P.clean_ground("Add New Ground") == "" and P.clean_ground(" Dorset Indoor Cricket Centre ") == "Dorset Indoor Cricket Centre"


def test_in_progress_code_from_live_api_is_held_back(verwood):
    # Play-Cricket's live API sends result "M" / "Match In Progress" for unfinished games.
    m = {"home_club_id": "8472", "home_team_id": "1", "away_team_id": "2", "result": "M", "result_applied_to": ""}
    assert P.outcome(m, "home", verwood) == ("P", "Result to follow")


def test_game_off_story_once_per_game(verwood, pc):
    verwood["game_off"]["enabled"] = True
    p = P.game_off_post(verwood, pc, date(2026, 10, 27), {})
    assert p["key"] == "gameoff-7700003" and p["stories_only"]
    r = p["data"]["matches"][0]
    assert (r["team"], r["date"], r["outcome"], r["summary"]) == ("3rd XI", "Yesterday", "A", "Abandoned")
    assert "3rd XI v" in p["caption"] and "abandoned" in p["caption"]
    assert P.game_off_post(verwood, pc, date(2026, 10, 27), {"gameoff-7700003": {}}) is None
    verwood["game_off"]["exclude_teams"] = r"\b3rd\b"
    assert P.game_off_post(verwood, pc, date(2026, 10, 27), {}) is None


def test_game_off_is_a_due_job(verwood):
    from kit.run import due_jobs
    verwood["game_off"]["enabled"] = True
    assert "game-off" in due_jobs(verwood, date(2026, 10, 27))
    assert due_jobs(verwood, date(2026, 10, 27), "game-off") == ["game-off"]


def test_feed_posts_wait_for_post_from(verwood, monkeypatch):
    from datetime import datetime
    from kit.run import hold_until
    verwood["posts"]["post_from"] = "10:00"
    monkeypatch.delenv("KIT_POST_NOW", raising=False)
    assert hold_until(verwood, datetime(2026, 11, 12, 6, 20, tzinfo=verwood.tz))
    assert not hold_until(verwood, datetime(2026, 11, 12, 10, 2, tzinfo=verwood.tz))
    monkeypatch.setenv("KIT_POST_NOW", "true")   # started by hand
    assert not hold_until(verwood, datetime(2026, 11, 12, 6, 20, tzinfo=verwood.tz))
    verwood["posts"]["post_from"] = ""
    monkeypatch.delenv("KIT_POST_NOW")
    assert not hold_until(verwood, datetime(2026, 11, 12, 6, 20, tzinfo=verwood.tz))


def test_evening_stories_reshare_once(club_root, monkeypatch):
    import json
    from datetime import datetime
    from types import SimpleNamespace
    from kit import config as C
    from kit.run import cmd_evening_stories, load_state
    y = (club_root / "club.yml").read_text() + "\nevening_stories:\n  enabled: true\n"
    (club_root / "club.yml").write_text(y)
    cfg = C.load(club_root / "club.yml")
    d = club_root / "posts/2026-11-12"
    d.mkdir(parents=True)
    (d / "match-1-story.jpg").write_bytes(b"x")
    (club_root / "state/posted.json").write_text(json.dumps({"posted": {
        "match-1": {"made": "2026-11-12"}, "match-2": {"made": "2026-11-11"}, "fixtures-x": {"made": "2026-11-12"}}}))
    sent = []
    meta = SimpleNamespace(post_instagram_story=lambda u: sent.append(u))
    monkeypatch.delenv("KIT_POST_NOW", raising=False)
    early = datetime(2026, 11, 12, 17, 2, tzinfo=cfg.tz)
    assert cmd_evening_stories(None, club_root, meta=meta, sha="abc", now=early, repo="o/r") and not sent
    late = datetime(2026, 11, 12, 18, 2, tzinfo=cfg.tz)
    cmd_evening_stories(None, club_root, meta=meta, sha="abc", now=late, repo="o/r")
    assert sent == ["https://raw.githubusercontent.com/o/r/abc/posts/2026-11-12/match-1-story.jpg"]
    cmd_evening_stories(None, club_root, meta=meta, sha="abc", now=late, repo="o/r")
    assert len(sent) == 1 and load_state(club_root)["evening_stories"]["match-1"] == "2026-11-12"
