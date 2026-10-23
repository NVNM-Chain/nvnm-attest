"""TEMPLATE: copy this file to make a new data source.

1. Copy:  cp sources/_template.py sources/my_source.py
2. Fill in NAME, DEFAULT_EVERY, BATCH, PUBLIC and fetch()
3. Test:  python scripts/attest_bot.py --wallet <w> --registry <id> --source sources/my_source.py --dry-run --max-runs 1
"""

NAME = "my-source"          # short, unique name; shows up in every record's metadata
DEFAULT_EVERY = 300         # seconds between fetches
BATCH = 1                   # 1 = one tx per data point | N = Merkle batch of N | "all" = one tx per fetch
PUBLIC = False              # True = put the data itself in on-chain metadata (only for public data!)


def fetch():
    """Return a list of data points. Each needs a unique 'key' and JSON-serialisable 'data'.

    Optional per point: 'uri', a public link to where the data lives (stored on chain).
    Without one, the kit uses urn:sha256:<checksum>.
    """
    return [
        {"key": "example-1", "data": {"value": 42}},
    ]
