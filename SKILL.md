---
name: nvnm-attest
description: Attest (anchor) any data on the NVNM Chain L1 testnet (prices, datasets, files, documents, API results) and run bots that attest data on a schedule. Use this skill whenever the user wants to put data on NVNM, anchor or attest something, prove a file or dataset existed at a point in time, create an NVNM registry or wallet, run an attestation bot, or verify that data was anchored, even if they don't say "attest" or "anchor" explicitly.
---

# NVNM Attest

Helps anyone (no dev skills needed) attest data on the **NVNM Chain L1 testnet**. Attesting means: hash the data with SHA-256 and write that hash, plus a little metadata, to the Anchoring contract. Later anyone can re-hash the original data and check it against the chain.

## About fees (read this once)

Fees are paid in **nUSD**, the testnet stablecoin. There is no native gas token.

On the testnet, nUSD comes free from the faucet. The gas price moves with demand. Just make sure the wallet has nUSD. The scripts print the real fee of every transaction.

## Setup (once)

Everything runs from the kit folder with Python 3.10+. The RPC only accepts TLS 1.3, so macOS's built-in `python3` (3.9, LibreSSL) can't reach it. Use e.g. `brew install python@3.12`.

```bash
pip install web3
```

## Workflow

Follow these steps in order. Check what already exists before creating anything new (`python scripts/status.py --wallet <name>`).

### 1. Wallet: one per bot
```bash
python scripts/setup_wallet.py --name <bot-name>
```
Each bot or agent gets its own wallet ("Know Your Agent"). The key is saved in `wallets/<name>.json`. Never print, paste or commit the private key. The script also requests 100 nUSD from the faucet straight away (skip with `--no-faucet`).

### 2. Fund it with nUSD
Agents fund wallets themselves through the faucet API. No need to ask the user.
```bash
python scripts/faucet.py --wallet <bot-name>
```
- The faucet API is `POST https://faucet.nvnm.testnet.nvnmchain.io/api/faucet` with body `{"address": "0x..."}`. It sends 100 nUSD and returns `{"txHash", "amount"}`.
- Limits: **1 request per address per 24h, and 1 per IP per hour.** When you set up several bots from one machine, only the first wallet gets funded right away. Fund the others from it with `fund.py`, or wait an hour.
- Bots top themselves up: `attest_bot.py` checks the balance every 10 minutes and asks the faucet when it drops below 5 nUSD (turn off with `--no-faucet`).
- Or top up from another funded wallet: `python scripts/fund.py --from <funded-wallet> --to <address> --amount 20`
- People can also use the web form at https://faucet.nvnm.testnet.nvnmchain.io (same limits).
- Check: `python scripts/status.py --wallet <bot-name>`

### 3. Registry: one per data source
```bash
python scripts/create_registry.py --wallet <bot-name> --name <source-name> --description "<what is attested>"
```
Note the registry id it prints. The wallet that creates the registry is its admin and can add records.

### 4a. Attest once (a file, text or JSON)
```bash
python scripts/attest.py --wallet <bot-name> --registry <id> --file report.pdf
python scripts/attest.py --wallet <bot-name> --registry <id> --json '{"gold_usd": 2390.5}'
```

### 4b. Attest on a schedule (a bot)
Pick or create a source in `sources/`, test it dry, then run it:
```bash
python scripts/attest_bot.py --wallet <bot-name> --registry <id> --source sources/hyperliquid_mids.py --dry-run --max-runs 1
python scripts/attest_bot.py --wallet <bot-name> --registry <id> --source sources/hyperliquid_mids.py
```
For a new data source, copy `sources/_template.py` and write its `fetch()`. It returns a list of `{"key": ..., "data": {...}}`, optionally with a `"uri"` (a public link to the data) per point. Use public APIs where possible. Wrap requests with a timeout.

To keep a bot running after the session ends, suggest `nohup python scripts/attest_bot.py ... > bot.log 2>&1 &`, or a cron job, or a small cloud VM.

