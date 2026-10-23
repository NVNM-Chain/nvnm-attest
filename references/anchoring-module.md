# Anchoring module: reference

Source: NVNM-Chain/nvnmchain-docs, `content/docs/modules/anchoring-module.mdx` and `resources/network-details.mdx` (checked 13 Oct 2026).

## Network (Testnet 1)

| | |
|---|---|
| Network name | `nvnm-next-testnet-1` |
| EVM chain ID | `787223` |
| RPC / WS | `https://rpc.nvnm.testnet.nvnmchain.io` / `wss://rpc.nvnm.testnet.nvnmchain.io` |
| Explorer (anchoring view) | `https://explorer.nvnm.testnet.nvnmchain.io` |
| Faucet | `https://faucet.nvnm.testnet.nvnmchain.io` (web form) |
| Faucet API | `POST /api/faucet`, body `{"address": "0x..."}` → `{txHash, amount}` (100 nUSD). Limits: 1 request per address per 24h, 1 per IP per hour. Errors: 400 bad address (bech32 `nvnm1...` is rejected), 429 limit with `Retry-After`, 500 faucet misconfigured or tx failed, 503 faucet empty or transfer pending. Source: `NVNM-Chain/nvnm-layer1-sovereign-faucet` README (checked 14 Oct 2026) |
| Faucet health | `curl -s https://faucet.nvnm.testnet.nvnmchain.io/api/faucet/balance` → `{balance, balanceRaw, healthy}` |

## Fees

- There's no native gas token. Fees are paid in the TIP-20 stablecoin **nUSD** at `0x20C0000000000000000000000000000000000000` (6 decimals). Contract calls fall back to nUSD automatically.
- Gas price is in attodollars (10^-18 USD) per gas. Fee in USD = `gas_used * gas_price / 1e18`.
- `eth_getBalance` returns a fixed huge placeholder. **Ignore it.** Read the nUSD `balanceOf` instead.

## Contract

Address `0x0000000000000000000000000000000000000A00`. It's a normal Solidity contract installed at genesis, not a precompile.

| Function | Who can call |
|---|---|
| `addRegistry(string name, string description, string metadata)` | Any wallet (EOA); caller becomes admin |
| `addRecord(Record record)` | Registry `admin` or `editor` |
| `updateRecordStatus(uint64 registryId, uint64 recordId, uint64 index, string status)` | `admin` or `editor` |
| `grantRole(uint64 registryId, string checksum, address account, string role)` | Registry `admin` (empty checksum = registry-wide) |
| `revokeRole(...)` | Registry `admin` |
| `records(uint64 registryId, string checksum, uint64 recordId, uint64 index, PageRequest)` | Anyone (read) |
| `registries(uint64 registryId, PageRequest)` | Anyone (read); `0` lists all |
| `registriesByName(string name, uint8 matchMode, PageRequest)` | Anyone (read), exact match only |

### Record
```solidity
struct Record {
    string uri;           // link to off-chain data; REQUIRED, max 2048 bytes (the kit defaults to urn:sha256:<checksum>)
    string checksum;      // hash of the data
    string checksumAlgo;  // e.g. "sha256"
    string metadata;      // JSON string; "" and "{}" are rejected
    string timestamp;     // set by chain
    string status;        // user-defined, e.g. "active"
    uint64 recordId;      // set by chain (pass 0)
    uint64 index;         // version, set by chain
    bool   isLatest;      // set by chain
    uint64 registryId;
}
```
Anchoring the same checksum again in the same registry creates a new version (`index`) under the same `recordId`.

PageRequest = `(bytes key, uint64 offset, uint64 limit, bool countTotal, bool reverse)`. Default limit 50, max 200.

### Events
- `AddRegistry(address indexed caller, uint64 registryId, string name)`, topic0 `0x181791bc379acedd3615cf065d3c275dfa6a3c4614c9065d54c98773f576108d`
- `AddRecord(address indexed caller, uint64 registryId, uint64 recordId, uint64 index, string checksum)`, topic0 `0x1a3295fa8cc0e28c95d21912c9e6958f3bc740231781f7640ad885c972a352fd`

### Gotchas
- All write calls must come from an EOA. Contracts calling on a user's behalf revert with `sender not an eoa`.
- `records()` reverts with `record does not exist` when nothing matches. `verify.py` treats that as "not found".
- The `creator` field of a registry is a bech32 `nvnm1...` address, even though the caller is an EVM address.
