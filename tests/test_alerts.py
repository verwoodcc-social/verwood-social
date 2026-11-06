"""Problem alerts: one issue per problem, emailed once, closed (and 'fixed' emailed) when it works again."""
from argparse import Namespace

from test_meta_review_run import FakeGitHub, meta
from kit import alerts, run as R


class GH(FakeGitHub):
    def create_issue(self, title, body, labels=("social-post",)):
        i = super().create_issue(title, body, labels)
        i["html_url"] = f"https://github.com/x/issues/{i['number']}"
        return i

    def open_issues(self, label):
        return [self.get_issue(n) for n, i in self.issues.items() if i["state"] == "open" and label in self.labels[n]]

    def ensure_labels(self):
        pass


def emails(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "_email", lambda subject, text: sent.append((subject, text)) or True)
    return sent


def test_problem_emailed_once_then_fixed(monkeypatch):
    sent, gh = emails(monkeypatch), GH()
    n = alerts.problem(gh, "sponsor-report", "The monthly sponsor report couldn't be made", "❌ Meta said no", "run1")
    assert gh.labels[n] == {"problem"} and len(sent) == 1 and sent[0][0].startswith("⚠️ VCC social media:")
    assert alerts.problem(gh, "sponsor-report", "The monthly sponsor report couldn't be made", "", "run2") == n
    assert len(sent) == 1 and "Still happening: run2" in gh.comments[n][-1]["body"]
    assert alerts.resolved(gh, "sponsor-report") == [n]
    assert gh.issues[n]["state"] == "closed" and sent[-1][0].startswith("✅ VCC social media: fixed")


def test_quiet_first_only_emails_if_it_happens_again(monkeypatch):
    sent, gh = emails(monkeypatch), GH()
    n = alerts.problem(gh, "make-posts", "The daily posts didn't run", "x", "run1", quiet_first=True)
    assert sent == []
    alerts.resolved(gh, "make-posts")  # 8am run worked: closed quietly
    assert gh.issues[n]["state"] == "closed" and sent == []
    m = alerts.problem(gh, "make-posts", "The daily posts didn't run", "x", "run3", quiet_first=True)
    alerts.problem(gh, "make-posts", "The daily posts didn't run", "x", "run4", quiet_first=True)
    assert m != n and len(sent) == 1


def test_failed_post_raises_and_retry_clears(monkeypatch, club_root):
    sent = emails(monkeypatch)
    gh = GH()
    from test_stories import enable_stories
    enable_stories(club_root)
    R.cmd_make(Namespace(today="2026-10-26", only="matches"), root=club_root,
               pc=__import__("test_meta_review_run").pc(), renderer=__import__("test_meta_review_run").FakeRenderer())
    R.cmd_announce(Namespace(sha="abc"), root=club_root, gh=gh)
    gh.add_labels(1, ["approved"])
    assert R.cmd_publish(Namespace(issue=1), root=club_root, gh=gh, meta=meta(fail_on="photo_stories")) is False
    probs = [n for n in gh.issues if "problem" in gh.labels[n]]
    assert len(probs) == 1 and len(sent) == 1 and "Facebook Stories" in sent[0][1]
    gh.add_labels(1, ["approved"])
    R.cmd_publish(Namespace(issue=1), root=club_root, gh=gh, meta=meta())
    assert gh.issues[probs[0]]["state"] == "closed" and sent[-1][0].startswith("✅")


def test_alert_command_reads_the_run_log(monkeypatch, club_root):
    sent, gh = emails(monkeypatch), GH()
    (club_root / R.RUN_LOG).write_text("## Something needs attention\n\n❌ Play-Cricket said the token is wrong\n")
    R.cmd_alert(Namespace(key="make-posts", title="The daily posts didn't run", link="L", quiet_first=False),
                root=club_root, gh=gh)
    assert "Play-Cricket said the token is wrong" in sent[0][1] and "L" in sent[0][1]


def test_alerts_never_raise():
    class Broken:
        def open_issues(self, label):
            raise RuntimeError("GitHub down")
    assert alerts.problem(Broken(), "k", "t") is None and alerts.resolved(Broken(), "k") == []
