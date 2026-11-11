"""Shared helpers for attesting data on the NVNM Chain L1 testnet.

Everything the other scripts need lives here: network config, the Anchoring
contract ABI, wallet loading, sending transactions, hashing and Merkle roots.
"""
import hashlib
import json
import math
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from eth_account import Account
from web3 import Web3
from web3.logs import DISCARD

# --- Network (NVNM Chain NEXT, Testnet 1) -----------------------------------
RPC_URL = os.getenv("NVNM_RPC_URL", "https://rpc.nvnm.testnet.nvnmchain.io")
CHAIN_ID = int(os.getenv("NVNM_CHAIN_ID", "787223"))
EXPLORER = os.getenv("NVNM_EXPLORER", "https://explorer.nvnm.testnet.nvnmchain.io")
FAUCET = "https://faucet.nvnm.testnet.nvnmchain.io"
FAUCET_API = os.getenv("NVNM_FAUCET_API", f"{FAUCET}/api/faucet")  # POST {"address": "0x..."} -> 100 nUSD

ANCHORING = Web3.to_checksum_address("0x0000000000000000000000000000000000000A00")
NUSD = Web3.to_checksum_address("0x20C0000000000000000000000000000000000000")  # fee token, 6 decimals
KIT_VERSION = "nvnm-attest/0.3.4"

KIT_DIR = Path(__file__).resolve().parent.parent
WALLET_DIR = Path(os.getenv("NVNM_WALLET_DIR", KIT_DIR / "wallets"))
DATA_DIR = Path(os.getenv("NVNM_DATA_DIR", KIT_DIR / "data"))

# --- ABI ---------------------------------------------------------------------
_RECORD = {
    "type": "tuple",
    "components": [
        {"name": "uri", "type": "string"},
        {"name": "checksum", "type": "string"},
        {"name": "checksumAlgo", "type": "string"},
        {"name": "metadata", "type": "string"},
        {"name": "timestamp", "type": "string"},
        {"name": "status", "type": "string"},
        {"name": "recordId", "type": "uint64"},
        {"name": "index", "type": "uint64"},
        {"name": "isLatest", "type": "bool"},
        {"name": "registryId", "type": "uint64"},
    ],
}
_REGISTRY = {
    "type": "tuple",
    "components": [
        {"name": "id", "type": "uint64"},
        {"name": "name", "type": "string"},
        {"name": "description", "type": "string"},
        {"name": "creator", "type": "string"},
        {"name": "createdAt", "type": "string"},
        {"name": "metadata", "type": "string"},
    ],
}
_PAGE_REQ = {
    "type": "tuple",
    "name": "pagination",
    "components": [
        {"name": "key", "type": "bytes"},
        {"name": "offset", "type": "uint64"},
        {"name": "limit", "type": "uint64"},
        {"name": "countTotal", "type": "bool"},
        {"name": "reverse", "type": "bool"},
    ],
}
_PAGE_RESP = {
    "type": "tuple",
    "name": "page",
    "components": [{"name": "nextKey", "type": "bytes"}, {"name": "total", "type": "uint64"}],
}

ANCHORING_ABI = [
    {"type": "function", "name": "addRegistry", "stateMutability": "nonpayable",
     "inputs": [{"name": "name", "type": "string"}, {"name": "description", "type": "string"},
                {"name": "metadata", "type": "string"}],
     "outputs": [{"name": "registryId", "type": "uint64"}]},
    {"type": "function", "name": "addRecord", "stateMutability": "nonpayable",
     "inputs": [dict(_RECORD, name="record")], "outputs": []},
    {"type": "function", "name": "updateRecordStatus", "stateMutability": "nonpayable",
     "inputs": [{"name": "registryId", "type": "uint64"}, {"name": "recordId", "type": "uint64"},
                {"name": "index", "type": "uint64"}, {"name": "status", "type": "string"}],
     "outputs": []},
    {"type": "function", "name": "grantRole", "stateMutability": "nonpayable",
     "inputs": [{"name": "registryId", "type": "uint64"}, {"name": "checksum", "type": "string"},
                {"name": "account", "type": "address"}, {"name": "role", "type": "string"}],
     "outputs": []},
    {"type": "function", "name": "records", "stateMutability": "view",
     "inputs": [{"name": "registryId", "type": "uint64"}, {"name": "checksum", "type": "string"},
                {"name": "recordId", "type": "uint64"}, {"name": "index", "type": "uint64"}, _PAGE_REQ],
     "outputs": [dict(_RECORD, name="records", type="tuple[]"), _PAGE_RESP]},
    {"type": "function", "name": "registries", "stateMutability": "view",
     "inputs": [{"name": "registryId", "type": "uint64"}, _PAGE_REQ],
     "outputs": [dict(_REGISTRY, name="registries", type="tuple[]"), _PAGE_RESP]},
    {"type": "event", "name": "AddRegistry", "anonymous": False,
     "inputs": [{"name": "caller", "type": "address", "indexed": True},
                {"name": "registryId", "type": "uint64", "indexed": False},
                {"name": "name", "type": "string", "indexed": False}]},
    {"type": "event", "name": "AddRecord", "anonymous": False,
     "inputs": [{"name": "caller", "type": "address", "indexed": True},
                {"name": "registryId", "type": "uint64", "indexed": False},
                {"name": "recordId", "type": "uint64", "indexed": False},
                {"name": "index", "type": "uint64", "indexed": False},
                {"name": "checksum", "type": "string", "indexed": False}]},
]


