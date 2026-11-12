"""US weather alerts from the National Weather Service, one record per alert. Public domain, no key.

The National Weather Service (NWS) issues every US watch, warning and advisory (tornado, flood, winter storm,
heat, marine, fire weather) as a CAP alert, and its public API lists all active alerts, usually several hundred
at a time. A record holds one alert exactly as the API published it (a GeoJSON feature: event, severity,
urgency, certainty, area, issuing office, sent, onset and expiry times, headline, description, instructions,
and the area's polygon when there is one). An update or cancellation is a new alert with its own id that
references the earlier one, so key = the alert's id and each alert is anchored once.

Feed: https://api.weather.gov/alerts/active
Docs: https://www.weather.gov/documentation/services-web-api

Licence: NWS data is US government work, public domain (https://www.weather.gov/disclaimer). Don't suggest that
NWS or NOAA runs or endorses your bot. Registry description, for example: "US weather watches, warnings and
advisories, one record per alert, from the National Weather Service public API. Not affiliated with NWS."

Runs often, anchors once: SKIP_ANCHORED makes the bot skip any alert already in the registry, even after a
restart. An alert issued and replaced between two runs is never seen.

Verify a record: while the API still serves the alert, fetch https://api.weather.gov/alerts/<alert id> with
Accept: application/geo+json, drop its top-level "@context" key and run scripts/verify.py --json on the rest.
After that, use the copy the bot keeps in data/<registry>/.
"""
import gzip
import json
import urllib.request

NAME = "nws-alerts"
DESCRIPTION = ("US weather watches, warnings and advisories, one record per alert, from the National Weather "
               "Service public API. Not affiliated with NWS.")
DEFAULT_EVERY = 300         # seconds; NWS offices issue new alerts around the clock
BATCH = 1                   # one transaction per alert
PUBLIC = False              # hash only: an alert is 1 to 12 KB, over the 2,048-byte metadata limit
SKIP_ANCHORED = True        # each run returns every active alert: anchor each one once

FEED = "https://api.weather.gov/alerts/active"


def fetch():
    req = urllib.request.Request(FEED, headers={
        "User-Agent": "nvnm-attest", "Accept": "application/geo+json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    items = {}
    for feature in json.loads(body).get("features", []):
        alert_id = feature.get("properties", {}).get("id")  # "urn:oid:2.49.0.1.840.0.<hash>.<n>.<n>"
        if not alert_id:
            continue
        items[alert_id] = {
            "key": f"nws:{alert_id}",
            "uri": alert_id,  # the alert's own CAP id, about 60 bytes
            "data": feature,
        }
    return [items[k] for k in sorted(items)]
