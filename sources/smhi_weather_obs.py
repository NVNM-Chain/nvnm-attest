"""Sweden's hourly weather observations from SMHI, one record per station per hour. CC BY 4.0, no key.

SMHI, Sweden's national weather service, publishes what its automatic stations measure every hour, from Abisko
in the Arctic to Falsterbo in the south. A record holds one station's observations for one hour: the station
(id, name, owner, latitude, longitude, height) and, for each parameter it reported, the value, quality flag,
unit and SMHI's parameter name: air temperature (1), wind direction (3), wind speed (4), relative humidity (6),
precipitation over the hour (7), sea-level pressure (9) and gust (21). key = station id + observation time, so
each station-hour is anchored once. About 180 stations report each hour.

Feed: https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/<p>/station-set/all/period/latest-hour/data.json
Docs: https://opendata.smhi.se/metobs/introduction

Licence: SMHI open data is CC BY 4.0, commercial use included; credit SMHI as the source
(https://www.smhi.se/data/om-smhis-data/villkor-for-anvandning). Source: SMHI. Don't suggest that SMHI runs or
endorses your bot. Registry description, for example: "Sweden's hourly weather observations, one record per
station per hour, from SMHI open data (CC BY 4.0). Source: SMHI. Not affiliated with SMHI."

Runs often, anchors once: SKIP_ANCHORED makes the bot skip any station-hour already in the registry, even after
a restart. A station that reports late is picked up on a later run within the hour. If a parameter arrives later
than the others, or SMHI revises a value or its quality flag, the station-hour is anchored again with the new data
(same key, new hash), so the chain keeps each version.

Verify a record: during that hour, fetch the seven feeds above, build the station's record as fetch() does and
run scripts/verify.py --json. After that, use the copy the bot keeps in data/<registry>/.
"""
import json
import urllib.request

NAME = "smhi-weather-obs"
DESCRIPTION = ("Sweden's hourly weather observations, one record per station per hour, from SMHI open data "
               "(CC BY 4.0). Source: SMHI. Not affiliated with SMHI.")
DEFAULT_EVERY = 900         # seconds; SMHI publishes hourly and some stations report late in the hour
BATCH = 1                   # one transaction per station-hour, about 180 an hour
PUBLIC = True               # open data, and a record is under 800 bytes: the observations go in on-chain metadata
SKIP_ANCHORED = True        # each run returns the latest hour again: anchor each version once

PARAMETERS = (1, 3, 4, 6, 7, 9, 21)
FEED = ("https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{}/station-set/all/period/"
        "latest-hour/data.json")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nvnm-attest"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch():
    records = {}
    for p in PARAMETERS:
        feed = _get(FEED.format(p))
        param = feed.get("parameter", {})
        for st in feed.get("station", []):
            for v in st.get("value") or []:
                key = f"smhi:{st['key']}:{v['date']}"
                rec = records.setdefault(key, {
                    "station": {k: st.get(k) for k in ("key", "name", "owner", "latitude", "longitude", "height")},
                    "time": v["date"],  # ms since epoch, UTC
                    "obs": {},
                })
                rec["obs"][str(p)] = {"value": v.get("value"), "quality": v.get("quality"),
                                      "unit": param.get("unit"), "name": param.get("name")}
    return [{"key": k, "uri": f"urn:{k}", "data": records[k]} for k in sorted(records)]
