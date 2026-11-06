"""Expiry reminders: warn the committee before a key the kit depends on runs out.

Checked every morning (make-posts) and shown in Check setup:
- META_TOKEN: asked of Meta itself (debug_token). A system-user or Page token from a long-lived login
  usually never expires; a normal login token lasts about 60 days. Meta also stops data access (the
  reach report) 90 days after the token was last re-authorised.
- PLAYER_PHOTOS_TOKEN: GitHub says when a personal access token expires (a response header).
- M365_CLIENT_SECRET: Microsoft doesn't let the kit read this, so its date goes in club.yml
  (expiry_reminders → m365_secret_expires), copied from Entra → App registrations → Certificates & secrets.
- The Play-Cricket token doesn't expire.

A warning opens a 'problem' issue and emails once at each stage (warn_days, e.g. 30 then 7 days before).
When the key is renewed the issue closes itself with a short "renewed" email.
If the Microsoft 365 secret itself has expired no email can be sent, but the issue still opens, and GitHub
emails the repository owner about new issues.
"""
import logging
from datetime import date, datetime, timezone

import requests

from . import alerts

log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v21.0"

HOW = {
    "meta": "Make a new token (setup guide, step 4) and update the META_TOKEN secret. A Meta Business "
            "'system user' token never expires, so that's the best kind to use.",
    "meta-data": "Regenerate the Meta token (setup guide, step 4) and update META_TOKEN. Posting still works "
                 "until then, but the monthly reach report can't read the figures.",
    "photos": "Make a new fine-grained token for the verwood-player-photos repository (Contents: read) and "
              "update the PLAYER_PHOTOS_TOKEN secret. Posts carry on without photos until it's renewed.",
    "m365": "In Microsoft Entra → App registrations → the kit's app → Certificates & secrets, add a new client "
            "secret, update the M365_CLIENT_SECRET secret, then change expiry_reminders → m365_secret_expires "
            "in club.yml to the new date. Without it, reports and alerts can't be emailed.",
}
NAMES = {"meta": "Meta (Facebook/Instagram) token", "meta-data": "Meta token's data access",
         "photos": "player photos key", "m365": "Microsoft 365 email secret"}


def _day(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).date() if ts else None


def meta_dates(token, session=None):
    """{'meta': date|None, 'meta-data': date|None} (None = never), or raises RuntimeError."""
    http = session or requests
    try:
        r = http.get(f"{GRAPH}/debug_token", params={"input_token": token, "access_token": token}, timeout=30)
        d = r.json().get("data") or {}
    except (requests.RequestException, ValueError) as e:
        raise RuntimeError(f"couldn't ask Meta ({e.__class__.__name__})")
    if not d:
        raise RuntimeError("Meta didn't say")
    if d.get("is_valid") is False:
        return {"meta": date.min, "meta-data": None}
    return {"meta": _day(d.get("expires_at")), "meta-data": _day(d.get("data_access_expires_at"))}


