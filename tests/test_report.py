"""Monthly sponsor report: figures from Meta + what the kit posted, as a PDF in an issue."""
import json
from argparse import Namespace
from datetime import date, datetime, timezone

from test_meta_review_run import FakeGitHub
from kit import config as C, report as RP, run as R


class FakeIns:
    def __init__(self, broken=False):
        self.problems = ["Instagram views: missing permission"] if broken else []
        self.broken = broken

    def followers(self):
        return {"facebook": 1204, "instagram": 860}

    def page_totals(self, a, b):
        return {"views": 5400, "reach": 2100}

    def ig_totals(self, a, b):
        return {} if self.broken else {"views": 3300, "reach": 1500, "interactions": 410}

    def page_posts(self, a, b):
        return [{"network": "Facebook", "text": "🏏 VICTORY for the 1st XI!\nmore", "when": "2026-10-12T08:00:00+0000",
                 "likes": 80, "comments": 6, "shares": 3, "views": 2300, "url": "u"},
                {"network": "Facebook", "text": "Fixtures this week", "when": "2026-10-09T08:00:00+0000",
                 "likes": 10, "comments": 0, "shares": 1, "views": 900, "url": "u"}]

    def ig_posts(self, a, b):
        return [{"network": "Instagram", "text": "Matchday", "when": "2026-10-11T07:00:00+0000",
                 "likes": 50, "comments": 2, "shares": 0, "views": 1200, "url": "u"}]


def published(kind, closed, images=1, stories=1, sample=False):
    meta = {"key": "k", "kind": kind, "images": ["i"] * images, "networks": ["facebook", "instagram"],
            "stories": ["s"] * stories, "sample": sample}
    return {"closed_at": closed, "body": f"x <!-- csk-post {json.dumps(meta)} -->"}


def test_gather_totals_kit_counts_and_top_posts(club_root):
    cfg = C.load(club_root / "club.yml")
    issues = [published("match", "2026-10-12T09:00:00Z"), published("match", "2026-10-19T09:00:00Z"),
              published("matchday", "2026-10-11T06:00:00Z", images=0), published("fixtures", "2026-11-01T06:00:00Z"),
              published("roundup", "2026-10-05T06:00:00Z", sample=True)]
    r = RP.gather(cfg, FakeIns(), issues, (2026, 10), {"facebook": 1190, "instagram": 861})
    assert r["totals"] == {"views": 8700, "reach": 3600, "engagement": 100 + 410}
    assert r["kit"]["rows"] == [("Match results", 2), ("Matchday Stories", 1)]  # November and samples left out
    assert r["kit"]["feed"] == 4 and r["kit"]["stories"] == 6
    assert [p["views"] for p in r["top"]] == [2300, 1200, 900] and r["top"][0]["title"] == "🏏 VICTORY for the 1st XI!"
    assert r["networks"][0]["change"] == 14 and r["networks"][1]["change"] == -1
    assert "8,700 views" in RP.caption(r) and "4 posts and 6 Stories carried the" in RP.caption(r)


def test_missing_figures_shown_as_dashes(club_root):
    cfg = C.load(club_root / "club.yml")
    r = RP.gather(cfg, FakeIns(broken=True), [], (2026, 10))
    assert r["networks"][1]["views"] is None and r["totals"]["views"] == 5400 and r["first_report"]
    assert r["problems"] and RP.fmt(None) == "–"


