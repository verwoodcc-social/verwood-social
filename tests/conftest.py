import json
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = Path(__file__).resolve().parent / "data"

from kit import config as C  # noqa: E402
from kit.playcricket import PlayCricket, parse_date  # noqa: E402


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.content = json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class FakePlayCricketHTTP:
    """Serves tests/data/*.json like the Play-Cricket API (incl. server-side match-date filtering)."""

    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        name = urlparse(url).path.rsplit("/", 1)[-1]
        if name == "match_detail.json":
            f = DATA / f"match_detail_{params['match_id']}.json"
            return Resp(200, json.loads(f.read_text())) if f.exists() else Resp(200, {"match_details": []})
        body = json.loads((DATA / name).read_text())
        if name == "result_summary.json" and "from_match_date" in params:
            a, b = parse_date(params["from_match_date"]), parse_date(params["end_match_date"])
            body["result_summary"] = [m for m in body["result_summary"] if a <= parse_date(m["match_date"]) <= b]
        return Resp(200, body)


@pytest.fixture
def verwood():
    return C.load(ROOT / "examples/verwood/club.yml")


@pytest.fixture
def pc():
    return PlayCricket("test-token", 8472, session=FakePlayCricketHTTP())


@pytest.fixture
def club_root(tmp_path):
    """A temporary club repository using the Verwood example settings."""
    shutil.copy(ROOT / "examples/verwood/club.yml", tmp_path / "club.yml")
    shutil.copy(ROOT / "examples/verwood/badge.svg", tmp_path / "badge.svg")
    (tmp_path / "state").mkdir()
    return tmp_path