def github_token_date(token, session=None):
    """Expiry date of a GitHub token, None if it never expires, date.min if already invalid."""
    http = session or requests
    try:
        r = http.get("https://api.github.com/user", timeout=30,
                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    except requests.RequestException as e:
        raise RuntimeError(f"couldn't reach GitHub ({e.__class__.__name__})")
    if r.status_code == 401:
        return date.min
    raw = r.headers.get("GitHub-Authentication-Token-Expiration") or ""
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def m365_date(cfg):
    v = str(cfg["expiry_reminders"].get("m365_secret_expires") or "").strip()
    return datetime.strptime(v, "%Y-%m-%d").date() if v else None


def gather(cfg, env, session=None):
    """{key: date|None|'unknown'|'error: …'} for every key that's set up."""
    out = {}
    if env.get("META_TOKEN"):
        try:
            out.update(meta_dates(env["META_TOKEN"], session))
        except RuntimeError as e:
            out["meta"] = f"error: {e}"
    if env.get("PHOTOS_KEY") or env.get("PLAYER_PHOTOS_TOKEN"):
        try:
            out["photos"] = github_token_date(env.get("PHOTOS_KEY") or env["PLAYER_PHOTOS_TOKEN"], session)
        except RuntimeError as e:
            out["photos"] = f"error: {e}"
    if env.get("M365_CLIENT_SECRET") or cfg["expiry_reminders"].get("m365_secret_expires"):
        out["m365"] = m365_date(cfg) or "unknown"
    return out


def stage(when, today, warn_days):
    """The warning stage (days) this date is in, or None if no warning is due yet."""
    if not isinstance(when, date):
        return None
    left = (when - today).days
    hits = [d for d in sorted(warn_days) if left <= d]
    return hits[0] if hits else None


def describe(key, when, today):
    if isinstance(when, str):
        return "date not set in club.yml" if when == "unknown" else when
    if when is None:
        return "never expires"
    if when == date.min:
        return "has expired or stopped working"
    left = (when - today).days
    if left < 0:
        return f"expired on {when:%-d %B %Y}"
    return f"expires {when:%-d %B %Y} ({left} day{'s' if left != 1 else ''})"


def check_lines(cfg, env, today, session=None):
    """Lines for Check setup."""
    dates = gather(cfg, env, session)
    warn = cfg["expiry_reminders"]["warn_days"]
    lines = []
    for key, when in dates.items():
        text = describe(key, when, today)
        if key == "m365" and when == "unknown":
            lines.append(f"ℹ️ **{NAMES[key]}**: add its expiry date to club.yml (expiry_reminders → "
                         f"m365_secret_expires) so you get a reminder before it runs out.")
        elif isinstance(when, str):
            lines.append(f"⚠️ **{NAMES[key]}**: couldn't check the expiry date ({when}).")
        elif stage(when, today, warn) is not None:
            lines.append(f"⚠️ **{NAMES[key]}** {text}. {HOW[key]}")
        else:
            lines.append(f"✅ **{NAMES[key]}** {text}.")
    return lines


def run(cfg, gh, env, today, session=None):
    """Open, escalate or close expiry warnings. Returns lines for the job summary."""
    er = cfg["expiry_reminders"]
    if not er["enabled"]:
        return []
    dates = gather(cfg, env, session)
    club = cfg.short_name_upper
    open_now = alerts._open_problems(gh)
    lines = []
    for key, when in dates.items():
        if isinstance(when, str):
            if key != "m365":
                lines.append(f"- ⚠️ {NAMES[key]}: couldn't check the expiry date ({when}).")
            continue
        st = stage(when, today, er["warn_days"])
        mine = {k: i for k, i in open_now.items() if k == f"expiry:{key}" or k.startswith(f"expiry:{key}:")}
        if st is None:
            for k, issue in mine.items():  # renewed
                gh.comment(issue["number"], f"✅ Renewed: the {NAMES[key]} now {describe(key, when, today)}. Closing.")
                gh.close(issue["number"])
                alerts._email(f"✅ {club} social media: {NAMES[key]} renewed",
                              f"Thanks: the {NAMES[key]} now {describe(key, when, today)}.\n\n{issue.get('html_url', '')}")
                lines.append(f"- ✅ {NAMES[key]} renewed: closed #{issue['number']}.")
            continue
        want = f"expiry:{key}:{st}"
        for k, issue in mine.items():  # a later stage replaces an earlier one, without a "fixed" email
            if k != want:
                gh.comment(issue["number"], "Replaced by a newer reminder.")
                gh.close(issue["number"])
        title = f"The {NAMES[key]} {describe(key, when, today)}"
        if want in mine:
            lines.append(f"- ⚠️ {title} (reminder already sent: #{mine[want]['number']}).")
            continue
        gh.ensure_labels()
        n = alerts.problem(gh, want, title, HOW[key], club=club)
        lines.append(f"- ⚠️ {title}: reminder sent (#{n}).")
    return lines
