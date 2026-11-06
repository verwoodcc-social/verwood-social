"""Club news and events: form -> preview for approval -> (scheduled) post -> reminder Story."""
from argparse import Namespace
from datetime import date

import pytest

from test_meta_review_run import FakeGitHub, FakeRenderer, meta
from kit import config as C, news as N, run as R
from kit.review import parse_issue


def form_body(**kw):
    vals = {"Headline": "Annual General Meeting", "What kind of post is it?": "Event", "Event date": "14/03/2027",
            "Start time": "19:30", "Venue": "Potterne Park clubhouse",
            "Details": "All members welcome. We'll review the season and elect the committee.\n\nTea and cake after.",
            "One line for the graphic": "", "Link": "", "Post on": "", "Photo": ""}
    vals.update(kw)
    return "\n\n".join(f"### {k}\n\n{v or '_No response_'}" for k, v in vals.items()) + \
        "\n\n### Before you submit\n\n- [X] This is fine to share publicly"


class NewsGitHub(FakeGitHub):
    def add_form(self, body, who="MEMBER"):
        n = len(self.issues) + 1
        self.issues[n] = {"number": n, "title": "Club news: AGM", "body": body, "state": "open",
                          "user": {"login": "volunteer"}, "author_association": who, "html_url": f"x/{n}"}
        self.labels[n], self.comments[n] = {"club-news"}, []
        return n

    def open_issues(self, label):
        return [self.get_issue(n) for n, i in self.issues.items() if i["state"] == "open" and label in self.labels[n]]

    def _req(self, method, path, **kw):
        if path == "issues":
            want = set(kw["params"]["labels"].split(","))
            return [self.get_issue(n) for n, i in self.issues.items()
                    if i["state"] == "closed" and want <= self.labels[n]]
        return super()._req(method, path, **kw)


def cfg(root):
    return C.load(root / "club.yml")


def test_parse_dates_and_form():
    today = date(2026, 11, 6)
    assert N.parse_day("14/03/2027", today) == date(2027, 3, 14)
    assert N.parse_day("14th March 2027", today) == date(2027, 3, 14)
    assert N.parse_day("14/3", today) == date(2027, 3, 14)  # no year: the next one
    assert N.parse_day("", today) is None
    with pytest.raises(N.FormError):
        N.parse_day("next Tuesday", today)
    f = N.parse_form(form_body())
    assert N.field(f, "headline") == "Annual General Meeting" and N.field(f, "link") == ""
    assert N.tidy_time("19:30") == "7:30pm" and N.tidy_time("10.00") == "10:00am"


def test_build_post_caption_and_reminder(club_root):
    post = N.build(cfg(club_root), N.parse_form(form_body()), 5, date(2026, 11, 6))
    d = post["data"]
    assert d["when"] == "Sunday 14 March 2027 · 7:30pm" and d["venue"] == "Potterne Park clubhouse"
    assert d["blurb"].startswith("All members welcome") and "Tea" not in d["blurb"]
    assert post["caption"].startswith("📅 Annual General Meeting") and "📍 Potterne Park clubhouse" in post["caption"]
    assert post["review"] and post["reminder_date"] == "2027-03-14" and post["reminder_data"]["today"]


def test_form_problems_are_explained(club_root):
    c = cfg(club_root)
    with pytest.raises(N.FormError, match="already passed"):
        N.build(c, N.parse_form(form_body(**{"Event date": "01/01/2026"})), 5, date(2026, 11, 6))
    with pytest.raises(N.FormError, match="70 or fewer"):
        N.build(c, N.parse_form(form_body(Headline="x" * 80)), 5, date(2026, 11, 6))


def test_photo_url_only_from_github():
    assert N.photo_url("![a](https://github.com/user-attachments/assets/abc)") == \
        "https://github.com/user-attachments/assets/abc"
    assert N.photo_url('<img src="https://evil.example/x.jpg">') is None


def test_strangers_forms_are_ignored(club_root):
    gh = NewsGitHub()
    n = gh.add_form(form_body(), who="NONE")
    assert R.cmd_news(Namespace(issue=n, today="2026-11-06"), root=club_root, gh=gh, renderer=FakeRenderer()) is None
    assert gh.comments[n] == []


def test_form_to_preview_even_when_automatic_then_scheduled_then_reminder(club_root):
    t = (club_root / "club.yml").read_text().replace("  approval: review", "  approval: automatic")
    (club_root / "club.yml").write_text(t)
    gh, m = NewsGitHub(), meta()
    n = gh.add_form(form_body(**{"Post on": "01/03/2027"}))
    (p,) = R.cmd_news(Namespace(issue=n, today="2026-11-06"), root=club_root, gh=gh, renderer=FakeRenderer())
    assert p["files"]
    assert p["reminder_file"].endswith("-reminder-story.jpg")
    (post_issue,) = R.cmd_announce(Namespace(sha="abc"), root=club_root, gh=gh, meta=m)
    assert gh.issues[post_issue]["state"] == "open" and not m.http.calls  # never posted without approval
    assert f"#{post_issue}" in gh.comments[n][-1]["body"]
    info, _ = parse_issue(gh.issues[post_issue]["body"])
    assert info["post_on"] == "2027-03-01" and info["reminder"]["date"] == "2027-03-14"
    assert "Goes out on Monday 1 March 2027" in gh.issues[post_issue]["body"]

    gh.add_labels(post_issue, ["approved"])
    assert R.cmd_publish(Namespace(issue=post_issue, today="2026-11-07"), root=club_root, gh=gh, meta=m) is None
    assert "scheduled" in gh.labels[post_issue] and not m.http.calls  # waits for its date

    R.cmd_due(Namespace(today="2027-02-28"), root=club_root, gh=gh, meta=m)
    assert not m.http.calls
    R.cmd_due(Namespace(today="2027-03-01"), root=club_root, gh=gh, meta=m)
    assert gh.issues[post_issue]["state"] == "closed" and "published" in gh.labels[post_issue]
    assert "scheduled" not in gh.labels[post_issue]
    gh.issues[post_issue]["closed_at"] = "2027-03-01T06:20:00Z"

    before = len(m.http.calls)
    R.cmd_due(Namespace(today="2027-03-14"), root=club_root, gh=gh, meta=m)
    new = [c[1] for c in m.http.calls[before:] if c[0] == "POST"]
    assert "PAGE1/photo_stories" in new and "IG1/media_publish" in new
    assert any("Reminder posted to Instagram Stories" in c["body"] for c in gh.comments[post_issue])
    before = len(m.http.calls)
    R.cmd_due(Namespace(today="2027-03-14"), root=club_root, gh=gh, meta=m)  # second morning run
    assert len(m.http.calls) == before  # not repeated


def test_edited_form_replaces_old_preview(club_root):
    gh = NewsGitHub()
    n = gh.add_form(form_body())
    for _ in range(2):
        R.cmd_news(Namespace(issue=n, today="2026-11-06"), root=club_root, gh=gh, renderer=FakeRenderer())
        R.cmd_announce(Namespace(sha="abc"), root=club_root, gh=gh)
    previews = [i for i in gh.issues if i != n]
    assert [gh.issues[i]["state"] for i in previews] == ["closed", "open"]
