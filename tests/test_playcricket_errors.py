"""Play-Cricket sometimes briefly blocks requests with an HTML bot-check page: retry, don't blame the token."""
import pytest

from conftest import FakePlayCricketHTTP, Resp
from kit.playcricket import PlayCricket, PlayCricketError


class Seq:
    """Returns the given responses in order, then real test data."""
    def __init__(self, *responses):
        self.responses, self.fallback, self.calls, self.headers = list(responses), FakePlayCricketHTTP(), 0, {}

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0) if self.responses else self.fallback.get(url, params, timeout)


class Html(Resp):
    def __init__(self, status):
        super().__init__(status, {})
        self.text = "<html><title>ECB Error Page</title>Checking your browser before accessing</html>"
        self.headers = {"content-type": "text/html"}

    def json(self):
        raise ValueError("not json")


class TokenErr(Resp):
    def __init__(self):
        super().__init__(401, {"error": "Invalid api_token"})
        self.headers = {"content-type": "application/json"}


def test_temporary_bot_check_is_retried_not_blamed_on_token():
    waits = []
    http = Seq(Html(403), Html(200), Html(403))
    pc = PlayCricket("t", 8472, session=http, sleep=waits.append)
    from datetime import date
    assert pc.fixtures(date(2026, 10, 29), date(2026, 10, 29))  # got real data in the end
    assert waits == [5, 15, 30]


def test_real_token_problem_is_reported_straight_away():
    waits = []
    pc = PlayCricket("bad", 8472, session=Seq(TokenErr()), sleep=waits.append)
    with pytest.raises(PlayCricketError, match="refused the API token"):
        pc.match_detail(1)
    assert waits == []


def test_gives_up_with_a_reassuring_message():
    pc = PlayCricket("t", 8472, session=Seq(*[Html(403)] * 10), sleep=lambda s: None)
    with pytest.raises(PlayCricketError) as e:
        pc.match_detail(1)
    assert "usually temporary" in str(e.value) and "Nothing is posted twice" in str(e.value)


def test_identifies_itself_honestly():
    http = Seq()
    PlayCricket("t", 8472, session=http)
    assert http.headers["User-Agent"].startswith("CricketSocialKit/")
