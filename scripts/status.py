"""Show network status, and optionally a wallet's balance and the registries on chain."""
import argparse
import nvnm

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--wallet", help="wallet name to check")
p.add_argument("--registries", action="store_true", help="list the newest registries")
a = p.parse_args()

w3 = nvnm.connect()
gp = w3.eth.gas_price
print(f"Network: chain {nvnm.CHAIN_ID}, block {w3.eth.block_number}")
print(f"Gas price: {gp} attodollars/gas  (~${gp * 5_700_000 / 1e18:.4f} per anchor at ~5.7M gas, estimate only)")
if a.wallet:
    acct = nvnm.load_account(a.wallet)
    print(f"Wallet '{a.wallet}': {acct.address}  balance {nvnm.nusd_balance(w3, acct.address):.4f} nUSD")
if a.registries:
    regs, total = nvnm.list_registries(w3, limit=20)
    print(f"Newest {len(regs)} registries on chain:")
    for r in regs:
        print(f"  #{r['id']:<6} {r['name']:<30} created {r['createdAt']}")
