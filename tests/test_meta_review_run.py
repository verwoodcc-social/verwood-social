import json
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import FakePlayCricketHTTP, Resp
from kit import run as R
from kit.meta import Meta, MetaError
from kit.playcricket import PlayCricket
from kit.review import issue_body, parse_issue, raw_url


# --- a stand-in for graph.facebook.com ----------------------------------------

class FakeGraph:
    def __init__(self, ig=True, fail_on=None, pages=1):
        self.calls, self.ig, self.fail_on, self.pages, self.n = [], ig, fail_on, pages, 0

    def request(self, method, url, data=None, params=None, timeout=None):
        p = dict(data or params or {})
        path = url.split("/v25.0/", 1)[1]
        self.calls.append((method, path, p))
        if self.fail_on and self.fail_on in path:
            return Resp(400, {"error": {"code": 9004, "message": "Media download has failed."}})
        self.n += 1
        if path == "me/accounts":
            return Resp(200, {"data": [{"id": f"PAGE{i}", "name": f"Page {i}"} for i in range(1, self.pages + 1)]})
        if path.startswith("PAGE1") and method == "GET":
            body = {"name": "Verwood Cricket Club", "access_token": "PAGE_TOKEN"}
            if self.ig:
                body["instagram_business_account"] = {"id": "IG1", "username": "verwoodcc"}
            return Resp(200, body)
        if path == "PAGE1/photos":
            return Resp(200, {"id": f"PH{self.n}", **({"post_id": f"PAGE1_{self.n}"} if p.get("published") != "false" else {})})
        if path == "PAGE1/photo_stories":
            return Resp(200, {"success": True, "post_id": f"PAGE1_S{self.n}"})
        if path == "PAGE1/feed":
            return Resp(200, {"id": f"PAGE1_F{self.n}"})
        if path == "IG1/media":
            return Resp(200, {"id": f"C{self.n}"})
        if path == "IG1/media_publish":
            return Resp(200, {"id": "M1"})
        if path.startswith("C") and method == "GET":
            return Resp(200, {"status_code": "FINISHED"})
        if path == "M1":
            return Resp(200, {"permalink": "https://www.instagram.com/p/abc/"})
        return Resp(404, {"error": {"code": 100, "message": f"unexpected {path}"}})


def meta(**kw):
    return Meta("SYSTEM_TOKEN", session=FakeGraph(**kw), sleep=lambda s: None)


def test_resolves_page_and_instagram_from_system_user_token():
    m = meta()
    info = m.resolve()
    assert info == {"page_id": "PAGE1", "page_name": "Verwood Cricket Club", "instagram_id": "IG1", "instagram_username": "verwoodcc"}
    assert m.page_token == "PAGE_TOKEN"


def test_several_pages_needs_page_id_in_config():
    with pytest.raises(MetaError, match="several Facebook Pages"):
        meta(pages=2).resolve()


def test_facebook_single_and_multi_photo():
    m = meta()
    r = m.post_facebook(["https://x/a.jpg"], "hello")
    method, path, p = m.http.calls[-1]
    assert (method, path) == ("POST", "PAGE1/photos") and p["url"] == "https://x/a.jpg" and p["message"] == "hello"
    assert p["access_token"] == "PAGE_TOKEN" and r["url"].startswith("https://www.facebook.com/PAGE1_")
    m.post_facebook(["https://x/1.jpg", "https://x/2.jpg"], "two")
    feed = m.http.calls[-1]
    assert feed[1] == "PAGE1/feed" and json.loads(feed[2]["attached_media[1]"])["media_fbid"].startswith("PH")


def test_instagram_single_and_carousel():
    m = meta()
    r = m.post_instagram(["https://x/a.jpg"], "cap")
    steps = [(c[0], c[1]) for c in m.http.calls if not c[1].startswith(("me/", "PAGE1"))]
    assert steps == [("POST", "IG1/media"), ("GET", steps[1][1]), ("POST", "IG1/media_publish"), ("GET", "M1")]
    assert steps[1][1].startswith("C")  # waited for the container to finish
    publish = next(c[2] for c in m.http.calls if c[1] == "IG1/media_publish")
    assert publish["creation_id"] == steps[1][1]
    assert r["url"] == "https://www.instagram.com/p/abc/"
    m2 = meta()
    m2.post_instagram(["https://x/1.jpg", "https://x/2.jpg"], "cap")
    media_posts = [c[2] for c in m2.http.calls if c[1] == "IG1/media"]
    assert [p.get("is_carousel_item") for p in media_posts[:2]] == ["true", "true"]
    assert media_posts[2]["media_type"] == "CAROUSEL" and media_posts[2]["children"].count(",") == 1
    assert media_posts[2]["caption"] == "cap"


def test_instagram_needs_linked_account():
    with pytest.raises(MetaError, match="no Instagram professional account"):
        meta(ig=False).post_instagram(["https://x/a.jpg"], "cap")


