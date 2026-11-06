"""Match photos as backgrounds: team folder, then Indoor / Juniors, then Club; rotating."""
from datetime import date

from kit import config as C
from kit.matchphotos import MatchPhotos, add_backgrounds


def store(tmp_path, folders):
    for folder, names in folders.items():
        d = tmp_path / "match-photos" / folder
        d.mkdir(parents=True)
        for n in names:
            (d / n).write_bytes(b"x")
    return tmp_path


def cfg(club_root):
    return C.load(club_root / "club.yml")


def test_folder_choice(club_root, tmp_path):
    c = cfg(club_root)
    mp = MatchPhotos(store(tmp_path, {"1st XI": ["a.jpg"], "Indoor": ["i.jpg"], "Juniors": ["j.jpg"], "Club": ["c.jpg"]}))
    assert mp.folder_for(c, "1st XI")[0] == "1st XI"
    assert mp.folder_for(c, "Indoor C")[0] == "Indoor"
    assert mp.folder_for(c, "Under 13 A")[0] == "Juniors"
    assert mp.folder_for(c, "U11 Indoor")[0] == "Juniors"
    assert mp.folder_for(c, "2nd XI")[0] == "Club"
    assert len(mp) == 4


def test_rotates_least_recently_used(club_root, tmp_path):
    c = cfg(club_root)
    used = {}
    mp = MatchPhotos(store(tmp_path, {"1st XI": ["a.jpg", "b.jpg", "c.jpg"]}), used)
    picks = [mp.pick(c, "1st XI", f"match-{i}", date(2026, 5, i + 1)).name for i in range(3)]
    assert sorted(picks) == ["a.jpg", "b.jpg", "c.jpg"]  # all three used before any repeats
    assert used and all(v.startswith("2026-05") for v in used.values())


def test_add_backgrounds(club_root, tmp_path):
    c = cfg(club_root)
    mp = MatchPhotos(store(tmp_path, {"Club": ["c.jpg"], "1st XI": ["a.jpg"]}))
    made = [{"key": "match-1", "kind": "match", "data": {"team": "1st XI"}},
            {"key": "milestone-1", "kind": "milestone", "data": {"team": "1st XI", "photo_path": "/p.jpg"}},
            {"key": "roundup-1", "kind": "roundup", "data": {"matches": []}},
            {"key": "fixtures-1", "kind": "fixtures", "data": {"matches": []}}]
    add_backgrounds(c, made, mp, date(2026, 5, 1))
    assert made[0]["data"]["bg_photo"].endswith("1st XI/a.jpg")
    assert "bg_photo" not in made[1]["data"]  # player photo already used
    assert made[2]["data"]["bg_photo"].endswith("Club/c.jpg")
    assert "bg_photo" not in made[3]["data"]  # fixtures not chosen


def test_no_store_is_fine(club_root, tmp_path):
    made = [{"key": "match-1", "kind": "match", "data": {"team": "1st XI"}}]
    add_backgrounds(cfg(club_root), made, MatchPhotos(tmp_path / "missing"), date(2026, 5, 1))
    assert "bg_photo" not in made[0]["data"]
