import os
from datetime import date, datetime

from kit import photoresults as PR
from kit import posts as P
from kit.matchphotos import MatchPhotos, fresh_photo


def photo(root, team, name, added):
    d = root / "match-photos" / team
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_bytes(b"x")
    t = datetime(*added, 12).timestamp()
    os.utime(f, (t, t))
    return f


def test_fresh_photo_is_from_the_game(verwood, tmp_path):
    verwood["photo_results"]["days_after"] = 3
    photo(tmp_path, "1st XI", "old.jpg", (2026, 10, 1))
    photo(tmp_path, "1st XI", "game.jpg", (2026, 10, 27))
    photo(tmp_path, "Club", "club.jpg", (2026, 10, 26))
    mp = MatchPhotos(tmp_path)
    assert fresh_photo(verwood, mp, "1st XI", date(2026, 10, 26)).name == "game.jpg"
    assert fresh_photo(verwood, mp, "1st XI", date(2026, 10, 20)) is None        # nothing within 3 days
    assert fresh_photo(verwood, mp, "2nd XI", date(2026, 10, 26)) is None        # never another team's folder
    assert fresh_photo(verwood, mp, "1st XI", date(2026, 10, 26), {"1st XI/game.jpg"}) is None


def test_lead_and_follow_up(verwood, pc, tmp_path):
    verwood["photo_results"].update(enabled=True, days_after=3)
    card = P.match_card(verwood, pc.match_detail("7700001"))   # 1st XI, 26 Oct 2026
    post = {"key": "match-7700001", "kind": "match", "data": card, "caption": P.caption_match(verwood, card)}
    used = {}
    PR.lead(verwood, [post], MatchPhotos(tmp_path), used)
    assert "lead_photo" not in card and used == {}                       # no photo yet: the usual graphic
    photo(tmp_path, "1st XI", "game.jpg", (2026, 10, 27))
    state = {"posted": {"match-7700001": {"made": "2026-10-27"}}, "photo_results": used}
    fu = PR.follow_ups(verwood, pc, MatchPhotos(tmp_path), state, date(2026, 10, 28), set())
    assert [p["key"] for p in fu] == ["photoresult-7700001"] and fu[0]["caption"].startswith("📸 From the game")
    assert used["7700001"] == {"photo": "1st XI/game.jpg", "how": "follow"}
    # remade on a later run (held until 10:00): same photo again
    fu2 = PR.follow_ups(verwood, pc, MatchPhotos(tmp_path), state, date(2026, 10, 28), set())
    assert fu2[0]["data"]["lead_photo"].endswith("game.jpg")


def test_junior_names_left_out_of_caption(verwood, pc, tmp_path):
    verwood["photo_results"].update(enabled=True)
    card = P.match_card(verwood, pc.match_detail("7700001"))
    card = {**card, "team": "Under 13", "date_obj": date(2026, 10, 26)}
    cap = P.caption_match(verwood, card)
    assert P.perf_line(card) in cap
    photo(tmp_path, "Under 13", "g.jpg", (2026, 10, 26))
    post = {"kind": "match", "data": card, "caption": cap}
    PR.lead(verwood, [post], MatchPhotos(tmp_path), {})
    assert post["data"]["lead_photo"] and P.perf_line(card) not in post["caption"]