One runner per wallet (since v0.3). Two bots on one wallet anchor the same data twice, so `attest_bot.py` guards against it:
- It refuses to start if another bot process on this machine uses the wallet (`wallets/<name>.runner`).
- It also refuses if the wallet anchored in the last 10 minutes from somewhere else, such as another machine, a Cloudflare Worker or another session.
- While running, it stops at the first send after another runner used the wallet.
When it refuses, don't work around it. Find the other runner first. Pass `--takeover` only once you know the other runner is stopped. A bot that's moving to a new home needs a new wallet, or `--takeover` after the old one is stopped.

### 5. Verify
```bash
python scripts/verify.py --registry <id> --json '{"gold_usd": 2390.5}'
```

## Batching: the source decides

Each source sets `BATCH`:

| BATCH | What happens | Use when |
|---|---|---|
| `1` | One transaction per data point | Default. Few data points per run (e.g. 4 prices every minute) |
| `N` | Merkle root of N points per transaction | Many points per run at high frequency |
| `"all"` | One transaction per run (Merkle root of everything fetched) | Large snapshots (e.g. 50 rows hourly) |

Every point stays provable either way: the bot logs each item and its hash locally. Prefer `1` unless a source produces so many points that one-per-point would be silly or too costly.

## Rules

- **Anything can be attested**, and people decide what's useful. Two exceptions:
  - **No client or production data** on the testnet.
  - **No secrets or personal data** anywhere. The checksum is a hash, but `metadata` and `uri` are stored **in plain text, publicly**.
- Set `PUBLIC = True` in a source only for public data. It puts the data itself in onchain metadata.
- Keep the original data. Bots write it to `data/<registry>/<date>.jsonl` automatically. An anchor is only useful if the data can be re-hashed later.
- Choose cadences that make sense for the data: every few seconds for volatile prices, hourly or daily for slow data.

## Troubleshooting

| Message | Fix |
|---|---|
| `has no nUSD to pay fees` | Fund the wallet: `python scripts/faucet.py --wallet <bot-name>` (step 2) |
| Faucet `[HTTP 429]` | Limit reached (address: 24h, IP: 1h). Wait for the time it prints, or fund from another wallet with `fund.py` |
| Faucet `[HTTP 503]` | The faucet is empty or still sending to this address. Try later; check `curl -s https://faucet.nvnm.testnet.nvnmchain.io/api/faucet/balance` |
| `Cannot reach the NVNM RPC` | Usually an old Python without TLS 1.3 (the message says so). Use Python 3.10+ built with OpenSSL |
| `unauthorized` / missing role | The wallet isn't admin/editor of that registry. Use the registry's creator wallet or create your own registry |
| `metadata cannot be empty` | Metadata must be a non-empty JSON object. The scripts add `kit` automatically |
| `already used by process` / `made N anchors in the last 10 min` / `Another runner sent` | Another bot uses this wallet. Stop it, or give this bot its own wallet. `--takeover` only once the other runner is stopped |
| `uri cannot be empty` | The contract requires a `uri`. The kit fills in `urn:sha256:<checksum>` (since v0.2). Update an older copy of the kit |
| `... exceeds max length` | Limits: metadata and uri 2048 bytes, checksum 64. Keep `PUBLIC = True` data small |
| `sender not an eoa` | Calls must come from a normal wallet, not a contract |
| `NOT FOUND` on verify | The data differs by even one byte, or it was anchored in another registry. JSON is hashed in canonical form (sorted keys, no spaces) |
| `Wrong network` | Check `NVNM_RPC_URL` / `NVNM_CHAIN_ID` |

## Reference

For contract details (functions, record fields, events, permissions), read `references/anchoring-module.md`. Network:

- Chain: `nvnm-next-testnet-1`, EVM chain ID `787223`
- RPC: `https://rpc.nvnm.testnet.nvnmchain.io`
- Explorer: `https://explorer.nvnm.testnet.nvnmchain.io`
- Faucet API: `POST https://faucet.nvnm.testnet.nvnmchain.io/api/faucet` `{"address": "0x..."}` (100 nUSD), health: `GET .../api/faucet/balance`
- Anchoring contract: `0x0000000000000000000000000000000000000A00`
- nUSD (fee token, 6 decimals): `0x20C0000000000000000000000000000000000000`
