"""Club uploads and customisation: background photos, sponsor, wording, show/hide, my-templates."""
import shutil

import pytest
from PIL import Image

from conftest import ROOT
from kit import config as C
from kit import posts as P
from kit.render import pages_html
from kit.run import customisations
from kit.samples import sample_posts
from datetime import date


def club(tmp_path, extra=""):
    (tmp_path / "assets").mkdir(exist_ok=True)
    shutil.copy(ROOT / "examples/verwood/badge.svg", tmp_path / "assets/badge.svg")
    base = (ROOT / "examples/verwood/club.yml").read_text().replace('badge: "badge.svg"', 'badge: "assets/badge.svg"')
    (tmp_path / "club.yml").write_text(base + "\n" + extra)
    return tmp_path


def photo(path, size=(1600, 2000), mode="RGB"):
    Image.new(mode, size, (40, 120, 50) if mode == "RGB" else (40, 120, 50, 255)).save(path)


def html_for(cfg, kind):
    posts = sample_posts(cfg, date(2026, 5, 15))
    return pages_html(cfg, {"fixtures": posts[0], "results": posts[1], "match": posts[2]}[kind]["data"])[0]


def test_defaults_need_no_new_settings(verwood):
    assert verwood["wording"]["win"] == "Victory" and verwood["show"]["toss"] is True
    assert verwood.background_for("match") is None and customisations(verwood) == []


def test_background_photo_and_per_type_override(tmp_path):
    root = club(tmp_path)
    photo(root / "assets/ground.jpg")
    photo(root / "assets/night.jpg")
    (root / "club.yml").write_text((root / "club.yml").read_text().replace(
        "branding:", 'branding:\n  background_image: "assets/ground.jpg"\n  match_background: "assets/night.jpg"'))
    cfg = C.load(root / "club.yml")
    assert cfg.background_for("fixtures").name == "ground.jpg" and cfg.background_for("match").name == "night.jpg"
    h = html_for(cfg, "fixtures")
    assert "has-photo" in h and 'class="photo"' in h and "data:image/jpeg;base64," in h
    assert "--overlay-top:rgba(" in h
    assert any("Background photo: assets/ground.jpg" in line for line in customisations(cfg))


def test_missing_upload_gets_a_helpful_message(tmp_path):
    root = club(tmp_path, 'wording: {}\n')
    photo(root / "assets/Ground.JPG")
    (root / "club.yml").write_text((root / "club.yml").read_text().replace(
        "branding:", 'branding:\n  background_image: "assets/ground.jpg"'))
    with pytest.raises(C.ConfigError) as e:
        C.load(root / "club.yml")
    msg = str(e.value)
    assert "I can't find 'assets/ground.jpg'" in msg and "Ground.JPG" in msg  # lists what is there


def test_not_a_picture_and_small_photo_warning(tmp_path):
    root = club(tmp_path)
    (root / "assets/notes.pdf").write_text("x")
    (root / "club.yml").write_text((root / "club.yml").read_text().replace(
        "branding:", 'branding:\n  sponsor_logo: "assets/notes.pdf"'))
    with pytest.raises(C.ConfigError, match="isn't a picture I can use"):
        C.load(root / "club.yml")
    photo(root / "assets/tiny.jpg", (600, 700))
    (root / "club.yml").write_text((root / "club.yml").read_text().replace("assets/notes.pdf", "assets/tiny.jpg")
                                   .replace("sponsor_logo", "background_image"))
    cfg = C.load(root / "club.yml")
    assert cfg.warnings and "may look blurry" in cfg.warnings[0]


def test_sponsor_on_graphics_and_captions(tmp_path):
    root = club(tmp_path)
    photo(root / "assets/sponsor.png", (500, 200), "RGBA")
    (root / "club.yml").write_text((root / "club.yml").read_text().replace(
        "branding:", 'branding:\n  sponsor_logo: "assets/sponsor.png"\n  sponsor_text: "Example Builders"\n  sponsor_in_captions: true'))
    cfg = C.load(root / "club.yml")
    h = html_for(cfg, "match")
    assert 'class="sponsor"' in h and "data:image/png;base64," in h and "Supported by" in h
    cap = sample_posts(cfg, date(2026, 5, 15))[2]["caption"]
    assert cap.endswith("Supported by Example Builders\n#VerwoodCC #CricketDorset #ClubCricket")


def test_sponsor_text_only(tmp_path):
    root = club(tmp_path, 'branding:\n  sponsor_text: "Example Builders"\n  sponsor_label: "Sponsored by"\n')
    cfg = C.load(root / "club.yml")
    h = html_for(cfg, "results")
    assert "Sponsored by" in h and '<span class="name">Example Builders</span>' in h
    assert "Example Builders" not in sample_posts(cfg, date(2026, 5, 15))[1]["caption"]  # captions off by default


def test_own_wording(tmp_path):
    root = club(tmp_path, 'wording:\n  fixtures_title: "Coming Up"\n  win: "Get In!"\n  fixtures_sign_off: "See you there!"\n')
    cfg = C.load(root / "club.yml")
    assert ">Coming Up<" in html_for(cfg, "fixtures") and ">Get In!<" in html_for(cfg, "match")
    assert "See you there!" in P.caption_fixtures(cfg, sample_posts(cfg, date(2026, 5, 15))[0]["data"])


def test_show_and_hide(tmp_path):
    root = club(tmp_path, 'show:\n  top_performers: false\n  toss: false\n  ground_on_fixtures: true\n  handle_and_website: false\n')
    cfg = C.load(root / "club.yml")
    m = html_for(cfg, "match")
    assert "Top batting" not in m and "won the toss" not in m and "@verwoodcc" not in m
    data = sample_posts(cfg, date(2026, 5, 15))[0]["data"]
    data["matches"][0]["ground"] = "Potterne Park"
    assert "at Potterne Park" in pages_html(cfg, data)[0]


def test_bad_show_and_wording_values(tmp_path):
    root = club(tmp_path, 'show:\n  toss: maybe\nwording:\n  win: ""\n')
    with pytest.raises(C.ConfigError) as e:
        C.load(root / "club.yml")
    assert "show → toss: use true or false" in str(e.value) and "wording → win" in str(e.value)


def test_my_templates_override_and_extra_css(tmp_path):
    root = club(tmp_path)
    (root / "my-templates").mkdir()
    (root / "my-templates/match.html").write_text("<html><style>{{ css|safe }}</style><h1>OWN {{ m.team }}</h1>"
                                                  "{% include '_foot.html' %}</html>")
    (root / "my-templates/extra.css").write_text(".title { color: hotpink; }")
    cfg = C.load(root / "club.yml")
    m = html_for(cfg, "match")
    assert "<h1>OWN 1st XI</h1>" in m and "hotpink" in m and 'class="foot"' in m  # shared parts still work
    fx = html_for(cfg, "fixtures")
    assert "hotpink" in fx and "<h1>OWN" not in fx and 'class="row fix"' in fx  # kit design otherwise
    assert any("my-templates" in line for line in customisations(cfg))
