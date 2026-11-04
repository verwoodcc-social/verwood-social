"""Minimal Play-Cricket API v2 client (club's own API token).

Endpoints used (ECB Play-Cricket helpdesk, "API - Experienced Developers Only"):
  matches.json        fixtures list for a site and season
  result_summary.json results (with innings totals) for a site and season, filterable by match date
  match_detail.json   full scorecard for one match
"""
import time
from datetime import date, datetime

import requests

BASE = "https://play-cricket.com/api/v2"


class PlayCricketError(RuntimeError):
    pass


def parse_date(s):
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def fmt_date(d):
    return d.strftime("%d/%m/%Y")


class PlayCricket:
    def __init__(self, token, site_id, session=None, base=BASE):
        if not token:
            raise PlayCricketError("No Play-Cricket API token found. Add it as a repository secret called "
                                   "PLAYCRICKET_API_TOKEN (see the setup guide, step 3).")
        self.token, self.site_id, self.base = token, int(site_id), base
        self.http = session or requests.Session()

    def _get(self, path, **params):
        params["api_token"] = self.token
        last = None
        for attempt in range(3):
            try:
                r = self.http.get(f"{self.base}/{path}", params=params, timeout=30)
            except requests.RequestException as e:
                last = f"couldn't reach Play-Cricket ({e.__class__.__name__})"
            else:
                if r.status_code in (401, 403):
                    raise PlayCricketError("Play-Cricket refused the API token. Check the PLAYCRICKET_API_TOKEN "
                                           "secret is copied exactly, and that the token is for this club's site.")
                if r.status_code == 200:
                    try:
                        return r.json()
                    except ValueError:
                        last = "Play-Cricket sent back something that wasn't data (it may be down)"
                else:
                    last = f"Play-Cricket replied with error {r.status_code}"
            time.sleep(2 * (attempt + 1))
        raise PlayCricketError(f"Gave up after 3 tries: {last}.")

    @staticmethod
    def _seasons(start, end):
        # Winter indoor seasons can be filed under the previous year, so check that too.
        return sorted({start.year - 1, start.year, end.year})

    def fixtures(self, start: date, end: date):
        """Published, not-deleted matches with start <= match_date <= end."""
        out = {}
        for season in self._seasons(start, end):
            for m in self._get("matches.json", site_id=self.site_id, season=season).get("matches", []):
                d = parse_date(m.get("match_date"))
                if not d or not start <= d <= end:
                    continue
                if str(m.get("status", "")).lower() == "deleted" or str(m.get("published", "Yes")).lower() == "no":
                    continue
                out[str(m["id"])] = m
        return sorted(out.values(), key=lambda m: (parse_date(m["match_date"]), m.get("match_time") or ""))

    def results(self, start: date, end: date):
        """Matches with a result attached, played start <= match_date <= end."""
        out = {}
        for season in self._seasons(start, end):
            data = self._get("result_summary.json", site_id=self.site_id, season=season,
                             from_match_date=fmt_date(start), end_match_date=fmt_date(end))
            for m in data.get("result_summary", []):
                d = parse_date(m.get("match_date"))
                if not d or not start <= d <= end:
                    continue
                if str(m.get("status", "")).lower() == "deleted":
                    continue
                out[str(m["id"])] = m
        return sorted(out.values(), key=lambda m: (parse_date(m["match_date"]), m.get("match_time") or ""))

    def match_detail(self, match_id):
        data = self._get("match_detail.json", match_id=match_id)
        details = data.get("match_details") or []
        if not details:
            raise PlayCricketError(f"Play-Cricket has no details for match {match_id}.")
        return details[0]