def test_meta_errors_are_explained():
    with pytest.raises(MetaError, match="repository is public"):
        meta(fail_on="IG1/media").post_instagram(["https://x/a.jpg"], "cap")


# --- issue body round trip ---------------------------------------------------

POST = {"key": "match-1", "kind": "match", "title": "Indoor C v Harbour Town", "caption": "Line one\nLine two",
        "alt": "alt text", "match_id": "1"}


def test_issue_body_round_trip_and_edited_caption():
    body = issue_body(POST, ["https://raw.githubusercontent.com/o/r/sha/posts/a.jpg"], ["facebook", "instagram"])
    meta_info, caption = parse_issue(body)
    assert caption == "Line one\nLine two" and meta_info["key"] == "match-1" and meta_info["sample"] is False
    edited = body.replace("Line two", "Line two, edited by a volunteer")
    assert parse_issue(edited)[1].endswith("edited by a volunteer")
    assert "add the **approved** label" in body


# --- full runs with stand-ins for GitHub and the browser -----------------------

class FakeGitHub:
    repo = "club/cricket-social"

    def __init__(self):
        self.issues, self.comments, self.labels = {}, {}, {}

    def ensure_labels(self):
        pass

    def create_issue(self, title, body, labels=("social-post",)):
        n = len(self.issues) + 1
        self.issues[n] = {"number": n, "title": title, "body": body, "state": "open",
                          "user": {"login": "github-actions[bot]"}, "html_url": f"https://github.com/x/issues/{n}"}
        self.labels[n] = set(labels)
        self.comments[n] = []
        return self.issues[n]

    def get_issue(self, n):
        return {**self.issues[n], "labels": [{"name": l} for l in self.labels[n]]}

    def comment(self, n, body):
        self.comments[n].append({"body": body, "user": {"login": "github-actions[bot]"}})

    def add_labels(self, n, labels):
        self.labels[n] |= set(labels)

    def remove_label(self, n, label):
        self.labels[n].discard(label)

    def close(self, n):
        self.issues[n]["state"] = "closed"

    def _req(self, method, path, **kw):
        return self.comments[int(path.split("/")[1])]

    def repo_info(self):
        return {"private": False}


class FakeRenderer:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def render(self, cfg, data, out_dir, stem, story=False):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        f = Path(out_dir) / f"{stem}{'-story' if story else ''}.jpg"
        f.write_bytes(b"jpg")
        return [f]


def pc():
    return PlayCricket("t", 8472, session=FakePlayCricketHTTP())


def test_monday_run_makes_roundup_and_match_post_then_no_repeats(club_root):
    args = Namespace(today="2026-10-26", only=None)  # a Monday
    pending = R.cmd_make(args, root=club_root, pc=pc(), renderer=FakeRenderer())
    assert sorted(p["kind"] for p in pending) == ["match", "roundup"]
    gh = FakeGitHub()
    opened = R.cmd_announce(Namespace(sha="abc123"), root=club_root, gh=gh)
    assert len(opened) == 2
    body = gh.issues[1]["body"] + gh.issues[2]["body"]
    assert raw_url(gh.repo, "abc123", "posts/2026-10-26/") in body
    state = json.loads((club_root / "state/posted.json").read_text())
    assert set(state["posted"]) == {"roundup-2026-10-26", "match-7758947"}
    # same day again: nothing new
    assert R.cmd_make(args, root=club_root, pc=pc(), renderer=FakeRenderer()) == []


def test_friday_run_makes_fixtures(club_root):
    pending = R.cmd_make(Namespace(today="2026-10-30", only=None), root=club_root, pc=pc(), renderer=FakeRenderer())
    assert [p["kind"] for p in pending] == ["fixtures"]


def _approved_issue(club_root, gh):
    R.cmd_make(Namespace(today="2026-10-26", only="matches"), root=club_root, pc=pc(), renderer=FakeRenderer())
    R.cmd_announce(Namespace(sha="abc123"), root=club_root, gh=gh)
    gh.add_labels(1, ["approved"])
    return 1


def test_publish_approved_issue_posts_to_both(club_root):
    gh = FakeGitHub()
    n = _approved_issue(club_root, gh)
    m = meta()
    links = R.cmd_publish(Namespace(issue=n), root=club_root, gh=gh, meta=m)
    assert [l["network"] for l in links] == ["facebook", "instagram"]
    assert "published" in gh.labels[n] and gh.issues[n]["state"] == "closed"
    fb = next(c for c in m.http.calls if c[1] == "PAGE1/photos")
    assert fb[2]["url"].startswith("https://raw.githubusercontent.com/club/cricket-social/abc123/posts/2026-10-26/")
    assert fb[2]["message"].startswith("🏆 Win for our Indoor C!")


