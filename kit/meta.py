"""Post images to a Facebook Page and its linked Instagram professional account (Meta Graph API).

One secret, META_TOKEN: a Meta Business "system user" token (never expires) or a Page access
token, with: pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic,
instagram_content_publish (and business_management for system users).
Images must be public URLs (Instagram fetches them itself) and JPEG.
"""
import json
import time
from datetime import timedelta

import requests

GRAPH = "https://graph.facebook.com"
VERSION = "v25.0"


class MetaError(RuntimeError):
    pass


def explain(err):
    """A plain-English hint for common Graph API errors."""
    code = err.get("code")
    msg = err.get("message", "unknown error")
    hint = {
        190: "The Meta token has expired or been revoked. Make a new one (setup guide, step 4) and update the META_TOKEN secret.",
        10: "The token is missing a permission. Regenerate it with all the permissions listed in the setup guide.",
        200: "The token is missing a permission. Regenerate it with all the permissions listed in the setup guide.",
        100: "Meta rejected one of the details sent. If this mentions an image, check the repository is public.",
        4: "Meta's rate limit was hit. Wait an hour, then remove and re-add the approved label to try again.",
        9004: "Instagram couldn't download the image. Check the repository is public.",
        36003: "Instagram didn't accept the image size or shape.",
    }.get(code, "")
    return f"{msg}" + (f" — {hint}" if hint else "")


