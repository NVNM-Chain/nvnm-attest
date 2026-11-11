"""Solar X-rays from NOAA's GOES satellite, one record per minute. Public domain, no key.

NOAA's Space Weather Prediction Center (SWPC) publishes what GOES measures every minute in two X-ray bands.
The 0.1-0.8 nm band gives the solar-flare class (A, B, C, M, X). Each minute is anchored once: key = satellite
+ minute, and the record holds that minute's two rows exactly as NOAA published them.

Licence: US government data, public domain (https://www.weather.gov/disclaimer). Don't suggest that NOAA runs
or endorses your bot. Registry description, for example: "GOES X-ray flux per minute, from NOAA SWPC public
data. Not affiliated with NOAA."

Runs twice, anchors once: SKIP_ANCHORED makes the bot check the chain before each anchor, so a minute already
in the registry is never sent again, even after a restart.

Verify a record: for 7 days, take that minute's two rows from
https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json, build the record as fetch() does, and run
scripts/verify.py --json. After that, use the copy the bot keeps in data/<registry>/.
"""
import gzip
import json
import os
import urllib.request
from datetime import datetime, timedelta

NAME = "noaa-goes-xray"
DESCRIPTION = "GOES X-ray flux per minute, from NOAA SWPC public data. Not affiliated with NOAA."
DEFAULT_EVERY = 600         # seconds; NOAA adds a row per band every minute, so each run finds ~10 new minutes
BATCH = 1                   # one transaction per minute of data
PUBLIC = False              # hash only, which keeps metadata small (the data is public domain, so True is allowed)
SKIP_ANCHORED = True        # never anchor the same minute twice
WINDOW_MINUTES = int(os.getenv("SWPC_WINDOW_MINUTES", "60"))  # minutes to look back each run; the file holds 6 h

FEED = "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json"
BANDS = ("0.05-0.4nm", "0.1-0.8nm")


def _time(tag):  # "2026-11-10T02:39:00Z"; Python 3.10 can't parse the "Z"
    return datetime.fromisoformat(tag.replace("Z", "+00:00"))


def fetch():
    req = urllib.request.Request(FEED, headers={"User-Agent": "nvnm-attest", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    minutes = {}
    for row in json.loads(body):  # two rows per minute, one per band
        minutes.setdefault((row["satellite"], row["time_tag"]), {})[row["energy"]] = row
    if not minutes:
        return []
    newest = max(_time(t) for _, t in minutes)
    since = newest - timedelta(minutes=WINDOW_MINUTES)
    items = []
    for (sat, t), rows in sorted(minutes.items(), key=lambda kv: kv[0][1]):
        if _time(t) <= since or set(rows) != set(BANDS):
            continue  # outside the window, or the minute's second band isn't published yet
        stamp = _time(t).strftime("%y%m%d%H%M")
        items.append({
            "key": f"xr:{sat}:{stamp}",
            "uri": f"urn:swpc:xr:{sat}:{stamp}",  # 25 bytes
            "data": {"src": FEED, "rows": [rows[b] for b in BANDS]},
        })
    return items
