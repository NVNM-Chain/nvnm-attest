"""Get 100 test nUSD from the faucet for a wallet, so it can pay fees.

Limits: 1 request per address per 24h, and 1 per IP per hour.
"""
import argparse
import nvnm

p = argparse.ArgumentParser(description=__doc__)
who = p.add_mutually_exclusive_group(required=True)
who.add_argument("--wallet", help="wallet name, e.g. hl-prices")
who.add_argument("--address", help="any 0x address")
a = p.parse_args()

address = a.address or nvnm.load_account(a.wallet).address
try:
    res = nvnm.request_faucet(address)
except nvnm.FaucetError as e:
    raise SystemExit(f"No nUSD sent: {e}\nOther options: the web form at {nvnm.FAUCET} (same limits), or another funded "
                     f"wallet: python scripts/fund.py --from <funded-wallet> --to {address} --amount 20")
print(f"Faucet sent {res.get('amount')} nUSD to {address}")
print(nvnm.tx_link(res["txHash"]))
print(f"Balance: {nvnm.wait_for_nusd(nvnm.connect(), address):.4f} nUSD")
