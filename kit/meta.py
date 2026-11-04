"""Post images to a Facebook Page and its linked Instagram professional account (Meta Graph API).

One secret, META_TOKEN: a Meta Business "system user" token (never expires) or a Page access
token, with: pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic,
instagram_content_publish (and business_management for system users).
Images must be public URLs (Instagram fetches them itself) and JPEG.
"""
import json
import time

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
