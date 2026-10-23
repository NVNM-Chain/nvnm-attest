"""Create a new wallet for one bot or agent (one wallet per bot), and fund it from the faucet."""
import argparse
import nvnm

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--name", required=True, help="short name for the bot, e.g. hl-prices")
p.add_argument("--no-faucet", action="store_true", help="don't request nUSD from the faucet")
a = p.parse_args()

w = nvnm.create_wallet(a.name)
print(f"Created wallet '{a.name}'")
print(f"  Address: {w['address']}")
print(f"  Saved to: {nvnm.wallet_path(a.name)} (keep this file private, never commit it)")

funded = False
if not a.no_faucet:
    try:
        res = nvnm.request_faucet(w["address"])
        print(f"\nFunded: the faucet sent {res.get('amount')} nUSD (pays the fees)")
        print(f"  {nvnm.tx_link(res['txHash'])}")
        print(f"  Balance: {nvnm.wait_for_nusd(nvnm.connect(), w['address'], timeout=30):.4f} nUSD")
        funded = True
    except nvnm.FaucetError as e:
        print(f"\nCouldn't fund it from the faucet: {e}")

if not funded:
    print("\nNext: fund it with nUSD (pays the fees)")
    print(f"  Option A: python scripts/faucet.py --wallet {a.name}  (or the web form at {nvnm.FAUCET})")
    print(f"  Option B: from another funded wallet: python scripts/fund.py --from <funded-wallet> --to {w['address']} --amount 20")
