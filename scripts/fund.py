"""Send nUSD from one of your wallets to another address (top up a bot)."""
import argparse
import nvnm

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--from", dest="src", required=True, help="wallet name that pays")
p.add_argument("--to", required=True, help="address that receives")
p.add_argument("--amount", type=float, required=True, help="nUSD amount")
a = p.parse_args()

w3 = nvnm.connect()
acct = nvnm.load_account(a.src)
token = nvnm.nusd(w3)
tx, _, fee = nvnm.send(w3, acct, token.functions.transfer(
    nvnm.Web3.to_checksum_address(a.to), int(a.amount * 1e6)))
print(f"Sent {a.amount} nUSD to {a.to} (fee ${fee:.6f})")
print(nvnm.tx_link(tx))
