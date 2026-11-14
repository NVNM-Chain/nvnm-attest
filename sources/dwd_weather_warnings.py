"""German weather warnings from Deutscher Wetterdienst (DWD), one record per CAP warning message. CC BY 4.0.

DWD, Germany's national weather service, issues every official weather warning for Germany (wind, gale, storm,
thunderstorm, heavy rain, snow, black ice, frost, fog, heat) as CAP messages, and its open data server keeps a
zip with the latest status of every active warning, refreshed every few minutes. A record holds one warning
message exactly as DWD published it: the file name and the full CAP XML (event, severity, urgency, certainty,
onset and expiry, headline, description, instructions, the warned areas and their polygons). A change to a warning
is a new message with a new identifier that references the earlier one, so key = the CAP identifier and each
message is anchored once. The English edition is used, so each warning gives one record, not one per language.

Feed: https://opendata.dwd.de/weather/alerts/cap/COMMUNEUNION_DWD_STAT/
      (Z_CAP_C_EDZW_LATEST_PVW_STATUS_PREMIUMDWD_COMMUNEUNION_EN.zip)

Licence: DWD's freely accessible geodata may be reused under CC BY 4.0 with a source credit
(https://www.dwd.de/EN/service/legal_notice/legal_notice_node.html). Source: Deutscher Wetterdienst. The area
geometry inside each message carries its own credit, "GeoBasis-DE / BKG", which stays in the record as published.
Don't suggest that DWD runs or endorses your bot. Registry description, for example: "German weather warnings,
one record per CAP warning message, from the DWD open data server (CC BY 4.0). Source: Deutscher Wetterdienst.
Not affiliated with DWD."

Runs often, anchors once: SKIP_ANCHORED makes the bot skip any message already in the registry, even after a
restart. A message replaced between two runs is never seen.

Verify a record: while the warning is active, download the zip above, read the file named in the record, build
{"file": <name>, "cap": <file text as UTF-8>} and run scripts/verify.py --json on it. After that, use the copy the
bot keeps in data/<registry>/.
"""
import io
import urllib.request
import zipfile

NAME = "dwd-weather-warnings"
DESCRIPTION = ("German weather warnings, one record per CAP warning message, from the DWD open data server "
               "(CC BY 4.0). Source: Deutscher Wetterdienst. Not affiliated with DWD.")
DEFAULT_EVERY = 300         # seconds; DWD refreshes the latest-status zip every few minutes
BATCH = 1                   # one transaction per warning message
PUBLIC = False              # hash only: a CAP message is 2 to 30 KB, over the 2,048-byte metadata limit
SKIP_ANCHORED = True        # each run returns every active warning: anchor each message once

FEED = ("https://opendata.dwd.de/weather/alerts/cap/COMMUNEUNION_DWD_STAT/"
        "Z_CAP_C_EDZW_LATEST_PVW_STATUS_PREMIUMDWD_COMMUNEUNION_EN.zip")


def fetch():
    req = urllib.request.Request(FEED, headers={"User-Agent": "nvnm-attest"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
    items = {}
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        for name in z.namelist():
            if not name.endswith(".xml"):
                continue
            identifier = name[:-len(".xml")]  # the file is named after the message's CAP identifier
            items[identifier] = {
                "key": f"dwd:{identifier}",
                "uri": f"urn:dwd:cap:{identifier}",  # about 100 bytes
                "data": {"file": name, "cap": z.read(name).decode("utf-8")},
            }
    return [items[k] for k in sorted(items)]
