"""Create a registry (a named container for your records). The wallet becomes its admin."""
import argparse
import nvnm

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--wallet", required=True)
p.add_argument("--name", required=True, help="e.g. hyperliquid-mid-prices")
p.add_argument("--description", default="")
p.add_argument("--owner", help="who runs this registry (public, optional)")
a = p.parse_args()

w3 = nvnm.connect()
acct = nvnm.load_account(a.wallet)
rid, tx, fee = nvnm.create_registry(w3, acct, a.name, a.description,
                                    {**({"owner": a.owner} if a.owner else {}), "kit": nvnm.KIT_VERSION})
print(f"Registry created: id {rid}  (fee ${fee:.6f})")
print(nvnm.tx_link(tx))
print(f"\nUse it with: --registry {rid}")