class Meta:
    def __init__(self, token, page_id="", version=VERSION, session=None, sleep=time.sleep):
        if not token:
            raise MetaError("No Meta token found. Add it as a repository secret called META_TOKEN (setup guide, step 4).")
        self.token, self.page_id, self.version = token, str(page_id or ""), version
        self.http = session or requests.Session()
        self.sleep = sleep
        self.page_token = self.ig_id = self.page_name = self.ig_username = None

    # -- low level --
    def _call(self, method, path, token=None, **params):
        params["access_token"] = token or self.token
        url = f"{GRAPH}/{self.version}/{path.lstrip('/')}"
        try:
            r = self.http.request(method, url, data=params if method == "POST" else None,
                                  params=params if method == "GET" else None, timeout=60)
        except requests.RequestException as e:
            raise MetaError(f"Couldn't reach Meta ({e.__class__.__name__}). Try again later.")
        try:
            body = r.json()
        except ValueError:
            raise MetaError(f"Meta replied with error {r.status_code} and no details.")
        if r.status_code >= 400 or "error" in body:
            raise MetaError(explain(body.get("error", {})))
        return body

    # -- setup --
    def resolve(self):
        """Find the Page, its Page token and the linked Instagram account."""
        if not self.page_id:
            try:
                pages = self._call("GET", "me/accounts", fields="id,name").get("data", [])
            except MetaError:
                pages = []  # Page tokens can't list accounts
            if not pages:
                # A Page token: 'me' is the Page itself.
                me = self._call("GET", "me", fields="id,name")
                self.page_id = me["id"]
            elif len(pages) == 1:
                self.page_id = pages[0]["id"]
            else:
                names = ", ".join(f"{p['name']} ({p['id']})" for p in pages)
                raise MetaError(f"This token can post to several Facebook Pages: {names}. Put the right Page ID "
                                f"in club.yml under facebook → page_id.")
        page = self._call("GET", self.page_id, fields="name,access_token,instagram_business_account{id,username}")
        self.page_name = page.get("name")
        self.page_token = page.get("access_token") or self.token
        ig = page.get("instagram_business_account") or {}
        self.ig_id, self.ig_username = ig.get("id"), ig.get("username")
        return {"page_id": self.page_id, "page_name": self.page_name,
                "instagram_id": self.ig_id, "instagram_username": self.ig_username}

    # -- Facebook --
    def post_facebook(self, image_urls, caption):
        if self.page_token is None:
            self.resolve()
        if len(image_urls) == 1:
            r = self._call("POST", f"{self.page_id}/photos", token=self.page_token, url=image_urls[0], message=caption)
            post_id = r.get("post_id") or r.get("id")
        else:
            ids = [self._call("POST", f"{self.page_id}/photos", token=self.page_token, url=u, published="false")["id"]
                   for u in image_urls]
            params = {f"attached_media[{i}]": json.dumps({"media_fbid": fid}) for i, fid in enumerate(ids)}
            post_id = self._call("POST", f"{self.page_id}/feed", token=self.page_token, message=caption, **params)["id"]
        return {"network": "facebook", "id": post_id, "url": f"https://www.facebook.com/{post_id}"}

    # -- Stories (one frame per image; stories have no caption) --
    def post_facebook_story(self, image_url):
        """Page photo story: upload the photo unpublished, then publish it as a story."""
        if self.page_token is None:
            self.resolve()
        photo_id = self._call("POST", f"{self.page_id}/photos", token=self.page_token,
                              url=image_url, published="false")["id"]
        r = self._call("POST", f"{self.page_id}/photo_stories", token=self.page_token, photo_id=photo_id)
        return {"network": "facebook_story", "id": r.get("post_id") or photo_id,
                "url": f"https://www.facebook.com/{self.page_id}"}

    def post_instagram_story(self, image_url):
        if self.page_token is None:
            self.resolve()
        if not self.ig_id:
            raise MetaError("Your Facebook Page has no Instagram professional account linked to it.")
        container = self._call("POST", f"{self.ig_id}/media", token=self.page_token,
                               image_url=image_url, media_type="STORIES")["id"]
        self._wait(container)
        media_id = self._call("POST", f"{self.ig_id}/media_publish", token=self.page_token, creation_id=container)["id"]
        return {"network": "instagram_story", "id": media_id,
                "url": f"https://www.instagram.com/stories/{self.ig_username or ''}/"}

    # -- Instagram --
    def _wait(self, container_id, timeout=300, every=10):
        waited = 0
        while True:
            status = self._call("GET", container_id, token=self.page_token, fields="status_code").get("status_code")
            if status in ("FINISHED", "PUBLISHED"):
                return
            if status in ("ERROR", "EXPIRED"):
                raise MetaError(f"Instagram couldn't process the image (status {status}). Check the repository is public.")
            if waited >= timeout:
                raise MetaError("Instagram took too long to process the image. Remove and re-add the approved label to retry.")
            self.sleep(every)
            waited += every

    def post_instagram(self, image_urls, caption):
        if self.page_token is None:
            self.resolve()
        if not self.ig_id:
            raise MetaError("Your Facebook Page has no Instagram professional account linked to it. Link them in "
                            "Instagram (Settings → Account type and tools) or Meta Business Suite, then try again.")
        if len(image_urls) == 1:
            container = self._call("POST", f"{self.ig_id}/media", token=self.page_token,
                                   image_url=image_urls[0], caption=caption)["id"]
        else:
            children = []
            for u in image_urls[:20]:
                cid = self._call("POST", f"{self.ig_id}/media", token=self.page_token,
                                 image_url=u, is_carousel_item="true")["id"]
                self._wait(cid)
                children.append(cid)
            container = self._call("POST", f"{self.ig_id}/media", token=self.page_token, media_type="CAROUSEL",
                                   children=",".join(children), caption=caption)["id"]
        self._wait(container)
        media_id = self._call("POST", f"{self.ig_id}/media_publish", token=self.page_token, creation_id=container)["id"]
        try:
            link = self._call("GET", media_id, token=self.page_token, fields="permalink").get("permalink")
        except MetaError:
            link = None
        return {"network": "instagram", "id": media_id, "url": link or f"https://www.instagram.com/{self.ig_username or ''}"}


# --- Insights, for the monthly sponsor report ----------------------------------
# Needs three extra token permissions: read_insights, pages_read_user_content and instagram_manage_insights.
# Meta keeps renaming these metrics, so every figure is fetched separately and a missing one is
# reported as unavailable rather than stopping the report.

