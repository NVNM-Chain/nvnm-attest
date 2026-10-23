"""Attest one piece of data: a file, a text, or a JSON value. Anchors its SHA-256 hash."""
import argparse
import json
import time
import nvnm

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--wallet", required=True)
p.add_argument("--registry", type=int, required=True)
src = p.add_mutually_exclusive_group(required=True)
src.add_argument("--file", help="path to a file")
src.add_argument("--text", help="a text string")
src.add_argument("--json", help="a JSON string (hashed in canonical form)")
p.add_argument("--uri", default="", help="where the original data lives (PUBLIC; default urn:sha256:<checksum>)")
p.add_argument("--meta", action="append", default=[], help="extra metadata key=value (PUBLIC)")
a = p.parse_args()

if a.file:
    # the path stays local: it can name a person or a client, and metadata is public
    data, label = open(a.file, "rb").read(), "file"
elif a.text is not None:
    data, label = a.text.encode(), "text"
else:
    data, label = nvnm.canonical_json(json.loads(a.json)), "json"

checksum = nvnm.sha256_hex(data)
meta = {"src": label, "ts": int(time.time())}
meta.update(dict(kv.split("=", 1) for kv in a.meta))

w3 = nvnm.connect()
acct = nvnm.load_account(a.wallet)
res = nvnm.add_record(w3, acct, a.registry, checksum, meta, uri=a.uri)
nvnm.log_line(a.registry, {"checksum": checksum, "meta": meta, **res,
                           "data": data.decode(errors="replace") if not a.file else None,
                           "file": a.file})
print(f"Anchored sha256 {checksum}")
print(f"  registry {a.registry}, record {res['recordId']} v{res['index']}, block {res['block']}, fee ${res['fee_usd']:.6f}")
print(f"  {nvnm.tx_link(res['tx'])}")
