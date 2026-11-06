"""GitHub issues as the approval step: one issue per post, approve by adding the 'approved' label."""
import json
import os
import re

import requests

API = "https://api.github.com"
LABELS = {
    "social-post": ("1A4192", "A post made by the Cricket Social Kit"),
    "approved": ("2DA44E", "Add this label to publish the post"),
    "published": ("8250DF", "Posted to Facebook / Instagram"),
    "failed": ("CF222E", "Posting failed: see the comment"),
    "scheduled": ("FBCA04", "Approved: will be posted on its 'post on' date"),
    "club-news": ("0E8A16", "Club news or event form"),
}
MARK = re.compile(r"<!--\s*csk-post\s+(\{.*?\})\s*-->", re.S)
CAPTION = re.compile(r"<!--\s*caption:start\s*-->\s*```[a-z]*\n(.*?)\n```\s*<!--\s*caption:end\s*-->", re.S)


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(self, token=None, repo=None, session=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY")
        if not self.token or not self.repo:
            raise GitHubError("GITHUB_TOKEN / GITHUB_REPOSITORY not set (this step must run inside GitHub Actions).")
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})

    def _req(self, method, path, ok=(200, 201), **kw):
        r = self.http.request(method, f"{API}/repos/{self.repo}/{path}", timeout=30, **kw)
        if r.status_code not in ok:
            raise GitHubError(f"GitHub {method} {path} failed ({r.status_code}): {r.text[:300]}")
        return r.json() if r.content else {}

    def ensure_labels(self):
        have = {l["name"] for l in self._req("GET", "labels", params={"per_page": 100})}
        for name, (color, desc) in LABELS.items():
            if name not in have:
                self._req("POST", "labels", json={"name": name, "color": color, "description": desc})

    def create_issue(self, title, body, labels=("social-post",)):
        return self._req("POST", "issues", json={"title": title, "body": body, "labels": list(labels)})

    def open_issues(self, label):
        return [i for i in self._req("GET", "issues", params={"state": "open", "labels": label, "per_page": 100})
                if "pull_request" not in i]

    def get_issue(self, number):
        return self._req("GET", f"issues/{number}")

    def comment(self, number, body):
        return self._req("POST", f"issues/{number}/comments", json={"body": body})

    def add_labels(self, number, labels):
        return self._req("POST", f"issues/{number}/labels", json={"labels": list(labels)})

    def remove_label(self, number, label):
        return self._req("DELETE", f"issues/{number}/labels/{label}", ok=(200, 204, 404))

    def close(self, number):
        return self._req("PATCH", f"issues/{number}", json={"state": "closed", "state_reason": "completed"})

    def repo_info(self):
        r = self.http.get(f"{API}/repos/{self.repo}", timeout=30)
        return r.json() if r.status_code == 200 else {}


def raw_url(repo, sha, path):
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def issue_body(post, image_urls, networks, sample=False, story_urls=(), reminder_url=""):
    nets = " and ".join(n.capitalize() for n in networks)
    imgs = "\n\n".join(f"![{post['title']} – image {i}]({u})" for i, u in enumerate(image_urls, 1))
    if story_urls:
        imgs += "\n\n**Story version** (posted to Stories too):\n\n" + " ".join(
            f'<img src="{u}" width="240" alt="Story frame {i}">' for i, u in enumerate(story_urls, 1))
    meta = {"key": post["key"], "kind": post["kind"], "images": image_urls, "networks": list(networks),
            "sample": sample, "stories": list(story_urls)}
    if post.get("post_on"):
        meta["post_on"] = post["post_on"]
    if reminder_url and post.get("reminder_date"):
        meta["reminder"] = {"date": post["reminder_date"], "story": reminder_url}
        imgs += (f"\n\n**Reminder Story** (posted on the morning of the event):\n\n"
                 f'<img src="{reminder_url}" width="240" alt="Reminder story">')
    how = ("**This is a preview of your graphics.** It can't be published. Close it when you've had a look."
           if sample else
           f"**To post this to {nets}:** add the **approved** label (in the GitHub app: tap *Labels*).\n"
           f"**To change the words first:** edit this issue and change the text in the caption box, then approve.\n"
           f"**To skip it:** close the issue.")
    checks = ""
    if post.get("post_on") or meta.get("reminder"):
        from .news import schedule_note
        how += "\n\n" + schedule_note({**post, **({"reminder": meta["reminder"]} if meta.get("reminder") else {})})
    if post.get("match_id"):
        checks = f"\n\nScorecard: https://play-cricket.com/website/results/{post['match_id']}"
    return (f"{how}\n\n{imgs}\n\n### Caption\n\n<!-- caption:start -->\n```text\n{post['caption']}\n```\n"
            f"<!-- caption:end -->\n\n**Image description** (for screen readers): {post.get('alt', '')}{checks}\n\n"
            f"<!-- csk-post {json.dumps(meta)} -->\n")


def parse_issue(body):
    """(meta dict, caption) from an issue made by issue_body. Raises if it isn't one of ours."""
    m = MARK.search(body or "")
    if not m:
        raise GitHubError("This issue wasn't made by the Cricket Social Kit, so there's nothing to post.")
    meta = json.loads(m.group(1))
    c = CAPTION.search(body)
    if not c:
        raise GitHubError("I couldn't find the caption box in this issue. It needs to stay between the ``` lines.")
    caption = c.group(1).strip()
    if not caption:
        raise GitHubError("The caption is empty.")
    return meta, caption
