"""Expiry reminders: warn at each stage, once; close with a 'renewed' email when the key is replaced."""
from datetime import date, datetime, timezone

from test_alerts import GH, emails
from kit import config as C, expiry as X

TODAY = date(2026, 11, 6)


def cfg(**er):
    c = C.load(C.ROOT / "club.yml")
    c["expiry_reminders"].update(er)
    return c


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._b, self.headers = status, body or {}, headers or {}

    def json(self):
        return self._b


class Session:
    def __init__(self, meta_exp=0, data_exp=0, gh_exp=""):
        self.meta_exp, self.data_exp, self.gh_exp = meta_exp, data_exp, gh_exp

    def get(self, url, params=None, headers=None, timeout=None):
        if "debug_token" in url:
            return Resp(body={"data": {"is_valid": True, "expires_at": self.meta_exp,
                                       "data_access_expires_at": self.data_exp}})
        return Resp(headers={"GitHub-Authentication-Token-Expiration": self.gh_exp} if self.gh_exp else {})


def ts(d):
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp())


def test_stage():
    assert X.stage(date(2026, 12, 20), TODAY, [30, 7]) is None
    assert X.stage(date(2026, 11, 30), TODAY, [30, 7]) == 30
    assert X.stage(date(2026, 11, 10), TODAY, [30, 7]) == 7
    assert X.stage(None, TODAY, [30, 7]) is None


def test_never_expiring_tokens_are_quiet(monkeypatch):
    sent, gh = emails(monkeypatch), GH()
    env = {"META_TOKEN": "m", "PHOTOS_KEY": "p"}
    assert X.run(cfg(), gh, env, TODAY, Session()) == [] and sent == [] and not gh.issues
    lines = X.check_lines(cfg(), env, TODAY, Session())
    assert all(l.startswith("✅") for l in lines) and "never expires" in lines[0]


def test_warns_once_per_stage_then_closes_when_renewed(monkeypatch):
    sent, gh = emails(monkeypatch), GH()
    env = {"PHOTOS_KEY": "p"}
    s = Session(gh_exp="2026-11-30 00:00:00 UTC")
    X.run(cfg(), gh, env, TODAY, s)
    (n,) = gh.issues
    assert "player photos key expires 30 November 2026 (24 days)" in gh.issues[n]["title"] and len(sent) == 1
    X.run(cfg(), gh, env, TODAY, s)                          # next day: no second email
    assert len(sent) == 1 and len(gh.issues) == 1
    X.run(cfg(), gh, env, date(2026, 11, 25), s)             # 7-day stage: new reminder, old one closed quietly
    assert len(gh.issues) == 2 and gh.issues[n]["state"] == "closed" and len(sent) == 2
    m = max(gh.issues)
    X.run(cfg(), gh, env, date(2026, 11, 26), Session(gh_exp="2027-11-26 00:00:00 UTC"))   # renewed
    assert gh.issues[m]["state"] == "closed" and "renewed" in sent[-1][0] and len(sent) == 3


def test_meta_and_m365_dates(monkeypatch):
    sent, gh = emails(monkeypatch), GH()
    env = {"META_TOKEN": "m", "M365_CLIENT_SECRET": "s"}
    s = Session(meta_exp=0, data_exp=ts(date(2026, 11, 12)))
    lines = X.check_lines(cfg(m365_secret_expires=""), env, TODAY, s)
    assert any("data access" in l and l.startswith("⚠️") for l in lines)
    assert any("m365_secret_expires" in l for l in lines)       # date not yet in club.yml
    X.run(cfg(m365_secret_expires="2026-11-20"), gh, env, TODAY, s)
    titles = sorted(i["title"] for i in gh.issues.values())
    assert len(titles) == 2 and any("Microsoft 365 email secret expires 20 November 2026" in t for t in titles)


def test_config_validation():
    c = cfg(warn_days="soon", m365_secret_expires="next year")
    import pytest
    with pytest.raises(C.ConfigError) as e:
        C.validate(c)
    assert "warn_days" in str(e.value) and "m365_secret_expires" in str(e.value)
