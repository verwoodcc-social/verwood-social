"""Photo-led result posts (club.yml → photo_results).

When a photo from the game is in the team's own folder (added on the day of the game or up to days_after
later, e.g. emailed in and moved out of To check), the result is posted as that photo, full size, with the
score in a banner, instead of the usual graphic. If the photo arrives after the result has gone out, a
"From the game" post follows with it, once per game.

The graphic never shows player names. The caption keeps the usual "top-scored with" line (junior names
shortened as usual); photo_results → junior_names_in_caption: false takes it out for junior teams.
"""
from datetime import date, timedelta

from . import posts as P
from .matchphotos import fresh_photo
from .playcricket import PlayCricketError


def _no_names(cfg, card, caption):
    line = P.perf_line(card)
    if cfg.is_junior(card["team"]) and line and not cfg["photo_results"].get("junior_names_in_caption", True):
        caption = caption.replace("\n" + line, "")
    return caption


def _taken(used, but=None):
    return {v["photo"] for k, v in used.items() if k != but}


def _photo(photos, rel):
    f = photos.root / rel
    return f if f.is_file() else None


def lead(cfg, made, photos, used):
    """Give today's result posts a photo from the game when there is one.
    used: {match id: {"photo": path in match-photos, "how": "lead" | "follow"}} (state → photo_results)."""
    if not cfg["photo_results"]["enabled"] or not photos:
        return
    for p in made:
        d = p["data"]
        if p["kind"] != "match" or not d.get("date_obj"):
            continue
        mid = str(d["id"])
        prev = used.get(mid)
        f = _photo(photos, prev["photo"]) if prev and prev["how"] == "lead" else None  # remade: same photo
        if not f and not prev:
            f = fresh_photo(cfg, photos, d["team"], d["date_obj"], _taken(used))
        if f:
            used[mid] = {"photo": str(f.relative_to(photos.root)), "how": "lead"}
            d["lead_photo"] = str(f)
            p["caption"] = _no_names(cfg, d, p["caption"])


def follow_ups(cfg, pc, photos, state, today, made_keys):
    """'From the game' posts for results already posted in the last few days, when a photo has arrived since."""
    pr = cfg["photo_results"]
    if not pr["enabled"] or not pr["follow_up"] or not photos:
        return []
    used = state.setdefault("photo_results", {})
    out = []
    since = today - timedelta(days=int(pr["days_after"]) + 1)
    for key, v in sorted(state["posted"].items()):
        if not key.startswith("match-") or key in made_keys:
            continue
        mid = key[len("match-"):]
        prev = used.get(mid)
        if (prev and prev["how"] == "lead") or f"photoresult-{mid}" in state["posted"]:
            continue
        if not prev and (v.get("made") or "") < since.isoformat():
            continue
        try:
            card = P.match_card(cfg, pc.match_detail(mid))
        except PlayCricketError:
            continue
        if not card:
            continue
        f = _photo(photos, prev["photo"]) if prev else \
            fresh_photo(cfg, photos, card["team"], card["date_obj"], _taken(used))
        if not f:
            continue
        used[mid] = {"photo": str(f.relative_to(photos.root)), "how": "follow"}
        card["lead_photo"] = str(f)
        cap = _no_names(cfg, card, P.caption_match(cfg, card))
        out.append({"key": f"photoresult-{mid}", "kind": "match",
                    "title": f"From the game: {card['team']} v {card['opponent']} ({P.short_date(card['date_obj'])})",
                    "data": card, "caption": "📸 From the game\n\n" + cap, "alt": P.alt_match(cfg, card),
                    "match_id": mid})
    return out
