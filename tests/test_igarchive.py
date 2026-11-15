import io
from datetime import datetime, timezone
from types import SimpleNamespace

from kit import igarchive as G

TAGS = "#VerwoodCC #CricketDorset #ClubCricket"


def test_names_and_graphics():
    when = datetime(2025, 7, 12, tzinfo=timezone.utc)
    assert G.safe_name(when, "Well done to our ladies A team! 🏏 #VerwoodCC\nmore") == \
        "2025-07-12 Well done to our ladies A team!.jpg"
    assert G.safe_name(when, "", 2) == "2025-07-12 photo 2.jpg"
    assert G.is_kit_graphic(f"🏆 Win!\n\n{TAGS}", TAGS) and not G.is_kit_graphic("Great day #VerwoodCC", TAGS)


def test_images_of_carousel_and_video():
    car = {"id": "1", "children": {"data": [{"id": "a", "media_type": "IMAGE", "media_url": "u1"},
                                            {"id": "b", "media_type": "VIDEO", "thumbnail_url": "t2"}]}}
    assert G.images_of(car) == [("a", "u1"), ("b", "t2")]
    assert G.images_of({"id": "2", "media_type": "IMAGE", "media_url": "u"}) == [("2", "u")]


def test_crops_without_faces_is_empty():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (40, 120, 40)).save(buf, "JPEG")
    assert G.crops(buf.getvalue()) == []


def test_run_saves_photos_skips_graphics_and_is_rerunnable(verwood, tmp_path):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 400), (200, 200, 200)).save(buf, "JPEG")
    posts = [{"id": "p1", "caption": "Three mum and daughter pairs", "timestamp": "2026-11-04T18:00:00+0000",
              "media_type": "IMAGE", "media_url": "https://x/1.jpg"},
             {"id": "p2", "caption": f"🏆 Win!\n\n{TAGS}", "timestamp": "2026-11-02T09:00:00+0000",
              "media_type": "IMAGE", "media_url": "https://x/2.jpg"},
             {"id": "p3", "caption": "Old", "timestamp": "2023-01-01T09:00:00+0000", "media_type": "IMAGE",
              "media_url": "https://x/3.jpg"}]

    class Meta:
        ig_id, page_token = "ig", "t"

        def resolve(self):
            pass

        def _call(self, method, path, token=None, **p):
            return {"data": posts, "paging": {}}

    ups = []
    sp = SimpleNamespace(drive=lambda site: "d", folder=lambda d, path: path,
                         upload=lambda d, parent, f, created=None: ups.append((parent, f.name, created)))
    get = lambda url, timeout=None: SimpleNamespace(status_code=200, content=buf.getvalue())
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    lines = G.run(verwood, {}, Meta(), get, sp, tmp_path, now=now)
    assert ups == [("Social media photos/Instagram archive/2026-11",
                    "2026-11-04 Three mum and daughter pairs.jpg", "2026-11-04T18:00:00Z")]
    assert "1 were club graphics" in lines[0]
    G.run(verwood, {}, Meta(), get, sp, tmp_path, now=now)
    assert len(ups) == 1   # already saved: skipped
