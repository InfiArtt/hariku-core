# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Finding live radio stations with the free Radio Browser directory
(https://www.radio-browser.info, no account or key).

Following its rules for clients: the server list comes from
all.api.radio-browser.info (a mirror is picked at random, the next one tried
when it fails, and a built-in list is the fallback), every request carries a
descriptive User-Agent, only stations that passed its last check are asked
for (hidebroken=true), and a station that starts playing is counted with
/json/url/<station id>, as the directory asks. Only the destination's country
code, name and rounded point are sent.

rank() prefers stations of the city itself (within GEO_KM, or naming it),
then the country's, the most listened to and voted for first, and only
streams Hariku can play: MP3 or AAC over HTTP(S), no HLS playlists. Blocking:
call search functions on a worker thread. No wx. A future Radio extension can
use it as it is.
"""

import math
import random
import urllib.parse

import core.place_search as place_search
from core.constants import CORE_VERSION

import world_trip_phrases as phrases

PROJECT_URL = "https://github.com/InfiArtt/hariku-core"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (World Trip extension; +{PROJECT_URL})"
SERVERS_URL = "https://all.api.radio-browser.info/json/servers"
FALLBACK_SERVERS = ("de1.api.radio-browser.info", "de2.api.radio-browser.info",
                    "fi1.api.radio-browser.info")
TIMEOUT_SECONDS = 10
GEO_KM = 60
SEARCH_LIMIT = 40
MAX_STATIONS = 12
PLAYABLE_CODECS = {"MP3": 0, "AAC": 1, "AAC+": 1, "AACP": 1, "HE-AAC": 1}


class StationError(Exception):
    """`kind`: "offline" or "service"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


def _default_fetch(url):
    return place_search.fetch_json(url, timeout=TIMEOUT_SECONDS, user_agent=USER_AGENT)


def clean_station(raw):
    """A directory entry as a plain dict, or None when unusable."""
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url_resolved") or raw.get("url") or "").strip()
    name = " ".join(str(raw.get("name") or "").split())
    if not url.lower().startswith(("http://", "https://")) or not name:
        return None
    codec = str(raw.get("codec") or "").strip().upper()

    def number(key):
        value = place_search.to_float(raw.get(key))
        return value if value is not None else None

    return {
        "uuid": str(raw.get("stationuuid") or ""),
        "name": name[:120],
        "url": url,
        "codec": codec,
        "bitrate": int(number("bitrate") or 0),
        "hls": bool(raw.get("hls")) and str(raw.get("hls")) not in ("0", "false"),
        "votes": int(number("votes") or 0),
        "clicks": int(number("clickcount") or 0),
        "state": " ".join(str(raw.get("state") or "").split()),
        "country_code": str(raw.get("countrycode") or "").upper()[:2],
        "latitude": number("geo_lat"),
        "longitude": number("geo_long"),
        "tags": str(raw.get("tags") or "")[:200],
    }


def playable(station):
    """MP3 or AAC over HTTP(S), not an HLS playlist."""
    return (station["codec"] in PLAYABLE_CODECS and not station["hls"]
            and not station["url"].lower().split("?")[0].endswith((".m3u8", ".m3u", ".pls")))


def _near(station, dest):
    if station.get("latitude") is None or station.get("longitude") is None:
        return False
    lat1, lon1 = math.radians(station["latitude"]), math.radians(station["longitude"])
    lat2, lon2 = math.radians(dest["latitude"]), math.radians(dest["longitude"])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h))) <= GEO_KM


def is_local(station, dest, names=()):
    """Whether a station is the city's own: near its point, or naming it in
    its name or region."""
    if _near(station, dest):
        return True
    words = f" {phrases.normalize(station['name'])} {phrases.normalize(station['state'])} "
    for name in names:
        key = phrases.normalize(name)
        if len(key) >= 3 and f" {key} " in words:
            return True
    return False


def score(station):
    return math.log1p(max(0, station["votes"])) + 2 * math.log1p(max(0, station["clicks"]))


def rank(stations, dest, names=(), limit=MAX_STATIONS):
    """The playable stations to try, best first: the city's own, then the
    country's; the most listened to first. Duplicates (same stream or name)
    once."""
    cc = str(dest.get("country_code") or "").upper()
    seen_urls, seen_names, usable = set(), set(), []
    for station in stations:
        if station is None or not playable(station):
            continue
        if cc and station["country_code"] and station["country_code"] != cc:
            continue
        name_key = phrases.normalize(station["name"])
        if station["url"] in seen_urls or name_key in seen_names:
            continue
        seen_urls.add(station["url"])
        seen_names.add(name_key)
        usable.append(station)
    usable.sort(key=lambda s: (0 if is_local(s, dest, names) else 1, -score(s),
                               PLAYABLE_CODECS.get(s["codec"], 9), s["name"].lower()))
    return usable[:limit]


class RadioBrowser:
    """Radio Browser, through one of its mirrors."""

    def __init__(self, fetch=None, rng=None):
        self._fetch = fetch or _default_fetch
        self._rng = rng or random.Random()
        self._servers = None

    def servers(self):
        """The mirrors, in a random order (asked once, then remembered)."""
        if self._servers is None:
            names = []
            try:
                for item in self._fetch(SERVERS_URL) or []:
                    name = str(item.get("name") or "").strip().lower() if isinstance(item, dict) else ""
                    if name.endswith(".api.radio-browser.info") and name not in names:
                        names.append(name)
            except Exception:
                names = []
            names = names or list(FALLBACK_SERVERS)
            self._rng.shuffle(names)
            self._servers = names
        return list(self._servers)

    def _get(self, path, params):
        last = None
        for server in self.servers():
            url = f"https://{server}{path}"
            if params:
                url += "?" + urllib.parse.urlencode(params)
            try:
                return self._fetch(url)
            except place_search.FetchError as e:
                last = e
                continue
        kind = "offline" if last is None or last.kind == "offline" else "service"
        raise StationError(kind, str(last or "no server"))

    def search(self, **params):
        query = dict(params, hidebroken="true", order="clickcount", reverse="true",
                     limit=SEARCH_LIMIT)
        found = self._get("/json/stations/search", query)
        return [s for s in (clean_station(item) for item in (found or [])) if s]

    def stations_for(self, dest, names=()):
        """The playable stations for a destination, best first. Raises
        StationError when no mirror answers."""
        cc = str(dest.get("country_code") or "").upper()
        lat, lon = round(float(dest["latitude"]), 2), round(float(dest["longitude"]), 2)
        found, errors = [], []
        requests = [{"geo_lat": f"{lat:.2f}", "geo_long": f"{lon:.2f}",
                     "geo_distance": GEO_KM * 1000}]
        if cc:
            requests.append({"countrycode": cc})
        for params in requests:
            try:
                found += self.search(**params)
            except StationError as e:
                errors.append(e)
        if not found and errors:
            raise errors[0]
        return rank(found, dest, names)

    def count_click(self, uuid):
        """Tell the directory a station was played (its popularity count)."""
        if uuid:
            try:
                self._get(f"/json/url/{urllib.parse.quote(uuid, safe='')}", None)
            except StationError:
                pass
