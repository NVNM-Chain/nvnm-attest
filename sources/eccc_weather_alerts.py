"""Canadian weather alerts from Environment and Climate Change Canada, one record per alert version. Open licence.

Environment and Climate Change Canada (ECCC) issues every public weather warning, watch, advisory and special
statement in Canada (wind, blizzard, snowfall, rainfall, heat, freezing rain, storm surge) and publishes the active
ones, per forecast area, on its open data API. A record holds one alert feature exactly as the API published it:
type and name (English and French), province, area, status (issued, continued, ended), publication, validity and
expiry times, risk colour, confidence, impact, the full alert text in both languages, and the area's polygon.
key = feature id + publication time, so each version the bot sees is anchored once. Usually a few dozen alerts
are active at a time, more in storm season.

Feed: https://api.weather.gc.ca/collections/weather-alerts/items?f=json
Docs: https://eccc-msc.github.io/open-data/msc-geomet/readme_en/

Licence: ECCC Data Servers End-use Licence, which allows copying, publishing and commercial use with attribution
(https://eccc-msc.github.io/open-data/licence/readme_en/). Data Source: Environment and Climate Change Canada.
Alerts must be reproduced without altering their content: each record is the feature exactly as published. Don't
suggest that ECCC runs or endorses your bot. Registry description, for example: "Canadian weather warnings,
watches and advisories, one record per alert version, from the ECCC open data API. Data Source: Environment and
Climate Change Canada. Not affiliated with ECCC."

Runs often, anchors once: SKIP_ANCHORED makes the bot skip any alert version already in the registry, even after a
restart. A version issued and replaced between two runs is never seen.

Verify a record: while the alert is active, fetch
https://api.weather.gc.ca/collections/weather-alerts/items/<feature id>?f=json, drop its top-level "links" key
and run scripts/verify.py --json on the rest. After that, use the copy the bot keeps in data/<registry>/.
"""
import gzip
import json
import urllib.request

NAME = "eccc-weather-alerts"
DESCRIPTION = ("Canadian weather warnings, watches and advisories, one record per alert version, from the ECCC "
               "open data API. Data Source: Environment and Climate Change Canada. Not affiliated with ECCC.")
DEFAULT_EVERY = 300         # seconds; forecast offices issue and update alerts around the clock
BATCH = 1                   # one transaction per alert version
PUBLIC = False              # hash only: an alert is 1.5 to 20 KB, over the 2,048-byte metadata limit
SKIP_ANCHORED = True        # each run returns every active alert: anchor each version once

FEED = "https://api.weather.gc.ca/collections/weather-alerts/items?f=json&limit=10000"


def fetch():
    req = urllib.request.Request(FEED, headers={"User-Agent": "nvnm-attest", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    items = {}
    for feature in json.loads(body).get("features", []):
        feature_id = feature.get("id")
        published = feature.get("properties", {}).get("publication_datetime")
        if not feature_id or not published:
            continue
        key = f"eccc:{feature_id}:{published}"
        items[key] = {
            "key": key,
            "uri": f"urn:eccc:alert:{feature_id}:{published}",  # about 75 bytes
            "data": feature,
        }
    return [items[k] for k in sorted(items)]
