"""Instagram and Facebook Stories: tall graphics posted after the feed post."""
from argparse import Namespace

from test_meta_review_run import FakeGitHub, FakeRenderer, meta, pc
from kit import run as R


def enable_stories(root, approval="review", kinds="[match, fixtures, roundup]"):
    t = (root / "club.yml").read_text().replace("  approval: review", f"  approval: {approval}\n  stories:\n    enabled: true\n    for: {kinds}")
    (root / "club.yml").write_text(t)


def test_story_api_calls():
    m = meta()
    fb = m.post_facebook_story("https://x/s.jpg")
    upload, publish = [c for c in m.http.calls if c[1] in ("PAGE1/photos", "PAGE1/photo_stories")]
    assert upload[2]["published"] == "false" and upload[2]["url"] == "https://x/s.jpg"
    assert publish[2]["photo_id"].startswith("PH") and fb["network"] == "facebook_story"  # publishes the uploaded photo
    m2 = meta()
    ig = m2.post_instagram_story("https://x/s.jpg")
    created = next(c[2] for c in m2.http.calls if c[1] == "IG1/media")
    assert created["media_type"] == "STORIES" and created["image_url"] == "https://x/s.jpg" and "caption" not in created
    assert any(c[1] == "IG1/media_publish" for c in m2.http.calls) and ig["network"] == "instagram_story"


def test_stories_off_by_default(club_root):
    pending = R.cmd_make(Namespace(today="2026-10-26", only=None), root=club_root, pc=pc(), renderer=FakeRenderer())
    assert all(p["story_files"] == [] for p in pending)


def test_story_versions_made_only_for_chosen_kinds(club_root):
    enable_stories(club_root, kinds="[match]")
    pending = R.cmd_make(Namespace(today="2026-10-26", only=None), root=club_root, pc=pc(), renderer=FakeRenderer())
    by_kind = {p["kind"]: p for p in pending}
    assert by_kind["match"]["story_files"] == ["posts/2026-10-26/match-7758947-story.jpg"]
    assert by_kind["roundup"]["story_files"] == []


def test_automatic_posts_feed_then_stories(club_root):
    enable_stories(club_root, approval="automatic")
    R.cmd_make(Namespace(today="2026-10-26", only="matches"), root=club_root, pc=pc(), renderer=FakeRenderer())
    gh, m = FakeGitHub(), meta()
    R.cmd_announce(Namespace(sha="abc"), root=club_root, gh=gh, meta=m)
    assert gh.issues[1]["state"] == "closed" and "published" in gh.labels[1]
    order = [c[1] for c in m.http.calls if c[0] == "POST"]
    assert order.index("PAGE1/photo_stories") > order.index("IG1/media_publish")  # stories after the feed posts
    said = " ".join(c["body"] for c in gh.comments[1])
    assert "Posted to Facebook Stories" in said and "Posted to Instagram Stories" in said
    assert 'width="240"' in gh.issues[1]["body"]  # story preview shown in the issue


def test_story_failure_never_undoes_feed_and_retry_only_redoes_story(club_root):
    enable_stories(club_root)
    R.cmd_make(Namespace(today="2026-10-26", only="matches"), root=club_root, pc=pc(), renderer=FakeRenderer())
    gh = FakeGitHub()
    R.cmd_announce(Namespace(sha="abc"), root=club_root, gh=gh)
    gh.add_labels(1, ["approved"])
    assert R.cmd_publish(Namespace(issue=1), root=club_root, gh=gh, meta=meta(fail_on="photo_stories")) is False
    said = " ".join(c["body"] for c in gh.comments[1])
    assert "Posted to Facebook:" in said and "Posted to Instagram:" in said and "Couldn't post to Facebook Stories" in said
    gh.add_labels(1, ["approved"])
    m = meta()
    links = R.cmd_publish(Namespace(issue=1), root=club_root, gh=gh, meta=m)
    assert [l["network"] for l in links] == ["facebook_story", "instagram_story"]
    assert not any(c[1] in ("PAGE1/feed",) or (c[1] == "PAGE1/photos" and c[2].get("published") != "false") for c in m.http.calls)
    assert gh.issues[1]["state"] == "closed"


def test_bad_story_settings(club_root):
    import pytest
    from kit import config as C
    enable_stories(club_root, kinds="[match, results]")
    with pytest.raises(C.ConfigError, match="posts → stories → for"):
        C.load(club_root / "club.yml")