def test_report_command_and_issue(club_root, monkeypatch):
    import kit.meta
    monkeypatch.setattr(kit.meta, "Insights", lambda m: FakeIns())

    class GH(FakeGitHub):
        def _req(self, method, path, **kw):
            return [published("match", "2026-10-12T09:00:00Z")] if path == "issues" else []

    def fake_render(cfg, r, out_dir, stem):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{stem}.pdf").write_bytes(b"pdf")
        (out_dir / f"{stem}.jpg").write_bytes(b"jpg")
        return out_dir / f"{stem}.pdf", out_dir / f"{stem}.jpg"

    gh = GH()
    out = R.cmd_report(Namespace(today="2026-11-01", month=None), root=club_root, gh=gh, meta=object(),
                       render=fake_render)
    assert out["month"] == "October 2026" and out["pdf"].endswith("-2026-10.pdf")
    state = json.loads((club_root / "state/posted.json").read_text())
    assert state["report_followers"]["2026-10"] == {"facebook": 1204, "instagram": 860}
    n = R.cmd_report_issue(Namespace(sha="abc"), root=club_root, gh=gh)
    assert gh.labels[n] == {"report"} and "social-post" not in gh.labels[n]  # can never be published
    assert "Download the PDF" in gh.issues[n]["body"] and "/raw/abc/posts/reports/" in gh.issues[n]["body"]


def test_email_settings_and_send(tmp_path):
    import pytest
    from kit import mailer
    assert mailer.settings({}) is None
    with pytest.raises(mailer.MailError, match="Missing"):
        mailer.settings({"M365_TENANT_ID": "t"})
    env = {"M365_TENANT_ID": "t", "M365_CLIENT_ID": "c", "M365_CLIENT_SECRET": "s",
           "REPORT_EMAIL_FROM": "a@club.co.uk", "REPORT_EMAIL_TO": "a@club.co.uk, b@club.co.uk;c@club.co.uk"}
    s = mailer.settings(env)
    assert s["to"] == ["a@club.co.uk", "b@club.co.uk", "c@club.co.uk"]

    class R:
        def __init__(self, code, body):
            self.status_code, self._b, self.content, self.text = code, body, b"x" if body else b"", ""

        def json(self):
            return self._b

    class HTTP:
        calls = []

        def post(self, url, **kw):
            self.calls.append((url, kw))
            return R(200, {"access_token": "tok"}) if "login" in url else R(202, None)

    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    h = HTTP()
    assert mailer.send(s, "Subj", "Body", [pdf], http=h) == s["to"]
    url, kw = h.calls[1]
    assert url.endswith("/users/a@club.co.uk/sendMail")
    msg = kw["json"]["message"]
    assert len(msg["toRecipients"]) == 3 and msg["attachments"][0]["name"] == "r.pdf"


def test_committee_ranks_all_posts_and_spots_hand_posts(club_root):
    cfg = C.load(club_root / "club.yml")
    meta = {"key": "k", "kind": "match", "images": ["i"], "networks": ["facebook"], "stories": [], "sample": False}
    issue = {"closed_at": "2026-10-12T09:00:00Z",
             "body": "<!-- caption:start -->\n```text\n🏏 VICTORY for the 1st XI!\nmore\n```\n<!-- caption:end -->\n"
                     f"<!-- csk-post {json.dumps(meta)} -->"}
    r = RP.gather(cfg, FakeIns(), [issue], (2026, 10))
    c = r["committee"]
    assert [x["views"] for x in c["top"]] == [2300, 1200, 900]
    assert c["top"][0]["type"] == "Match results" and c["top"][1]["type"] == RP.BY_HAND
    assert c["kit"]["posts"] == 1 and c["hand"]["posts"] == 2
    text = RP.committee_text(c)
    assert "1. 🏏 VICTORY for the 1st XI! (Facebook" in text and "Posted by hand: 2 posts" in text
    assert "posts made by hand averaged 1,050 views" in text and "Automatic posts averaged" in text
    old = {"network": "Facebook", "text": "Win!\n\n#VerwoodCC #CricketDorset", "when": "2026-11-02T08:00:00+0000"}
    assert RP.post_type(old, {}, "#VerwoodCC #CricketDorset") == RP.OLDER
    assert RP.post_type({**old, "when": "2026-12-02T08:00:00+0000"}, {}, "#VerwoodCC #CricketDorset") == RP.BY_HAND
