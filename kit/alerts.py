"""Problem alerts: when something goes wrong, open a 'problem' issue and email the committee.

- One open issue per problem (by key), so a repeat doesn't send another email.
- When the same job next works, the issue is closed and a short "fixed" email goes out.
- 'quiet_first': the daily posts run twice each morning, so a one-off blip (Play-Cricket briefly
  unavailable) is only emailed if the second run fails too.
Emails go through Microsoft 365 (kit.mailer) to ALERT_EMAIL_TO, or REPORT_EMAIL_TO if that isn't set.
Alerts must never stop posting, so every failure in here is swallowed and logged.
"""
import logging
import os
import re

from . import mailer

log = logging.getLogger(__name__)
MARK = "<!-- csk-problem "
EMAILED = "<!-- csk-emailed -->"

HINTS = {
    "make-posts": "If this mentions Play-Cricket, it's often Play-Cricket being briefly unavailable; the kit tries "
                  "again tomorrow morning. If it mentions the token, the PLAYCRICKET_API_TOKEN secret needs updating.",
    "post": "The post is kept, and nothing already posted will be posted twice. Once the cause is fixed, add the "
            "approved label to the post's issue again to retry.",
    "sponsor-report": "Run it again from Actions → Sponsor report once it's fixed.",
    "club-news": "Edit the form to try again.",
    "check-setup": "Open the run to see which line has a ❌.",
}


def _mail_settings():
    env = dict(os.environ)
    if env.get("ALERT_EMAIL_TO"):
        env["REPORT_EMAIL_TO"] = env["ALERT_EMAIL_TO"]
    try:
        return mailer.settings(env)
    except mailer.MailError as e:
        log.warning("Alert email not set up properly: %s", e)
        return None


def _email(subject, text):
    s = _mail_settings()
    if not s:
        return False
    try:
        mailer.send(s, subject, text)
        return True
    except mailer.MailError as e:
        log.warning("Couldn't send alert email: %s", e)
        return False


def _open_problems(gh):
    out = {}
    for i in gh.open_issues("problem"):
        m = re.search(re.escape(MARK) + r"(\S+) -->", i.get("body") or "")
        if m:
            out[m.group(1)] = i
    return out


def _hint(key):
    return HINTS.get(key.split(":")[0], "")


def problem(gh, key, title, details="", link="", quiet_first=False, club="VCC"):
    """Record a problem. Emails the first time (or the second, with quiet_first). Returns the issue number."""
    try:
        existing = _open_problems(gh).get(key)
        hint = _hint(key)
        text = (f"{title}\n\n{details.strip()}\n\n{hint}\n\nDetails: {link}").strip() if details or hint or link else title
        if existing:
            n = existing["number"]
            gh.comment(n, f"Still happening: {link}" + (f"\n\n{details.strip()}" if details else ""))
            emailed = EMAILED in (existing.get("body") or "") or any(
                EMAILED in (c.get("body") or "") for c in gh._req("GET", f"issues/{n}/comments", params={"per_page": 100}))
            if not emailed and _email(f"⚠️ {club} social media: {title}", text + f"\n\nTracking issue: {existing.get('html_url', '')}"):
                gh.comment(n, f"📧 Emailed the committee. {EMAILED}")
            return n
        body = (f"⚠️ **{title}**\n\n{details.strip()}\n\n{hint}\n\n{link}\n\nThis issue closes itself once it's "
                f"working again.\n\n{MARK}{key} -->")
        issue = gh.create_issue(f"⚠️ {title}", body, labels=("problem",))
        if not quiet_first and _email(f"⚠️ {club} social media: {title}",
                                      text + f"\n\nTracking issue: {issue.get('html_url', '')}"):
            gh.comment(issue["number"], f"📧 Emailed the committee. {EMAILED}")
        return issue["number"]
    except Exception as e:  # never let an alert break posting
        log.warning("Couldn't record problem %s: %s", key, e)
        return None


def resolved(gh, key, club="VCC"):
    """Close the open problem with this key (or keys starting 'key:'), emailing 'fixed' if we emailed about it."""
    closed = []
    try:
        for k, issue in _open_problems(gh).items():
            if k != key and not k.startswith(key + ":"):
                continue
            n = issue["number"]
            comments = gh._req("GET", f"issues/{n}/comments", params={"per_page": 100})
            emailed = EMAILED in (issue.get("body") or "") or any(EMAILED in (c.get("body") or "") for c in comments)
            gh.comment(n, "✅ Working again, so I've closed this.")
            gh.close(n)
            title = (issue.get("title") or "").lstrip("⚠️ ").strip()
            if emailed:
                _email(f"✅ {club} social media: fixed – {title}", f"Good news: this is working again.\n\n{title}\n\n"
                                                                   f"{issue.get('html_url', '')}")
            closed.append(n)
    except Exception as e:
        log.warning("Couldn't clear problem %s: %s", key, e)
    return closed


def problem_lines(summary_text, limit=8):
    """The ❌ / ⚠️ lines from a job summary, for the email."""
    lines = [l.strip() for l in (summary_text or "").splitlines() if l.strip().startswith(("- ❌", "❌", "- ⚠️", "⚠️"))]
    return "\n".join(re.sub(r"\*\*", "", l) for l in lines[:limit])