def _bytes_for_strings(t):
    """`t` with every string read as bytes. Both share one ABI encoding, and bytes can't fail to decode."""
    if t["type"] == "string":
        return dict(t, type="bytes")
    if "components" in t:
        return dict(t, components=[_bytes_for_strings(c) for c in t["components"]])
    return t


# Reads decode strings as bytes first. The contract accepts any bytes in a record, binary data included,
# and web3's strict UTF-8 decode crashed verify.py on such records.
_READ_ABI = [dict(f, outputs=[_bytes_for_strings(o) for o in f["outputs"]])
             for f in ANCHORING_ABI if f.get("stateMutability") == "view"]

ERC20_ABI = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"type": "function", "name": "transfer", "stateMutability": "nonpayable",
     "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
]


# --- Connection --------------------------------------------------------------
def connect() -> Web3:
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        hint = ""
        if sys.version_info < (3, 10) or "LibreSSL" in ssl.OPENSSL_VERSION:
            hint = (f"\nThis Python ({sys.version.split()[0]}, {ssl.OPENSSL_VERSION}) can't speak TLS 1.3, which the "
                    "RPC requires. Use Python 3.10+ built with OpenSSL, e.g. `brew install python@3.12`.")
        sys.exit(f"Cannot reach the NVNM RPC at {RPC_URL}{hint}")
    if w3.eth.chain_id != CHAIN_ID:
        sys.exit(f"Wrong network: expected chain ID {CHAIN_ID}, got {w3.eth.chain_id}")
    return w3


def anchoring(w3):
    return w3.eth.contract(address=ANCHORING, abi=ANCHORING_ABI)


def nusd(w3):
    return w3.eth.contract(address=NUSD, abi=ERC20_ABI)


# --- Wallets -----------------------------------------------------------------
def wallet_path(name: str) -> Path:
    return WALLET_DIR / f"{name}.json"


def create_wallet(name: str) -> dict:
    path = wallet_path(name)
    if path.exists():
        sys.exit(f"Wallet '{name}' already exists at {path}")
    WALLET_DIR.mkdir(parents=True, exist_ok=True)
    acct = Account.create()
    data = {"name": name, "address": acct.address, "private_key": acct.key.hex()}
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)
    return data


def load_account(name: str):
    """Load a wallet by name, or from NVNM_PRIVATE_KEY if set."""
    key = os.getenv("NVNM_PRIVATE_KEY")
    if key:
        return Account.from_key(key)
    path = wallet_path(name)
    if not path.exists():
        sys.exit(f"No wallet '{name}'. Create one first: python scripts/setup_wallet.py --name {name}")
    return Account.from_key(json.loads(path.read_text())["private_key"])


def nusd_balance(w3, address) -> float:
    return nusd(w3).functions.balanceOf(address).call() / 1e6


def has_pending(w3, address) -> bool:
    """True while a transaction from this address is sent but not yet in a block."""
    return w3.eth.get_transaction_count(address, "pending") > w3.eth.get_transaction_count(address, "latest")


# --- Faucet ------------------------------------------------------------------
class FaucetError(RuntimeError):
    def __init__(self, status, message, retry_after=None):
        self.status, self.retry_after = status, retry_after
        super().__init__(message)


_FAUCET_HINTS = {
    400: "the faucet rejected the address (it must be a 0x EVM address, not nvnm1...)",
    429: "faucet limit reached: 1 request per address per 24h and 1 per IP per hour",
    503: "the faucet is empty or busy with a transfer to this address",
}


