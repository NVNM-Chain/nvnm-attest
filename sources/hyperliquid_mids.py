"""Hyperliquid mid prices for a few perps. Public data, high frequency.

One anchor per asset per run (BATCH = 1): every price point is its own transaction.
"""
import json
import os
import urllib.request

NAME = "hyperliquid-mids"
DEFAULT_EVERY = 60          # seconds
BATCH = 1                   # one transaction per data point
PUBLIC = True               # public market data: include the price in on-chain metadata
SYMBOLS = os.getenv("HL_SYMBOLS", "BTC,ETH,SOL,HYPE").split(",")


def fetch():
    req = urllib.request.Request("https://api.hyperliquid.xyz/info",
                                 data=json.dumps({"type": "allMids"}).encode(),
                                 headers={"Content-Type": "application/json"})
    mids = json.load(urllib.request.urlopen(req, timeout=15))
    return [{"key": s, "data": {"symbol": s, "mid": mids[s], "venue": "hyperliquid"}}
            for s in SYMBOLS if s in mids]
