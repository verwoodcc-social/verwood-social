"""Email through the club's Microsoft 365, using Microsoft Graph (no passwords stored).

Needs an app registration in Microsoft Entra ID with the *application* permission Mail.Send (admin
consented), and these repository secrets:
    M365_TENANT_ID, M365_CLIENT_ID, M365_CLIENT_SECRET   the app registration
    REPORT_EMAIL_FROM                                    mailbox it sends as, e.g. trevor.smith@verwoodcc.co.uk
    REPORT_EMAIL_TO                                      who gets it: addresses separated by commas
Addresses are secrets rather than in club.yml because this repository is public.
"""
import base64
import os
import re
from pathlib import Path

import requests

ADDRESS = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


class MailError(RuntimeError):
    pass


def settings(env=os.environ):
    keys = ("M365_TENANT_ID", "M365_CLIENT_ID", "M365_CLIENT_SECRET", "REPORT_EMAIL_FROM", "REPORT_EMAIL_TO")
    vals = {k: (env.get(k) or "").strip() for k in keys}
    if not any(vals.values()):
        return None  # email not set up: fine
    missing = [k for k, v in vals.items() if not v]
    if missing:
        raise MailError("Email is partly set up. Missing secret(s): " + ", ".join(missing))
    to = [a.strip() for a in re.split(r"[,;\s]+", vals["REPORT_EMAIL_TO"]) if a.strip()]
    bad = [a for a in to + [vals["REPORT_EMAIL_FROM"]] if not ADDRESS.match(a)]
    if bad:
        raise MailError(f"These don't look like email addresses: {', '.join(bad)}")
    return {**vals, "to": to}


def _token(s, http):
    r = http.post(f"https://login.microsoftonline.com/{s['M365_TENANT_ID']}/oauth2/v2.0/token", timeout=30,
                  data={"client_id": s["M365_CLIENT_ID"], "client_secret": s["M365_CLIENT_SECRET"],
                        "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"})
    body = r.json() if r.content else {}
    if r.status_code != 200 or "access_token" not in body:
        hint = body.get("error_description", "").split("\r\n")[0] or r.text[:200]
        raise MailError(f"Microsoft 365 sign-in failed: {hint}. Check the M365 secrets (and that the "
                        "client secret hasn't expired).")
    return body["access_token"]


def send(s, subject, text, attachments=(), http=None):
    """Send a plain-text email with file attachments (each under 3 MB)."""
    http = http or requests.Session()
    token = _token(s, http)
    files = []
    for f in attachments:
        f = Path(f)
        files.append({"@odata.type": "#microsoft.graph.fileAttachment", "name": f.name,
                      "contentType": "application/pdf" if f.suffix == ".pdf" else "application/octet-stream",
                      "contentBytes": base64.b64encode(f.read_bytes()).decode()})
    msg = {"message": {"subject": subject, "body": {"contentType": "Text", "content": text},
                       "toRecipients": [{"emailAddress": {"address": a}} for a in s["to"]],
                       "attachments": files},
           "saveToSentItems": True}
    r = http.post(f"https://graph.microsoft.com/v1.0/users/{s['REPORT_EMAIL_FROM']}/sendMail", json=msg,
                  headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if r.status_code != 202:
        err = (r.json().get("error") or {}) if r.content else {}
        code, message = err.get("code", r.status_code), err.get("message", "")
        hint = ""
        if code in ("ErrorAccessDenied", "Authorization_RequestDenied", 403):
            hint = (" The app needs the Mail.Send application permission with admin consent, and must be "
                    "allowed to send as this mailbox.")
        elif code in ("ErrorInvalidUser", "ResourceNotFound", "MailboxNotEnabledForRESTAPI"):
            hint = " Check REPORT_EMAIL_FROM is a real mailbox in your Microsoft 365."
        raise MailError(f"Microsoft 365 didn't send the email ({code}: {message}).{hint}")
    return s["to"]
