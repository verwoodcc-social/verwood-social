"""Milestones (50s, 100s, five-fors) and player photos, with the ECB rule: never a junior's photo and name together."""
import json
from argparse import Namespace
from pathlib import Path

import pytest
from PIL import Image

from conftest import DATA, ROOT
from kit import config as C
from kit import posts as P
from kit.milestones import PhotoStore, find_milestones, milestone_posts
from kit.render import pages_html


def card_with(cfg, runs=104, batter="Sam Butler", wickets=5, bowler="Max Cross"):
    d = json.loads((DATA / "match_detail_7700001.json").read_text())["match_details"][0]
    d["innings"][1]["bat"][1].update(runs=str(runs), batsman_name=batter, balls="71")   # Verwood batting
    d["innings"][0]["bowl"][1].update(wickets=str(wickets), runs="23", bowler_name=bowler)  # Verwood bowling
    return P.match_card(cfg, d)


def store(tmp_path, adults=(), juniors=()):
    for group, names in (("adults", adults), ("juniors", juniors)):
        (tmp_path / group).mkdir(parents=True, exist_ok=True)
        for n in names:
            Image.new("RGB", (600, 800), (40, 120, 60)).save(tmp_path / group / f"{n}.jpg")
    return PhotoStore(tmp_path)


def test_finds_fifties_centuries_and_five_fors(verwood):
    card = card_with(verwood)
    got = [(m["type"], m["figures"], m["name"]) for m in find_milestones(verwood, card)]
    assert got == [("100", "104", "Sam B."), ("5w", "5-23", "Max C."), ("50", "87*", "Alex A.")]  # century, five-for, fifty


def test_no_milestones_no_posts(verwood):
    card = card_with(verwood, runs=49, wickets=4)
    card["all_batting"] = [b for b in card["all_batting"] if b["runs"] < 50]  # nobody reached 50
    assert find_milestones(verwood, card) == [] and milestone_posts(verwood, card) == []


def test_thresholds_and_switch_off(verwood):
    verwood["milestones"]["bowling_wickets"] = 6
    assert "5w" not in [m["type"] for m in find_milestones(verwood, card_with(verwood))]
    verwood["milestones"]["enabled"] = False
    assert milestone_posts(verwood, card_with(verwood)) == []


def test_adult_photo_and_name_together(verwood, tmp_path):
    photos = store(tmp_path, adults=["Alex Archer"])
    post = next(p for p in milestone_posts(verwood, card_with(verwood), photos) if p["data"]["type"] == "50")
    assert post["photo_rule"] == "adult: photo and name" and post["data"]["name"] == "Alex A."
    assert post["data"]["photo_path"].endswith("Alex Archer.jpg")
    assert post["caption"].startswith("🎉 Congratulations to Alex A. on a brilliant fifty!")
    html = pages_html(verwood, post["data"])[0]
    assert 'class="ms-photo"' in html and "Alex A." in html


def test_junior_never_photo_and_name_together(verwood, tmp_path):
    photos = store(tmp_path, juniors=["Sam Butler"])
    post = next(p for p in milestone_posts(verwood, card_with(verwood), photos) if p["data"]["type"] == "100")
    assert post["photo_rule"] == "junior: name, no photo"
    assert post["data"]["photo_path"] == "" and post["data"]["name"] == "Sam B."
    assert 'class="ms-photo"' not in pages_html(verwood, post["data"])[0]
    verwood["milestones"]["junior_photos"] = "photo_no_name"
    post = next(p for p in milestone_posts(verwood, card_with(verwood), photos) if p["data"]["type"] == "100")
    assert post["data"]["photo_path"] and post["data"]["name"] == ""
    assert "Sam" not in post["caption"] and "Sam" not in post["alt"] and "Sam" not in post["title"]
    html = pages_html(verwood, post["data"])[0]
    assert 'class="ms-photo"' in html and "Sam" not in html


def test_junior_team_photo_in_adults_folder_still_follows_junior_rule(verwood, tmp_path):
    photos = store(tmp_path, adults=["Sam Butler"])
    card = card_with(verwood)
    card["junior"] = True  # e.g. an U15 match
    post = next(p for p in milestone_posts(verwood, card, photos) if p["data"]["type"] == "100")
    assert post["data"]["photo_path"] == "" and post["photo_rule"].startswith("junior")


def test_photo_names_match_loosely(tmp_path):
    photos = store(tmp_path, adults=["alex  archer"])
    assert photos.find("Alex Archer") and photos.find("ALEX ARCHER") and not photos.find("Alex Archers")


def test_milestones_come_with_the_daily_match_post_and_never_repeat(verwood, pc, monkeypatch):
    orig = P.match_card
    monkeypatch.setattr(P, "match_card", lambda cfg, d: (lambda c: c and c | {"all_batting": c["all_batting"] +
        [{"name": "Alex A.", "full_name": "Alex Archer", "player_id": "77", "not_out": True, "runs": 61,
          "balls": 40, "figures": "61*", "detail": ""}]})(orig(cfg, d)))
    from datetime import date
    posts, _ = P.match_posts(verwood, pc, date(2026, 10, 26), {})
    keys = [p["key"] for p in posts]
    assert keys == ["match-7758947", "milestone-7758947-50-77"]
    again, _ = P.match_posts(verwood, pc, date(2026, 10, 26), {"match-7758947": {}, "milestone-7758947-50-77": {}})
    assert again == []


def test_photos_never_saved_in_public_repo(tmp_path):
    ignored = (ROOT / ".gitignore").read_text()
    assert "player-photos/" in ignored
    wf = (ROOT / ".github/workflows/make-posts.yml").read_text()
    assert "git add posts state" in wf and "kit photos sync" in wf  # photos copied in; only posts/ and state/ committed


def test_bad_milestone_settings(club_root):
    (club_root / "club.yml").write_text((club_root / "club.yml").read_text() +
                                        "\nmilestones:\n  junior_photos: both\n")
    with pytest.raises(C.ConfigError, match="never both"):
        C.load(club_root / "club.yml")
