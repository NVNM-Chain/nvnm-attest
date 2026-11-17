"""Euro reference rates from the European Central Bank via Frankfurter, one record per currency per day. No key.

The European Central Bank (ECB) publishes euro foreign exchange reference rates every working day, usually
around 16:00 CET, from its daily concertation procedure with national central banks. They are reference
rates: published for information only, and the ECB itself says they are not intended to be used, directly
or indirectly, as benchmarks in market transactions. Frankfurter is a free, open-source API that serves
the ECB's published rates as JSON. A record holds one currency's rate for one date exactly as the API
published it (1 EUR = rate × quote currency). key = the currency pair + the rate date the API reports, so
each day's set is anchored once, and the chain keeps a public, timestamped history of the ECB's rates
against seven major currencies: USD, GBP, JPY, CHF, CNY, CAD and AUD.

Why these choices: one API call returns all seven quotes at once, so a run is a single fetch that becomes
seven small points (BATCH = 1, one transaction each), and each point is tiny enough to go in the metadata
(PUBLIC = True), the same treatment the kit gives Hyperliquid prices. The rates only change once per
business day, so polling hourly (DEFAULT_EVERY) is already generous — it exists to catch the new set soon
after publication, not because the data moves. SKIP_ANCHORED is what makes that safe: without it the bot
would re-anchor the same date's rates on every poll, 24 times a day; with it, the bot checks the chain
first and anchors each date exactly once.

Licence and terms: the ECB allows reuse of its statistical data free of charge provided the source is
acknowledged (see the euro reference rates page:
https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html),
and the DESCRIPTION below carries that acknowledgement. Frankfurter is open-source software (MIT,
https://github.com/frankfurter/frankfurter) with a free public API (https://www.frankfurter.app) that
needs no key and sets no non-commercial condition. Not affiliated with the ECB or Frankfurter.
Registry description, for example: "Euro reference rates from the European Central Bank via Frankfurter.
Not affiliated with the ECB or Frankfurter."

Verify a record: unlike a "current conditions" feed, these rates stay fetchable. Re-request the record's
date at https://api.frankfurter.dev/v1/<date>?from=EUR&to=<quote> (for example /v1/2026-11-10) and
compare the rate, or run scripts/verify.py --json on the point's data.
"""
import gzip
import json
import urllib.parse
import urllib.request

NAME = "ecb-fx-rates"
DESCRIPTION = ("Euro reference rates from the European Central Bank via Frankfurter. "
               "Not affiliated with the ECB or Frankfurter.")
DEFAULT_EVERY = 3600        # seconds; the ECB publishes once per working day, this just catches it promptly
BATCH = 1                   # one transaction per currency (seven points per run)
PUBLIC = True               # public data, and each point is small (~120 bytes): include it in metadata
SKIP_ANCHORED = True        # rates change once per business day; never anchor the same date twice

BASE = "EUR"
QUOTES = ("USD", "GBP", "JPY", "CHF", "CNY", "CAD", "AUD")  # seven major currencies against the euro
API = "https://api.frankfurter.dev/v1/latest"  # canonical v1 endpoint; api.frankfurter.app 301-redirects here


def _url():
    q = urllib.parse.urlencode({"from": BASE, "to": ",".join(QUOTES)})
    return f"{API}?{q}"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nvnm-attest", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return json.loads(body)


def fetch():
    url = _url()
    payload = _get(url)
    date = payload.get("date")
    rates = payload.get("rates") or {}
    if not date or not rates:
        return []  # API returned no rate set; anchor nothing rather than a stub
    items = []
    for quote in QUOTES:
        if quote not in rates:
            continue  # a quote the API did not publish today; skip rather than anchor a stub
        items.append({
            "key": f"fx:{BASE}{quote}:{date}",
            "uri": url,  # the exact API call these points came from
            "data": {
                "base": BASE,
                "quote": quote,
                "rate": rates[quote],
                "date": date,
            },
        })
    return items
