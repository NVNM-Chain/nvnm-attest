"""Finland's hourly weather observations from FMI, one record per station per hour. CC BY 4.0, no key.

The Finnish Meteorological Institute (FMI) publishes what its automatic weather stations measure, from the
Aland islands to Lapland, through its open WFS service. A record holds one station's observations for one full
hour: the station (FMI station id, name, region, latitude, longitude), the observation time, and the values FMI
reports for air temperature (t2m, degC), wind speed and direction (ws_10min, m/s; wd_10min, deg), gust
(wg_10min, m/s), relative humidity (rh, %), sea-level pressure (p_sea, hPa) and precipitation over the hour
(r_1h, mm). A value FMI has no reading for is null. key = station id + hour, so each station-hour is anchored
once. About 185 stations report each hour.

Feed: https://opendata.fmi.fi/wfs, stored query fmi::observations::weather::multipointcoverage, bbox of Finland,
hourly timestep, the last three hours
Docs: https://en.ilmatieteenlaitos.fi/open-data-manual

Licence: FMI open data is CC BY 4.0 (https://en.ilmatieteenlaitos.fi/open-data-licence). Source: Finnish
Meteorological Institute. Don't suggest that FMI runs or endorses your bot. Registry description, for example:
"Finland's hourly weather observations, one record per station per hour, from FMI open data (CC BY 4.0).
Source: Finnish Meteorological Institute. Not affiliated with FMI."

Runs often, anchors once: each run reads the last three hours and SKIP_ANCHORED skips any station-hour already
in the registry, even after a restart. If FMI fills in a late value or corrects one, the station-hour is
anchored again with the new data (same key, new hash), so the chain keeps each version.

Verify a record: for about a day, query the WFS above with starttime and endtime set to that hour, build the
station's record as fetch() does and run scripts/verify.py --json. After that, use the copy the bot keeps in
data/<registry>/.
"""
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

NAME = "fmi-weather-obs"
DESCRIPTION = ("Finland's hourly weather observations, one record per station per hour, from FMI open data "
               "(CC BY 4.0). Source: Finnish Meteorological Institute. Not affiliated with FMI.")
DEFAULT_EVERY = 900         # seconds; FMI publishes each hour's values within minutes, some arrive later
BATCH = 1                   # one transaction per station-hour, about 185 an hour
PUBLIC = False              # hash only: keeps metadata small (the data is CC BY 4.0, so True is allowed)
SKIP_ANCHORED = True        # each run reads the last three hours: anchor each version once

PARAMETERS = ("t2m", "ws_10min", "wd_10min", "wg_10min", "rh", "p_sea", "r_1h")
WFS = "https://opendata.fmi.fi/wfs"
HOURS = 3

NS = {"gml": "http://www.opengis.net/gml/3.2", "target": "http://xml.fmi.fi/namespace/om/atmosphericfeatures/1.1",
      "gmlcov": "http://www.opengis.net/gmlcov/1.0", "xlink": "http://www.w3.org/1999/xlink",
      "swe": "http://www.opengis.net/swe/2.0"}
GML_ID = "{http://www.opengis.net/gml/3.2}id"


def _url(start, end):
    return WFS + "?" + urllib.parse.urlencode({
        "service": "WFS", "version": "2.0.0", "request": "getFeature",
        "storedquery_id": "fmi::observations::weather::multipointcoverage",
        "bbox": "19,59,32,71", "timestep": "60", "parameters": ",".join(PARAMETERS),
        "starttime": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "endtime": end.strftime("%Y-%m-%dT%H:%M:%SZ")})


def _pos(text):  # "60.30373 25.54916" -> a key that ignores spacing
    return tuple(text.split()[:2])


def parse(body):
    """Turn one WFS response into {key: record}. Used by fetch() and to rebuild a record when verifying."""
    if b"<!DOCTYPE" in body or b"<!ENTITY" in body:  # FMI never sends a DTD; refusing one blocks entity attacks
        raise ValueError("unexpected DTD in the WFS response")
    root = ET.fromstring(body)
    points = {p.get(GML_ID): _pos(p.findtext("gml:pos", "", NS)) for p in root.iter(f"{{{NS['gml']}}}Point")}
    stations, seen = {}, set()
    for loc in root.iter(f"{{{NS['target']}}}Location"):
        names = {n.get("codeSpace", "").rsplit("/", 1)[-1]: n.text for n in loc.findall("gml:name", NS)}
        ref = loc.find("target:representativePoint", NS)
        pos = points.get((ref.get(f"{{{NS['xlink']}}}href") or "").lstrip("#")) if ref is not None else None
        if pos is None:
            continue
        if pos in seen:  # two stations at one position can't be told apart in the coverage: leave both out
            stations.pop(pos, None)
            continue
        seen.add(pos)
        stations[pos] = {"fmisid": loc.findtext("gml:identifier", "", NS), "name": names.get("name"),
                         "region": loc.findtext("target:region", None, NS),
                         "latitude": float(pos[0]), "longitude": float(pos[1])}
    fields = [f.get("name") for f in root.iter(f"{{{NS['swe']}}}field")]  # the column order FMI declares
    if sorted(fields) != sorted(PARAMETERS):
        raise ValueError(f"unexpected WFS fields {fields}")
    positions = root.findtext(".//gmlcov:positions", "", NS).split()  # lat, lon, epoch per row
    tokens = root.findtext(".//gml:doubleOrNilReasonTupleList", "", NS).split()  # whitespace-separated values
    rows = len(positions) // 3
    if len(positions) % 3 or len(tokens) != rows * len(fields):
        raise ValueError("WFS positions and values don't line up")
    records = {}
    for i in range(rows):
        lat, lon, epoch = positions[3 * i: 3 * i + 3]
        station = stations.get((lat, lon))
        if station is None:
            continue
        row = tokens[i * len(fields): (i + 1) * len(fields)]
        obs = {name: (None if v == "NaN" else v) for name, v in zip(fields, row)}
        if all(v is None for v in obs.values()):
            continue  # no reading at all for this hour
        when = datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        key = f"fmi:{station['fmisid']}:{when}"
        records[key] = {"station": station, "time": when, "obs": obs}
    return records


def fetch():
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    req = urllib.request.Request(_url(end - timedelta(hours=HOURS - 1), end), headers={"User-Agent": "nvnm-attest"})
    with urllib.request.urlopen(req, timeout=20) as r:
        records = parse(r.read())
    return [{"key": k, "uri": f"urn:{k}", "data": records[k]} for k in sorted(records)]
