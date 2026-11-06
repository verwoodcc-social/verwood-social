"""Club news and events: a committee member fills in the 'Club news or event' form (a GitHub issue
form), the kit turns it into a branded post + story, and opens it for approval like any other post.

- Always previewed first, even when match posts are automatic.
- 'Post on' date: approve any time; it goes out with that morning's run.
- Events with a date get a 'Today' reminder Story on the morning of the event.
- Only people with access to this repository can use the form (anyone else's issue is ignored).
"""
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from .posts import _tags, long_date, short_date

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
KINDS = {"Event": ("📅", "Event"), "News": ("📣", "Club news"), "Notice": ("📌", "Notice")}
NO_ANSWER = {"", "_no response_", "none", "n/a"}
FIELDS = {
    "headline": "Headline",
    "type": "What kind of post is it?",
    "event_date": "Event date",
    "time": "Start time",
    "venue": "Venue",
    "details": "Details",
    "strap": "One line for the graphic",
    "link": "Link",
    "post_on": "Post on",
    "photo": "Photo",
}
PHOTO_HOSTS = ("github.com", "user-images.githubusercontent.com", "private-user-images.githubusercontent.com",
               "githubusercontent.com")


class FormError(ValueError):
    pass


def parse_form(body):
    """{label: answer} from a GitHub issue form body (### Label / answer sections)."""
    out = {}
    for block in re.split(r"^###\s+", body or "", flags=re.M)[1:]:
        label, _, answer = block.partition("\n")
        answer = answer.strip()
        out[label.strip()] = "" if answer.lower() in NO_ANSWER else answer
    return out


def field(form, key):
    return (form.get(FIELDS[key]) or "").strip()


DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%A %d %B %Y",
                "%a %d %b %Y", "%d.%m.%Y")


def parse_day(text, today):
    """A date from what someone typed: 14/03/2027, 14 March 2027, 14/3 (next one), Saturday 14 March."""
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", (text or "").strip(), flags=re.I)
    t = re.sub(r"\s+", " ", t.replace(",", " ")).strip()
    if not t:
        return None
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            pass
    for f in ("%d/%m", "%d %B", "%d %b", "%A %d %B", "%a %d %b"):  # no year: the next one
        try:
            d = datetime.strptime(f"{t} {today.year}", f + " %Y").date()
        except ValueError:
            continue
        return d if d >= today else d.replace(year=today.year + 1)
    raise FormError(f"I couldn't read the date “{text}”. Please write it like 14/03/2027.")


def tidy_time(text):
    t = (text or "").strip()
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", t)
    if m and int(m.group(1)) < 24:
        h, mi = int(m.group(1)), m.group(2)
        return f"{(h - 1) % 12 + 1}:{mi}{'am' if h < 12 else 'pm'}"
    return t


def photo_url(text):
    """First image URL in the Photo answer, if it's a GitHub upload."""
    for u in re.findall(r"!\[[^\]]*\]\((\S+?)\)|<img[^>]+src=\"([^\"]+)\"", text or ""):
        url = next(x for x in u if x)
        host = urlparse(url).hostname or ""
        if urlparse(url).scheme == "https" and any(host == h or host.endswith("." + h) for h in PHOTO_HOSTS):
            return url
    return None


def download_photo(url, session, folder):
    """Save an attached photo for drawing into the graphic. Returns a path, or None if it isn't an image."""
    from PIL import Image

    r = session.get(url, timeout=60)
    if r.status_code != 200 or len(r.content) > 25_000_000:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    f = Path(tempfile.mkstemp(dir=folder, suffix=".img")[1])
    f.write_bytes(r.content)
    try:
        with Image.open(f) as im:
            im.verify()
    except Exception:
        f.unlink(missing_ok=True)
        return None
    return f


def blurb(strap, details, limit=170):
    """What goes on the graphic: the strapline, or the start of the details."""
    text = strap or re.split(r"\n\s*\n", details.strip())[0]
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sentence = cut.rfind(". ")
    return cut[:sentence + 1] if sentence > 60 else cut.rsplit(" ", 1)[0] + "…"


def build(cfg, form, number, today, photo=None):
    """A post dict (kind 'news') from a filled-in form. Raises FormError with a friendly message."""
    headline = field(form, "headline")
    details = field(form, "details")
    if not headline:
        raise FormError("The headline is empty.")
    if not details:
        raise FormError("The details are empty.")
    if len(headline) > 70:
        raise FormError(f"The headline is {len(headline)} characters. Please keep it to 70 or fewer so it fits.")
    kind = field(form, "type") or "News"
    emoji, kicker = KINDS.get(kind, KINDS["News"])
    event_day = parse_day(field(form, "event_date"), today)
    post_on = parse_day(field(form, "post_on"), today)
    if post_on and post_on < today:
        raise FormError(f"The “Post on” date ({long_date(post_on)}) has already passed. "
                        "Leave it empty to post as soon as it's approved.")
    if event_day and event_day < today:
        raise FormError(f"The event date ({long_date(event_day)}) has already passed.")
    if event_day and post_on and post_on > event_day:
        raise FormError("The “Post on” date is after the event.")
    time = tidy_time(field(form, "time"))
    venue = field(form, "venue")
    link = field(form, "link")
    when = " · ".join(x for x in (long_date(event_day) if event_day else "", time) if x)
    data = {"kind": "news", "kicker": kicker, "headline": headline, "when": when, "venue": venue,
            "blurb": blurb(field(form, "strap"), details), "bg_photo": str(photo) if photo else "",
            "link": link}
    lines = [f"{emoji} {headline}", "", details.strip()]
    facts = [f"🗓️ {when}" if when else "", f"📍 {venue}" if venue else "", f"🔗 {link}" if link else ""]
    facts = [f for f in facts if f]
    if facts:
        lines += [""] + facts
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    post = {"key": f"news-{number}-{stamp}", "kind": "news", "title": f"{kicker}: {headline}", "data": data,
            "caption": "\n".join(lines) + _tags(cfg),
            "alt": f"{cfg['club']['name']} {kicker.lower()}: {headline}." + (f" {when}." if when else "")
                   + (f" At {venue}." if venue else ""),
            "review": True, "source_issue": number,
            "post_on": post_on.isoformat() if post_on else ""}
    news = cfg["news"]
    if event_day and news.get("reminder") and event_day > (post_on or today):
        post["reminder_date"] = event_day.isoformat()
        post["reminder_data"] = {**data, "kicker": news.get("reminder_title") or "Today",
                                 "when": time or short_date(event_day), "today": True}
    return post


def schedule_note(post):
    out = []
    if post.get("post_on"):
        d = date.fromisoformat(post["post_on"])
        out.append(f"🗓️ **Goes out on {long_date(d)}** with the morning run (about 6:20am), once approved. "
                   "You can approve it any time before then.")
    if post.get("reminder"):
        d = date.fromisoformat(post["reminder"]["date"])
        out.append(f"⏰ **Reminder Story** on the morning of the event ({long_date(d)}).")
    return "\n".join(out)