def request_faucet(address: str) -> dict:
    """Ask the testnet faucet for 100 nUSD. Returns {"txHash", "amount"} or raises FaucetError.

    Limits (best effort): 1 request per address per 24h, 1 request per IP per hour.
    """
    req = urllib.request.Request(FAUCET_API, method="POST", data=json.dumps({"address": address}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": KIT_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("error")
        except Exception:
            detail = None
        retry = int(e.headers.get("Retry-After") or 0) or None
        msg = f"{detail or _FAUCET_HINTS.get(e.code, 'unknown error')} [HTTP {e.code}]"
        if retry:
            msg += f", retry in {retry // 60 + 1} min" if retry < 7200 else f", retry in {retry / 3600:.0f} h"
        raise FaucetError(e.code, msg, retry) from None


def wait_for_nusd(w3, address, above=0.0, timeout=60) -> float:
    """Poll until the wallet's nUSD balance is above `above`, e.g. right after a faucet transfer."""
    deadline = time.time() + timeout
    while True:
        bal = nusd_balance(w3, address)
        if bal > above or time.time() > deadline:
            return bal
        time.sleep(2)


# --- Sending -----------------------------------------------------------------
def send(w3, acct, fn, gas_fallback=8_000_000, wait=True, guard=None):
    """Build, sign and send a contract call. Returns (tx_hash, receipt, fee_usd).

    With a guard from claim_wallet(), it refuses to send if another runner has used the wallet since the last send.
    """
    gas_price = w3.eth.gas_price
    nonce = w3.eth.get_transaction_count(acct.address, "pending")
    if guard is not None and nonce > guard["next_nonce"]:
        raise WalletInUse(f"Another runner sent {nonce - guard['next_nonce']} tx(s) from {acct.address} since this "
                          "bot's last send. One wallet per bot, so this bot stops here.")
    tx = fn.build_transaction({
        "from": acct.address,
        "chainId": CHAIN_ID,
        "nonce": nonce,
        "maxFeePerGas": gas_price * 2,
        "maxPriorityFeePerGas": 0,
        "gas": gas_fallback,
    })
    try:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.3)
    except Exception as e:  # surface the revert reason, it is usually the useful part
        msg = str(e)
        if "exceeds allowance (0)" in msg or "insufficient" in msg.lower():
            raise RuntimeError(f"Wallet {acct.address} has no nUSD to pay fees. Fund it: {FAUCET}") from None
        raise RuntimeError(f"Transaction would fail: {msg}") from None
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    if guard is not None:
        guard["next_nonce"] = nonce + 1
    if not wait:
        return tx_hash.hex(), None, None
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if guard is not None:
        guard["last_block"] = receipt.blockNumber
        _save_runner(guard, os.getpid())
    if receipt.status != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")
    price = receipt.get("effectiveGasPrice", gas_price)
    fee_usd = math.ceil(price * receipt.gasUsed / 10**12) / 1e6  # attodollars -> microdollars -> USD
    return tx_hash.hex(), receipt, fee_usd


# --- One runner per wallet ---------------------------------------------------
# Two bots on one wallet anchor the same data twice and race for nonces, so a bot claims its wallet
# before it starts, and send() checks the nonce before every transaction.
ADD_RECORD_TOPIC = "0x1a3295fa8cc0e28c95d21912c9e6958f3bc740231781f7640ad885c972a352fd"
RECENT_SECONDS = 600


class WalletInUse(RuntimeError):
    pass


def claim_wallet(w3, name, address, takeover=False):
    """Refuse to start when another runner uses this wallet, then record this process as its runner.

    Another runner is a live process on this machine (wallets/<name>.runner), or anchors from this wallet
    in the last RECENT_SECONDS that this machine's runner didn't send. Returns the guard for send().
    """
    path = WALLET_DIR / f"{name}.runner"
    state = json.loads(path.read_text()) if path.exists() else {}
    pid, host = state.get("pid"), socket.gethostname()
    if not takeover and pid and pid != os.getpid() and state.get("host") == host and _alive(pid):
        raise WalletInUse(f"Wallet '{name}' is already used by process {pid} on this machine. Stop that bot first.")
    if not takeover:
        try:
            foreign = _recent_anchors(w3, address, after_block=state.get("last_block", -1))
        except Exception as e:  # e.g. the RPC's rate limit; the nonce check in send() still guards the run
            foreign = []
            print(f"Could not check this wallet's recent anchors ({e}). The nonce check still guards this run.")
        if foreign:
            raise WalletInUse(
                f"Wallet '{name}' ({address}) made {len(foreign)} anchors in the last {RECENT_SECONDS // 60} min "
                f"that this machine's runner didn't send. Latest: {tx_link(foreign[-1]['transactionHash'].hex())}. "
                "One wallet per bot: stop the other runner, or give this bot its own wallet. "
                f"If the other runner is already stopped, wait {RECENT_SECONDS // 60} min or pass --takeover.")
    guard = {"path": path, "host": host, "last_block": state.get("last_block", -1),
             "next_nonce": w3.eth.get_transaction_count(address, "pending")}
    _save_runner(guard, os.getpid())
    return guard


def release_wallet(guard):
    _save_runner(guard, None)


def _save_runner(guard, pid):
    guard["path"].write_text(json.dumps({"pid": pid, "host": guard["host"], "last_block": guard["last_block"],
                                         "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2))


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _recent_anchors(w3, address, after_block):
    latest = w3.eth.block_number
    seconds_per_block = (w3.eth.get_block(latest)["timestamp"] - w3.eth.get_block(latest - 1000)["timestamp"]) / 1000
    start = max(latest - int(RECENT_SECONDS / max(seconds_per_block, 0.01)), after_block + 1)
    if start > latest:
        return []
    return w3.eth.get_logs({"address": ANCHORING, "fromBlock": start, "toBlock": latest,
                            "topics": [ADD_RECORD_TOPIC, "0x" + address[2:].lower().rjust(64, "0")]})


# --- Hashing -----------------------------------------------------------------
def canonical_json(obj) -> bytes:
    """Stable bytes for JSON data, so the same data always gives the same hash."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_root(leaves_hex):
    """SHA-256 Merkle root over hex leaf hashes (last leaf duplicated on odd levels)."""
    level = [bytes.fromhex(h) for h in leaves_hex]
    if not level:
        raise ValueError("No leaves")
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


# --- Anchoring ---------------------------------------------------------------
def create_registry(w3, acct, name, description, metadata: dict):
    c = anchoring(w3)
    meta = json.dumps(metadata or {"kit": KIT_VERSION})
    tx, receipt, fee = send(w3, acct, c.functions.addRegistry(name, description, meta))
    ev = c.events.AddRegistry().process_receipt(receipt, errors=DISCARD)  # skip the nUSD fee log
    return ev[0]["args"]["registryId"], tx, fee


def add_record(w3, acct, registry_id, checksum, metadata: dict, uri="", status="active",
               algo="sha256", wait=True, guard=None):
    meta = dict(metadata or {})
    meta.setdefault("kit", KIT_VERSION)  # metadata must not be empty or "{}"
    uri = uri or f"urn:sha256:{checksum}"  # the contract rejects an empty uri
    record = (uri, checksum, algo, json.dumps(meta, separators=(",", ":")), "", status,
              0, 0, False, int(registry_id))
    c = anchoring(w3)
    tx, receipt, fee = send(w3, acct, c.functions.addRecord(record), wait=wait, guard=guard)
    if receipt is None:
        return {"tx": tx}
    ev = c.events.AddRecord().process_receipt(receipt, errors=DISCARD)[0]["args"]
    return {"tx": tx, "recordId": ev["recordId"], "index": ev["index"], "fee_usd": fee,
            "block": receipt.blockNumber}


def _reader(w3):
    return w3.eth.contract(address=ANCHORING, abi=_READ_ABI)


def _as_dict(struct, row):
    """Name a struct's fields. Invalid UTF-8 becomes U+FFFD instead of raising."""
    return {c["name"]: v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v
            for c, v in zip(struct["components"], row)}


def find_records(w3, registry_id=0, checksum="", limit=50):
    try:
        recs, _page = _reader(w3).functions.records(
            int(registry_id), checksum, 0, 0, (b"", 0, limit, False, True)).call()
    except Exception as e:  # the contract reverts with "record does not exist" when nothing matches
        if "does not exist" in str(e):
            return []
        raise
    return [_as_dict(_RECORD, r) for r in recs]


def list_registries(w3, registry_id=0, limit=50):
    regs, page = _reader(w3).functions.registries(int(registry_id), (b"", 0, limit, True, True)).call()
    return [_as_dict(_REGISTRY, r) for r in regs], page[1]


def log_line(registry_id, entry: dict):
    """Keep the original data locally: an anchor is only useful if the data can be re-hashed later."""
    d = DATA_DIR / str(registry_id)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{time.strftime('%Y-%m-%d')}.jsonl", "a+b") as f:
        end = f.seek(0, os.SEEK_END)
        if end:
            f.seek(end - 1)
            if f.read(1) != b"\n":
                f.write(b"\n")  # the last write was cut short by a crash: end that line first
        f.write((json.dumps({"chain": CHAIN_ID, **entry}, ensure_ascii=False) + "\n").encode())


def saved_hashes(registry_id, days=2):
    """Item hashes in a registry's newest local logs (the last `days` files): data a bot anchored and saved.

    Only entries from this chain count. Ones from another chain, or from kits before 0.3.3 (no "chain"), are left out,
    so the bot checks those on chain.
    """
    hashes = set()
    for path in sorted((DATA_DIR / str(registry_id)).glob("*.jsonl"))[-days:]:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.split("\n"):  # not splitlines(): JSON strings can hold U+2028
            try:
                entry = json.loads(line)
                if entry.get("chain") == CHAIN_ID:
                    hashes.update(it["hash"] for it in entry.get("items") or [])
            except (ValueError, KeyError):
                continue  # a line cut short by a crash
    return hashes


def tx_link(tx_hash: str) -> str:
    h = tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash
    return f"{EXPLORER}/tx/{h}"
