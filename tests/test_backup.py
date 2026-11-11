"""Weekly backup: folders made once, files uploaded in chunks, only the newest weeks kept."""
from datetime import date

from kit import backup as B, config as C

ENV = {"M365_TENANT_ID": "t", "M365_CLIENT_ID": "c", "M365_CLIENT_SECRET": "s",
       "REPORT_EMAIL_FROM": "a@verwoodcc.co.uk", "REPORT_EMAIL_TO": "a@verwoodcc.co.uk"}


class R:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body
        self.content = b"x" if body is not None else b""
        self.headers = {"Content-Type": "application/json"}
        self.text = ""

    def json(self):
        return self._b


class Graph:
    def __init__(self, weeks=()):
        self.items = {"root": []}
        self.n = 0
        self.puts, self.deleted = [], []
        for w in weeks:
            self._mk("FOLDER", "Social media kit backups") if not self.items["root"] else None
        self.pre = list(weeks)

    def _mk(self, parent, name):
        self.n += 1
        i = {"id": f"i{self.n}", "name": name, "folder": {}}
        self.items.setdefault(parent, []).append(i)
        self.items[i["id"]] = []
        return i

    def post(self, url, data=None, timeout=None):  # token
        return R(200, {"access_token": "tok"})

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        if "/sites/" in url and url.endswith("/drive"):
            return R(200, {"id": "d1"})
        if "/sites/" in url:
            return R(200, {"id": "s1"})
        if url.endswith("/children") and method == "GET":
            parent = url.split("/items/")[1].split("/")[0]
            return R(200, {"value": self.items.get(parent, [])})
        if url.endswith("/children") and method == "POST":
            parent = url.split("/items/")[1].split("/")[0]
            i = self._mk(parent, json["name"])
            if json["name"] == "Social media kit backups":
                for w in self.pre:
                    self._mk(i["id"], w)
            return R(201, i)
        if "createUploadSession" in url:
            return R(200, {"uploadUrl": "https://upload/x"})
        if method == "DELETE":
            self.deleted.append(url.rsplit("/", 1)[1])
            return R(204)
        raise AssertionError(url)

    def put(self, url, data=None, timeout=None, headers=None):
        self.puts.append(headers["Content-Range"])
        return R(201, {"id": "f"})


def test_backup_uploads_and_keeps_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "CHUNK", 4)
    f = tmp_path / "verwood-social-2026-11-15.bundle"
    f.write_bytes(b"0123456789")
    cfg = C.load(C.ROOT / "club.yml")
    cfg["backup"]["keep"] = 2
    g = Graph(weeks=["2026-10-25", "2026-11-01", "2026-11-08"])
    lines = B.run(cfg, ENV, [f], today=date(2026, 11, 15), http=g)
    assert g.puts == ["bytes 0-3/10", "bytes 4-7/10", "bytes 8-9/10"]
    assert len(g.deleted) == 2 and "2026-10-25" in lines[-2] and "2026-11-01" in lines[-2]
    assert lines[0].startswith("- ✅ Saved **verwood-social-2026-11-15.bundle**")


def test_backup_needs_m365(tmp_path):
    f = tmp_path / "x.bundle"
    f.write_bytes(b"1")
    import pytest
    with pytest.raises(B.BackupError, match="isn't set up"):
        B.run(C.load(C.ROOT / "club.yml"), {}, [f])