def test_partial_failure_then_retry_does_not_double_post(club_root):
    gh = FakeGitHub()
    n = _approved_issue(club_root, gh)
    assert R.cmd_publish(Namespace(issue=n), root=club_root, gh=gh, meta=meta(fail_on="IG1/media")) is False
    assert "failed" in gh.labels[n] and "approved" not in gh.labels[n] and gh.issues[n]["state"] == "open"
    assert "Couldn't post to Instagram" in gh.comments[n][-1]["body"]
    gh.add_labels(n, ["approved"])  # volunteer fixes it and approves again
    m = meta()
    links = R.cmd_publish(Namespace(issue=n), root=club_root, gh=gh, meta=m)
    assert [l["network"] for l in links] == ["instagram"]  # Facebook not posted twice
    assert not any(c[1] == "PAGE1/photos" for c in m.http.calls)
    assert gh.issues[n]["state"] == "closed" and "failed" not in gh.labels[n]


def test_publish_refuses_unapproved_or_foreign_issues(club_root):
    gh = FakeGitHub()
    n = _approved_issue(club_root, gh)
    gh.remove_label(n, "approved")
    assert R.cmd_publish(Namespace(issue=n), root=club_root, gh=gh, meta=meta()) is None
    gh.add_labels(n, ["approved"])
    gh.issues[n]["user"]["login"] = "someone-else"
    m = meta()
    assert R.cmd_publish(Namespace(issue=n), root=club_root, gh=gh, meta=m) is None and m.http.calls == []
    gh.issues[n]["user"]["login"] = "github-actions[bot]"
    gh.issues[n]["body"] = gh.issues[n]["body"].replace("raw.githubusercontent.com/club/cricket-social", "evil.example")
    assert R.cmd_publish(Namespace(issue=n), root=club_root, gh=gh, meta=m) is None and m.http.calls == []


def test_automatic_mode_posts_without_waiting(club_root):
    cfg_path = club_root / "club.yml"
    cfg_path.write_text(cfg_path.read_text().replace("approval: review", "approval: automatic"))
    R.cmd_make(Namespace(today="2026-10-26", only="matches"), root=club_root, pc=pc(), renderer=FakeRenderer())
    gh, m = FakeGitHub(), meta()
    R.cmd_announce(Namespace(sha="abc123"), root=club_root, gh=gh, meta=m)
    assert gh.issues[1]["state"] == "closed" and "published" in gh.labels[1]
    assert any(c[1] == "IG1/media_publish" for c in m.http.calls)


def test_check_reports_each_connection(club_root, capsys):
    ok = R.cmd_check(Namespace(today="2026-10-26"), root=club_root, pc=pc(), meta=meta(), gh=FakeGitHub(),
                     renderer=FakeRenderer())
    out = capsys.readouterr().out
    assert ok is True
    assert "Play-Cricket** connected" in out and 'Page "Verwood Cricket Club"' in out and "@verwoodcc" in out
    pending = json.loads((club_root / ".kit-pending.json").read_text())
    assert [p["key"] for p in pending] == ["sample-fixtures", "sample-roundup", "sample-match", "sample-milestone"]


def test_check_explains_bad_settings(tmp_path, capsys):
    (tmp_path / "club.yml").write_text("club:\n  name: x\n   bad indent: [")
    assert R.cmd_check(Namespace(today=None), root=tmp_path) is False
    assert "isn't laid out correctly" in capsys.readouterr().out


def test_preview_closes_older_previews(club_root):
    gh = FakeGitHub()
    gh.open_issues = lambda label: [{"number": n, "title": i["title"]} for n, i in gh.issues.items() if i["state"] == "open"]
    for _ in range(2):
        R.cmd_check(Namespace(today="2026-10-26"), root=club_root, pc=pc(), meta=meta(), gh=gh, renderer=FakeRenderer())
        R.cmd_preview(Namespace(sha="abc"), root=club_root, gh=gh)
    assert [i["state"] for i in gh.issues.values()] == ["closed", "open"]
    meta_info, _ = parse_issue(gh.issues[2]["body"])
    assert meta_info["sample"] is True


def test_sample_preview_cannot_be_published(club_root):
    gh = FakeGitHub()
    gh.open_issues = lambda label: []
    R.cmd_check(Namespace(today="2026-10-26"), root=club_root, pc=pc(), meta=meta(), gh=gh, renderer=FakeRenderer())
    n = R.cmd_preview(Namespace(sha="abc"), root=club_root, gh=gh)
    gh.add_labels(n, ["approved"])
    m = meta()
    assert R.cmd_publish(Namespace(issue=n), root=club_root, gh=gh, meta=m) is None
    assert m.http.calls == [] and "can't be posted" in gh.comments[n][-1]["body"]


def test_old_images_are_cleared(club_root):
    for d in ("2026-08-01", "2026-10-20"):
        (club_root / "posts" / d).mkdir(parents=True)
    (club_root / "posts/samples").mkdir()
    R.clear_old_images(club_root, R.date(2026, 10, 26))
    assert sorted(p.name for p in (club_root / "posts").iterdir()) == ["2026-10-20", "samples"]
