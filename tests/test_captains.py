"""Captain's reports from the Microsoft Form, added to result posts."""
from datetime import date, datetime

from test_meta_review_run import FakeGitHub
from kit import captains as CR, config as C


def body(team="1st XI", day="2027-05-15", report="A great win. Ben bowled superbly. See https://x.com", potm="Ben T"):
    return (f"### Team\n\n{team}\n\n### Match date\n\n{day}\n\n### Captain\n\nSam Cole\n\n### Report\n\n{report}\n\n"
            f"### Player of the match\n\n{potm}\n")


class GH(FakeGitHub):
    def add(self, title, b, who="OWNER", created="2027-05-15"):
        n = len(self.issues) + 1
        self.issues[n] = {"number": n, "title": title, "body": b, "state": "open", "author_association": who,
                          "created_at": created + "T20:00:00Z", "user": {"login": "verwoodcc-social"}}
        self.labels[n], self.comments[n] = set(), []
        return n

    def _req(self, method, path, **kw):
        if path == "issues":
            return [self.get_issue(n) for n, i in self.issues.items() if i["state"] == "open"]
        return super()._req(method, path, **kw)


def post(team="1st XI", d=date(2027, 5, 15)):
    return {"kind": "match", "key": "match-1", "title": f"{team} v Opp", "data": {"team": team, "date_obj": d},
            "caption": "✅ Verwood won by 44 runs\n\nTop scores…\n\nSupported by Struan\n#VerwoodCC"}


def cfg(root):
    (root / "club.yml").write_text((root / "club.yml").read_text() + "\ncaptain_reports:\n  enabled: true\n")
    return C.load(root / "club.yml")


def test_report_added_to_result_caption(club_root):
    c, gh = cfg(club_root), GH()
    n = gh.add("Captain's report: 1st XI 15/05/2027", body())
    gh.add("Captain's report: spam", body(), who="NONE")  # not from the Power Automate connection: ignored
    reports = CR.load(c, gh, date(2027, 5, 16))
    assert len(reports) == 1
    made, notes = CR.attach(c, gh, [post()], reports, {}, datetime(2027, 5, 16, 7, 20))
    cap = made[0]["caption"]
    assert "🗣️ Captain's report – Sam Cole:" in cap and "“A great win. Ben bowled superbly. See”" in cap
    assert "⭐ Player of the match: Ben T" in cap and "https://" not in cap
    assert cap.index("Captain's report") < cap.index("Supported by Struan")  # before the sponsor line and tags
    assert made[0]["report_issue"] == n


def test_result_waits_for_a_report_then_goes(club_root):
    c, gh = cfg(club_root), GH()
    made, notes = CR.attach(c, gh, [post()], [], {}, datetime(2027, 5, 16, 7, 20))
    assert made == [] and "Waiting until 09:15" in notes[0]
    made, notes = CR.attach(c, gh, [post()], [], {}, datetime(2027, 5, 16, 9, 20))
    assert len(made) == 1 and "Captain's report" not in made[0]["caption"]
    made, _ = CR.attach(c, gh, [post(team="Under 13 A")], [], {}, datetime(2027, 5, 16, 7, 20))
    assert len(made) == 1  # junior results never wait


def test_bad_and_stale_reports_closed(club_root):
    c, gh = cfg(club_root), GH()
    bad = gh.add("Captain's report: x", body(day="sometime"))
    old = gh.add("Captain's report: old", body(day="2027-05-01"))
    reports = CR.load(c, gh, date(2027, 5, 16))
    CR.attach(c, gh, [], reports, {}, datetime(2027, 5, 16, 9, 30))
    assert gh.issues[bad]["state"] == "closed" and gh.issues[old]["state"] == "closed"
