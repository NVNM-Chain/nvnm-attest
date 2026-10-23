# NVNM Attest Kit

Put data on the NVNM Chain testnet by talking to Claude. No coding needed.

**What it does:** takes any data (a price, a file, a dataset, an API result), creates a fingerprint of it (a SHA-256 hash) and writes that fingerprint to NVNM Chain. Later, anyone can prove the data existed at that moment and hasn't changed. It can also run bots that do this on their own, every few seconds, minutes or hours.

## Before you start

- **Use kit 0.3.1 or newer.** Ask Claude "which nvnm-attest version is installed?" or look for `KIT_VERSION` in `scripts/nvnm.py`. Version 0.1 sends an empty uri, which the contract rejects, so every anchor fails. Versions before 0.3.1 also put a file's full path (which can include your name) in the public metadata.
- **On a Mac, install Python 3.12:** `brew install python@3.12`. The built-in `python3` can't reach the network, because its TLS is too old. Claude installs the `web3` package itself on first use.

## Install

| Where | Good for | How |
|---|---|---|
| Claude Code (terminal, desktop app's Code tab, IDE) | Bots that run for hours or days | `git clone https://github.com/NVNM-Chain/nvnm-attest ~/.claude/skills/nvnm-attest` (or into a project's `.claude/skills/`) |
| Claude.ai | One-off attestations | Download the [kit zip](https://github.com/NVNM-Chain/nvnm-attest/archive/refs/heads/main.zip) and upload it in claude.ai's skill settings |

A bot started in a claude.ai chat stops when the chat does. For a bot that keeps running, use Claude Code.

## Anchor something in 3 steps

**1. Ask Claude.** Copy one of these:

- "Attest this PDF on NVNM and show me the transaction."
- "Set up a wallet and a registry for attesting Hyperliquid prices on NVNM, then run the bot every minute."
- "Make a new NVNM source that attests the gold and oil price every hour from a free API."
- "Create a bot that attests the top 50 chains by TVL from DefiLlama daily."

Claude handles every step: wallet, funding, registry, attesting. Each new wallet gets 100 test nUSD from the faucet automatically, and running bots top themselves up.

**2. Check it landed.** A bot logging "success" isn't proof. Ask Claude for the transaction link (`https://explorer.nvnm.testnet.nvnmchain.io/tx/0x…`), then ask it to "verify this data in registry N". You want `VERIFIED`.

**3. Keep it running.** One wallet per bot, and one copy of each bot. The kit refuses to start a second runner on the same wallet, so a bot can't anchor the same record twice.

## About fees

NVNM Chain has no native gas token: fees are paid in nUSD, a stablecoin. On the testnet that is test nUSD from the faucet, so anchoring costs you nothing. The scripts print the fee of every transaction.

## Rules

- Attest **anything** you think is interesting, with these exceptions:
  - **no client or production data** on the testnet;
  - **no secrets or personal data**. Metadata is public;
  - **no hash of a small value** (one price, one rent figure) on its own: it can be guessed back. Salt it or leave it off.
- One wallet per bot. Its key stays in the kit's `wallets/` folder on your machine. Never paste it into chat or commit it.
- Pick a cadence that fits the data: fast-moving prices every few seconds or minutes, slow data hourly or daily.

## When something goes wrong

| You see | What it means | Do this |
|---|---|---|
| `faucet limit reached` (429) | The faucet gives 1 request per address per 24h and 1 per IP per hour | Wait an hour, or ask Claude to fund the new wallet from one you already have |
| A bot won't start: another runner uses the wallet | The single-runner guard | Stop the other copy. If it's already gone, wait 10 minutes |
| Every anchor fails or reverts | An old kit version (0.1) | Install the latest kit |
| A TLS or SSL error | macOS's built-in Python | `brew install python@3.12` |
| Error 1015 or 429 from the RPC | The RPC's per-IP rate limit | Wait about 5 minutes, then retry |

## Ideas to start with

Hyperliquid perps and spot prices · Derive options versus Hyperliquid · tokenized versus listed equity prices · GPU/CPU rental prices · commodity prices · inflation and index data · DefiLlama TVL · trading card prices · sports and fantasy data.

## What's in the folder

| Path | What it is |
|---|---|
| `SKILL.md` | Instructions Claude follows |
| `scripts/setup_wallet.py` | Create a wallet for a bot |
| `scripts/fund.py` | Send nUSD from one wallet to another |
| `scripts/status.py` | Network, balance and registry check |
| `scripts/create_registry.py` | Create a registry (container for records) |
| `scripts/attest.py` | Attest one file / text / JSON |
| `scripts/attest_bot.py` | Run a scheduled attestation bot |
| `scripts/verify.py` | Check if data was anchored |
| `scripts/faucet.py` | Ask the faucet for test nUSD |
| `sources/` | Data sources for bots: Hyperliquid, DefiLlama, and a template for your own |
| `references/anchoring-module.md` | Contract details |
