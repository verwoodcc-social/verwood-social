"""Render post data into 1080x1350 JPEG graphics (Instagram requires JPEG)."""
import base64
import math
import mimetypes
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

HERE = Path(__file__).resolve().parent
ROWS_PER_PAGE = 6
FONT_WEIGHTS = {"Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800, "Black": 900}


def _data_uri(path):
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if path.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _css(cfg):
    fonts = []
    for name, weight in FONT_WEIGHTS.items():
        f = HERE / f"fonts/InterDisplay-{name}.otf"
        if f.exists():
            fonts.append(f'@font-face{{font-family:"KitFont";font-weight:{weight};'
                         f'src:url({_data_uri(f)}) format("opentype");}}')
    pal = ":root{" + "".join(f"--{k}:{v};" for k, v in cfg.palette().items()) + "}"
    return "\n".join(fonts) + "\n" + pal + "\n" + (HERE / "templates/base.css").read_text()


def pages_html(cfg, data):
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
    common = {"css": _css(cfg), "badge": _data_uri(cfg.badge_path()),
              "club": {"name": cfg["club"]["name"], "short_name": cfg.short_name,
                       "handle": cfg["club"].get("handle", ""), "website": cfg["club"].get("website", "")}}
    if data["kind"] == "match":
        return [env.get_template("match.html").render(m=data, **common)]
    rows = data["matches"]
    if not rows:
        return []
    pages = math.ceil(len(rows) / ROWS_PER_PAGE)
    per = math.ceil(len(rows) / pages)  # spread rows evenly
    tpl = env.get_template("list.html")
    return [tpl.render(kind=data["kind"], title=data["title"], date_range=data["date_range"],
                       rows=rows[i * per:(i + 1) * per], page=i + 1, pages=pages, **common)
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

    def render(self, cfg, data, out_dir, stem):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        htmls = pages_html(cfg, data)
        for i, html in enumerate(htmls, 1):
            self._page.set_content(html, wait_until="load")
            self._page.evaluate("document.fonts.ready")
            name = f"{stem}.jpg" if len(htmls) == 1 else f"{stem}_{i}.jpg"
            f = out_dir / name
            self._page.screenshot(path=str(f), type="jpeg", quality=92,
                                  clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
            files.append(f)
        return files
