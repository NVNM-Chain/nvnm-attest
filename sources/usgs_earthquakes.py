"""Earthquakes worldwide from the USGS real-time feed, one record per event version. Public domain, no key.

The US Geological Survey (USGS) publishes every earthquake it locates, worldwide, within minutes, and updates the
feed every minute. Each event is revised as more data comes in: magnitude, location, review status. A record
holds one event exactly as the feed published it (a GeoJSON feature: magnitude, place, time, depth, coordinates,
alert level, tsunami flag, review status). key = event id + its "updated" time, so every revision is anchored once
and the chain keeps a public history of how a quake's numbers changed.

Feed: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson (past 24 hours, all magnitudes)
Docs: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php

Licence: USGS data is US government work, public domain
(https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). Don't suggest that USGS runs
or endorses your bot. Registry description, for example: "Earthquakes worldwide, one record per event revision,
from the USGS real-time GeoJSON feed (public domain). Not affiliated with USGS."

Runs often, anchors once: SKIP_ANCHORED makes the bot skip any event version already in the registry, even after
a restart. A new revision of an event has a new "updated" time, so it gets its own record.

Verify a record: for 7 days, find the feature with that id in
https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson. If its "updated" time still matches,
take the feature as is and run scripts/verify.py --json. After a newer revision, or after 7 days, use the copy
the bot keeps in data/<registry>/.
"""
import gzip
import json
import urllib.request

NAME = "usgs-earthquakes"
DEFAULT_EVERY = 300         # seconds; the feed updates every minute, about 10 to 20 new events or revisions an hour
BATCH = 1                   # one transaction per event version
PUBLIC = False              # hash only: a feature is about 700 bytes, too close to the metadata limit with the kit's fields
SKIP_ANCHORED = True        # the feed is a rolling 24-hour window: anchor each event version once

FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"


def fetch():
    req = urllib.request.Request(FEED, headers={"User-Agent": "nvnm-attest", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    items = {}
    for feature in json.loads(body).get("features", []):
        event_id, updated = feature.get("id"), feature.get("properties", {}).get("updated")
        if not event_id or updated is None:
            continue
        key = f"eq:{event_id}:{updated}"
        items[key] = {
            "key": key,
            "uri": f"urn:usgs:eq:{event_id}:{updated}",  # about 40 bytes
            "data": feature,
        }
    return [items[k] for k in sorted(items)]
