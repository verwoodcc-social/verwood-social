"""SharePoint photo store: folders named as on Play-Cricket, photos copied in, Under = U when matching."""
from kit import config as C, photostore as PS
from kit.matchphotos import MatchPhotos, _key
from test_backup import ENV, R


class Graph:
    """A tiny drive: Social media photos/match-photos/1st XI/a.jpg and notes.txt."""
    def __init__(self):
        self.tree = {"root": [{"id": "s", "name": "Social media photos", "folder": {}}],
                     "s": [{"id": "m", "name": "match-photos", "folder": {}}, {"id": "c", "name": "To check", "folder": {}}],
                     "c": [{"id": "f9", "name": "emailed.jpg", "file": {}}],
                     "m": [{"id": "t", "name": "1st XI", "folder": {}}],
                     "t": [{"id": "f1", "name": "a.jpg", "file": {}},
                           {"id": "f2", "name": "notes.txt", "file": {}, "@microsoft.graph.downloadUrl": "https://dl/n"}]}
        self.made = []

    def post(self, url, data=None, timeout=None):
        return R(200, {"access_token": "tok"})

    def get(self, url, timeout=None, headers=None):
        r = R(200, {})
        r.content = b"JPEG"
        return r

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        if url.endswith("/drive"):
            return R(200, {"id": "d"})
        if "/sites/" in url:
            return R(200, {"id": "site"})
        parent = url.split("/items/")[1].split("/")[0]
        if method == "GET":
            return R(200, {"value": self.tree.get(parent, [])})
        i = {"id": f"n{len(self.made)}", "name": json["name"], "folder": {}}
        self.tree.setdefault(parent, []).append(i)
        self.made.append(json["name"])
        return R(201, i)


def cfg():
    c = C.load(C.ROOT / "club.yml")
    c["photo_store"]["teams"] = ["1st XI", "Under 12 Indoor"]
    return c


def test_sync_copies_only_photos(tmp_path):
    n = PS.sync(cfg(), ENV, tmp_path, http=Graph())
    assert n == 1 and (tmp_path / "match-photos" / "1st XI" / "a.jpg").read_bytes() == b"JPEG"
    assert not (tmp_path / "match-photos" / "1st XI" / "notes.txt").exists()


def test_make_folders_adds_missing_only():
    g = Graph()
    made = PS.make_folders(cfg(), ENV, http=g)
    assert "match-photos/1st XI" not in made
    assert {"match-photos/Under 12 Indoor", "match-photos/Indoor", "match-photos/Juniors", "match-photos/Club",
            "adults", "juniors"} <= set(made) and "To check" not in made  # already there


def test_under_and_u_are_the_same_team(tmp_path):
    (tmp_path / "match-photos" / "Under 12 Indoor").mkdir(parents=True)
    (tmp_path / "match-photos" / "Under 12 Indoor" / "x.jpg").write_bytes(b"x")
    mp = MatchPhotos(tmp_path)
    c = C.load(C.ROOT / "club.yml")
    assert mp.folder_for(c, "U12 Indoor")[0] == "Under 12 Indoor"
    assert _key("Girls Under 11 A") == _key("Girls U11 A")
