"""Render post data into 1080x1350 JPEG graphics (Instagram requires JPEG)."""
import base64
import math
import mimetypes
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

HERE = Path(__file__).resolve().parent
ROWS_PER_PAGE = 6
STORY_ROWS_PER_PAGE = 7
SIZES = {False: (1080, 1350), True: (1080, 1920)}  # feed post, story
FONT_WEIGHTS = {"Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800, "Black": 900}


def _data_uri(path, max_px=None):
    """Embed a file in the page. Big photos are shrunk first so rendering stays quick."""
    path = Path(path)
    if max_px and path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        try:
            import io
            from PIL import Image, ImageOps
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)  # respect phone photo rotation
                im.thumbnail((max_px, max_px))
                buf = io.BytesIO()
                if im.mode in ("RGBA", "LA", "P"):
                    im.save(buf, "PNG")
                    mime = "image/png"
                else:
                    im.convert("RGB").save(buf, "JPEG", quality=88)
                    mime = "image/jpeg"
            return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if path.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _template_dirs(cfg):
    """A club's own designs in my-templates/ take priority over the kit's."""
    own = cfg.root / "my-templates"
    return ([own] if own.is_dir() else []) + [HERE / "templates"]


def _css(cfg):
    from .config import overlay
    fonts = []
    for name, weight in FONT_WEIGHTS.items():
        f = HERE / f"fonts/InterDisplay-{name}.otf"
        if f.exists():
            fonts.append(f'@font-face{{font-family:"KitFont";font-weight:{weight};'
                         f'src:url({_data_uri(f)}) format("opentype");}}')
    pal = cfg.palette()
    vars_ = {**pal, **overlay(pal, cfg["branding"].get("background_darkness", "medium"))}
    root = ":root{" + "".join(f"--{k}:{v};" for k, v in vars_.items()) + "}"
    own = cfg.root / "my-templates"
    base = (own / "base.css") if (own / "base.css").exists() else (HERE / "templates/base.css")
    extra = (own / "extra.css").read_text() if (own / "extra.css").exists() else ""
    return "\n".join(fonts) + "\n" + root + "\n" + base.read_text() + "\n" + extra


def _common(cfg, kind, data=None):
    b = cfg["branding"]
    bg = (data or {}).get("bg_photo")
    photo = Path(bg) if bg and Path(bg).exists() else cfg.background_for(kind)
    sponsor_logo = cfg.image("sponsor_logo")
    return {
        "css": _css(cfg), "badge": _data_uri(cfg.badge_path(), max_px=400),
        "photo": _data_uri(photo, max_px=1600) if photo else "",
        "club": {"name": cfg["club"]["name"], "short_name": cfg.short_name,
                 "handle": cfg["club"].get("handle", ""), "website": cfg["club"].get("website", "")},
        "sponsor": {"logo": _data_uri(sponsor_logo, max_px=600) if sponsor_logo else "",
                    "text": (b.get("sponsor_text") or "").strip(), "label": (b.get("sponsor_label") or "").strip()},
        "words": cfg.words(), "show": cfg["show"], "wording": cfg["wording"],
    }


def pages_html(cfg, data, story=False):
    env = Environment(loader=FileSystemLoader(_template_dirs(cfg)), autoescape=True)
    if data["kind"] == "match":
        return [env.get_template("match.html").render(m=data, pages=1, page=1, story=story, **_common(cfg, "match", data))]
    if data["kind"] == "leaderboards":
        tpl = env.get_template("leaderboards.html")
        common = _common(cfg, "leaderboards", data)
        n = len(data["boards"])
        return [tpl.render(d=data, b=b, page=i, pages=n, story=story, **common)
                for i, b in enumerate(data["boards"], 1)]
    if data["kind"] == "news":
        return [env.get_template("news.html").render(m=data, pages=1, page=1, story=story,
                                                    **_common(cfg, "news", data))]
    if data["kind"] == "milestone":
        pp = data.get("photo_path")
        player_photo = _data_uri(pp, max_px=1400) if pp and Path(pp).exists() else ""
        return [env.get_template("milestone.html").render(m=data, pages=1, page=1, story=story,
                                                         player_photo=player_photo, **_common(cfg, "match", data))]
    common = _common(cfg, data["kind"], data)
    rows = data["matches"]
    if not rows:
        return []
    pages = math.ceil(len(rows) / (STORY_ROWS_PER_PAGE if story else ROWS_PER_PAGE))
    per = math.ceil(len(rows) / pages)  # spread rows evenly
    tpl = env.get_template("list.html")
    return [tpl.render(kind=data["kind"], title=data["title"], date_range=data["date_range"],
                       rows=rows[i * per:(i + 1) * per], page=i + 1, pages=pages, story=story,
                       cta=data.get("cta", ""), **common)
            for i in range(pages)]


class Renderer:
    """Keeps one browser open while rendering several posts."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(viewport={"width": 1080, "height": 1350})
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def render(self, cfg, data, out_dir, stem, story=False):
        """Feed graphics (1080x1350), or story graphics (1080x1920) when story=True."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        w, h = SIZES[bool(story)]
        self._page.set_viewport_size({"width": w, "height": h})
        stem = f"{stem}-story" if story else stem
        files = []
        htmls = pages_html(cfg, data, story=story)
        for i, html in enumerate(htmls, 1):
            self._page.set_content(html, wait_until="load")
            self._page.evaluate("document.fonts.ready")
            name = f"{stem}.jpg" if len(htmls) == 1 else f"{stem}_{i}.jpg"
            f = out_dir / name
            self._page.screenshot(path=str(f), type="jpeg", quality=92, clip={"x": 0, "y": 0, "width": w, "height": h})
            files.append(f)
        return files


def report_html(cfg, r):
    """The monthly sponsor report page (A4)."""
    from .config import overlay
    from .report import fmt
    env = Environment(loader=FileSystemLoader(_template_dirs(cfg)), autoescape=True)
    fonts = []
    for name, weight in FONT_WEIGHTS.items():
        f = HERE / f"fonts/InterDisplay-{name}.otf"
        if f.exists():
            fonts.append(f'@font-face{{font-family:"KitFont";font-weight:{weight};'
                         f'src:url({_data_uri(f)}) format("opentype");}}')
    pal = cfg.palette()
    root = ":root{" + "".join(f"--{k}:{v};" for k, v in pal.items()) + "}"
    common = _common(cfg, "report")
    return env.get_template("report.html").render(fonts="".join(fonts) + root, r=r, fmt=fmt, badge=common["badge"],
                                                  club=common["club"], sponsor=common["sponsor"])


def render_report(cfg, r, out_dir, stem):
    """PDF (A4) and a preview JPEG of the sponsor report. Returns (pdf, jpg)."""
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html = report_html(cfg, r)
    pdf, jpg = out_dir / f"{stem}.pdf", out_dir / f"{stem}.jpg"
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=2)
        page.set_content(html, wait_until="load")
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(jpg), type="jpeg", quality=90, clip={"x": 0, "y": 0, "width": 794, "height": 1123})
        page.pdf(path=str(pdf), format="A4", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        b.close()
    return pdf, jpg
