"""Run a bot that fetches data from a source on a schedule and attests it on NVNM.

A "source" is a small Python file in sources/ with a fetch() function. The source
decides how its data is anchored (one transaction per data point, or batched).
"""
import argparse
import atexit
import importlib.util
import time
from pathlib import Path
import nvnm


def load_source(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr in ("NAME", "fetch"):
        if not hasattr(mod, attr):
            raise SystemExit(f"Source {path} must define {attr}")
    return mod


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_once(w3, acct, src, registry, batch, public, dry_run, guard):
    fetched_at = int(time.time())
    items = src.fetch()
    for it in items:
        it["hash"] = nvnm.sha256_hex(nvnm.canonical_json(it["data"]))
    size = len(items) if batch == "all" else int(batch)
    sent, fees = 0, 0.0
    for group in chunks(items, max(size, 1)):
        if len(group) == 1:
            it = group[0]
            checksum, uri = it["hash"], it.get("uri", "")
            meta = {"src": src.NAME, "key": it["key"], "ts": fetched_at}
            if public:
                meta["data"] = it["data"]
        else:
            checksum, uri = nvnm.merkle_root([g["hash"] for g in group]), ""
            meta = {"src": src.NAME, "type": "merkle-batch", "count": len(group),
                    "first": group[0]["key"], "last": group[-1]["key"], "ts": fetched_at}
        if dry_run:
            print(f"  [dry-run] would anchor {checksum[:16]}... {meta}")
            continue
        res = nvnm.add_record(w3, acct, registry, checksum, meta, uri=uri, guard=guard)
        sent += 1
        fees += res["fee_usd"] or 0
        nvnm.log_line(registry, {"checksum": checksum, "meta": meta, **res,
                                 "items": [{"key": g["key"], "data": g["data"], "hash": g["hash"]} for g in group]})
    return len(items), sent, fees


LOW_BALANCE = 5.0           # nUSD; below this the bot asks the faucet for more
BALANCE_CHECK_EVERY = 600   # seconds between balance checks


def top_up(w3, address, state):
    """Keep a long-running bot funded: below LOW_BALANCE, request 100 nUSD from the faucet.

    The faucet allows 1 request per address per 24h, so after a refusal we wait as long as it says.
    Returns True if the faucet sent nUSD.
    """
    now = time.time()
    if now < state["next_check"]:
        return False
    state["next_check"] = now + BALANCE_CHECK_EVERY
    bal = nvnm.nusd_balance(w3, address)
    if bal >= LOW_BALANCE or now < state["next_faucet"]:
        return False
    try:
        res = nvnm.request_faucet(address)
    except nvnm.FaucetError as e:
        state["next_faucet"] = now + (e.retry_after or 3600)
        print(f"[{time.strftime('%H:%M:%S')}] balance {bal:.2f} nUSD, faucet: {e}")
        return False
    print(f"[{time.strftime('%H:%M:%S')}] balance {bal:.2f} nUSD, faucet sent {res.get('amount')} nUSD: "
          f"{nvnm.tx_link(res['txHash'])}")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wallet", required=True)
    p.add_argument("--registry", type=int, required=True)
    p.add_argument("--source", required=True, help="path to a source file, e.g. sources/hyperliquid_mids.py")
    p.add_argument("--every", type=float, help="seconds between runs (default: the source's DEFAULT_EVERY)")
    p.add_argument("--batch", help="override the source's BATCH: 1, a number, or 'all'")
    p.add_argument("--max-runs", type=int, default=0, help="stop after N runs (0 = run forever)")
    p.add_argument("--dry-run", action="store_true", help="fetch and hash, but send nothing")
    p.add_argument("--no-faucet", action="store_true", help="don't top up from the faucet when nUSD runs low")
    p.add_argument("--takeover", action="store_true",
                   help="start even though this wallet anchored recently from elsewhere (only once that runner is stopped)")
    a = p.parse_args()

    src = load_source(a.source)
    every = a.every or getattr(src, "DEFAULT_EVERY", 60)
    batch = a.batch or str(getattr(src, "BATCH", 1))
    public = getattr(src, "PUBLIC", False)

    w3 = nvnm.connect()
    acct = None if a.dry_run else nvnm.load_account(a.wallet)
    auto_fund = acct is not None and not a.no_faucet
    funding = {"next_check": 0, "next_faucet": 0}
    guard = None
    if acct:
        try:
            guard = nvnm.claim_wallet(w3, a.wallet, acct.address, takeover=a.takeover)
        except nvnm.WalletInUse as e:
            raise SystemExit(str(e))
        atexit.register(nvnm.release_wallet, guard)
        if auto_fund and top_up(w3, acct.address, funding):
            nvnm.wait_for_nusd(w3, acct.address, timeout=30)
        bal = nvnm.nusd_balance(w3, acct.address)
        print(f"Wallet {acct.address}: {bal:.4f} nUSD")
        if bal <= 0:
            raise SystemExit(f"Wallet has no nUSD. Fund it: python scripts/faucet.py --wallet {a.wallet}")
    print(f"Bot '{src.NAME}' -> registry {a.registry}, every {every}s, batch={batch}, public data={public}")

    runs, total_tx, total_fee, backoff = 0, 0, 0.0, every
    while True:
        start = time.time()
        try:
            if auto_fund:
                top_up(w3, acct.address, funding)
            n_items, n_tx, fee = run_once(w3, acct, src, a.registry, batch, public, a.dry_run, guard)
            total_tx += n_tx
            total_fee += fee
            backoff = every
            avg = f", avg fee ${total_fee / total_tx:.6f}/tx" if total_tx else ""
            print(f"[{time.strftime('%H:%M:%S')}] run {runs + 1}: {n_items} items, {n_tx} tx "
                  f"(total {total_tx} tx, ${total_fee:.4f}{avg})")
        except nvnm.WalletInUse as e:
            raise SystemExit(f"[{time.strftime('%H:%M:%S')}] stopped: {e}")
        except Exception as e:  # keep the bot alive; back off on errors
            backoff = min(backoff * 2, 600)
            print(f"[{time.strftime('%H:%M:%S')}] error: {e} (retrying in {backoff:.0f}s)")
        runs += 1
        if a.max_runs and runs >= a.max_runs:
            break
        time.sleep(max(0, backoff - (time.time() - start)))


if __name__ == "__main__":
    main()
