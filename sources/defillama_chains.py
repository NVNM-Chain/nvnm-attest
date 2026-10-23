"""Top chains by TVL from DefiLlama. Public data, low frequency.

One fetch returns many rows, so they are anchored together as one Merkle batch
(BATCH = "all"): one transaction per run, every row still individually provable.
"""
import json
import urllib.request

NAME = "defillama-chain-tvl"
DEFAULT_EVERY = 3600        # hourly
BATCH = "all"               # one transaction per run (Merkle root of all rows)
PUBLIC = False
TOP_N = 50


def fetch():
    req = urllib.request.Request("https://api.llama.fi/v2/chains", headers={"User-Agent": "nvnm-attest"})
    chains = json.load(urllib.request.urlopen(req, timeout=20))
    chains = sorted(chains, key=lambda c: c.get("tvl") or 0, reverse=True)[:TOP_N]
    return [{"key": c["name"], "data": {"chain": c["name"], "tvl_usd": c.get("tvl")}} for c in chains]
