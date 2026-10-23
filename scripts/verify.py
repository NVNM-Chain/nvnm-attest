"""Check whether a file / text / JSON value was anchored: re-hash it and look it up on chain."""
import argparse
import json
import nvnm

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--registry", type=int, required=True)
src = p.add_mutually_exclusive_group(required=True)
src.add_argument("--file")
src.add_argument("--text")
src.add_argument("--json")
src.add_argument("--checksum", help="a hash you already have")
a = p.parse_args()

if a.checksum:
    checksum = a.checksum
elif a.file:
    checksum = nvnm.sha256_hex(open(a.file, "rb").read())
elif a.text is not None:
    checksum = nvnm.sha256_hex(a.text.encode())
else:
    checksum = nvnm.sha256_hex(nvnm.canonical_json(json.loads(a.json)))

w3 = nvnm.connect()
recs = nvnm.find_records(w3, a.registry, checksum)
if not recs:
    print(f"NOT FOUND: sha256 {checksum} is not anchored in registry {a.registry}")
    raise SystemExit(1)
print(f"VERIFIED: sha256 {checksum} is anchored in registry {a.registry}")
for r in recs:
    print(f"  record {r['recordId']} v{r['index']}  at {r['timestamp']}  status={r['status']}  latest={r['isLatest']}")
    print(f"  metadata: {r['metadata']}")