class Insights:
    def __init__(self, meta):
        self.m = meta
        if meta.page_token is None:
            meta.resolve()
        self.problems = []

    def _get(self, path, **params):
        return self.m._call("GET", path, token=self.m.page_token, **params)

    def _note(self, what, e):
        self.problems.append(f"{what}: {e}")

    def followers(self):
        out = {"facebook": None, "instagram": None}
        try:
            p = self._get(self.m.page_id, fields="followers_count,fan_count")
            out["facebook"] = p.get("followers_count", p.get("fan_count"))
        except MetaError as e:
            self._note("Facebook followers", e)
        if self.m.ig_id:
            try:
                out["instagram"] = self._get(self.m.ig_id, fields="followers_count").get("followers_count")
            except MetaError as e:
                self._note("Instagram followers", e)
        return out

    def page_totals(self, since, until):
        """Facebook Page views (and people reached, where Meta provides it) between two datetimes."""
        out = {}
        for key, metrics in (("views", ("page_media_view", "page_impressions")),
                             ("reach", ("page_total_media_view_unique", "page_impressions_unique"))):
            for metric in metrics:
                try:
                    data = self._get(f"{self.m.page_id}/insights", metric=metric, period="day",
                                     since=int(since.timestamp()), until=int(until.timestamp())).get("data", [])
                except MetaError as e:
                    self._note(f"Facebook {key} ({metric})", e)
                    continue
                if data:
                    out[key] = sum(int(v.get("value") or 0) for v in data[0].get("values", [])
                                   if isinstance(v.get("value"), (int, float)))
                    out[f"{key}_daily_total"] = key == "reach"
                    break
        return out

    def page_posts(self, since, until):
        """Facebook posts published in the range, with views and engagement."""
        try:
            posts = self._get(f"{self.m.page_id}/published_posts",
                              fields="id,created_time,message,permalink_url,shares,"
                                     "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)",
                              since=int(since.timestamp()), until=int(until.timestamp()), limit=100).get("data", [])
        except MetaError as e:
            self._note("Facebook posts", e)
            return []
        out = []
        for p in posts:
            row = {"network": "Facebook", "id": p["id"], "when": p.get("created_time", ""),
                   "text": (p.get("message") or "").strip(), "url": p.get("permalink_url", ""),
                   "likes": ((p.get("reactions") or {}).get("summary") or {}).get("total_count", 0),
                   "comments": ((p.get("comments") or {}).get("summary") or {}).get("total_count", 0),
                   "shares": (p.get("shares") or {}).get("count", 0), "views": None}
            for metric in ("post_media_view", "post_impressions"):
                try:
                    d = self._get(f"{p['id']}/insights", metric=metric).get("data", [])
                except MetaError as e:
                    if not any("Facebook post views" in x for x in self.problems):
                        self._note("Facebook post views", e)
                    continue
                if d and d[0].get("values"):
                    row["views"] = d[0]["values"][-1].get("value")
                    break
            out.append(row)
        return out

    def ig_totals(self, since, until):
        """Instagram account views, accounts reached and interactions (Meta allows 30 days per request)."""
        if not self.m.ig_id:
            return {}
        out = {}
        chunks, start = [], since
        while start < until:
            end = min(until, start + timedelta(days=28))  # Meta allows 30 days; clock changes add an hour
            chunks.append((start, end))
            start = end
        for metric, key in (("views", "views"), ("reach", "reach"), ("total_interactions", "interactions"),
                            ("likes", "likes"), ("comments", "comments"), ("shares", "shares")):
            total, ok = 0, False
            for a, b in chunks:
                try:
                    data = self._get(f"{self.m.ig_id}/insights", metric=metric, period="day",
                                     metric_type="total_value", since=int(a.timestamp()),
                                     until=int(b.timestamp())).get("data", [])
                except MetaError as e:
                    self._note(f"Instagram {key}", e)
                    break
                if data:
                    total += int((data[0].get("total_value") or {}).get("value") or 0)
                    ok = True
            if ok:
                out[key] = total
        return out

    def ig_posts(self, since, until):
        if not self.m.ig_id:
            return []
        try:
            media = self._get(f"{self.m.ig_id}/media",
                              fields="id,caption,timestamp,permalink,media_type,like_count,comments_count",
                              since=int(since.timestamp()), until=int(until.timestamp()), limit=100).get("data", [])
        except MetaError as e:
            self._note("Instagram posts", e)
            return []
        out = []
        for p in media:
            row = {"network": "Instagram", "id": p["id"], "when": p.get("timestamp", ""),
                   "text": (p.get("caption") or "").strip(), "url": p.get("permalink", ""),
                   "likes": p.get("like_count", 0), "comments": p.get("comments_count", 0), "shares": 0,
                   "views": None, "reach": None}
            try:
                d = self._get(f"{p['id']}/insights", metric="views,reach,shares").get("data", [])
                vals = {x["name"]: (x.get("values") or [{}])[-1].get("value") for x in d}
                row.update(views=vals.get("views"), reach=vals.get("reach"), shares=vals.get("shares") or 0)
            except MetaError as e:
                if not any("Instagram post views" in x for x in self.problems):
                    self._note("Instagram post views", e)
            out.append(row)
        return out
