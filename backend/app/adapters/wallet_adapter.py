"""Blockchain wallet adapter: Bitcoin, EVM chains, Solana. Uses address only (no private keys)."""
import asyncio
import httpx
from app.adapters.base import AdapterResult, BalanceItem
from app.config import get_settings


# Public RPC endpoints (no API key). Override via env if needed.
DEFAULT_RPC = {
    "ethereum": "https://eth.llamarpc.com",
    "polygon": "https://polygon.llamarpc.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "base": "https://mainnet.base.org",
    "bsc": "https://bsc-dataseed.binance.org",
    "hyperevm": "https://rpc.hyperliquid.xyz/evm",
    "hypercore": "https://rpc.hyperliquid.xyz/evm",
}

# Covalent chain names for balances_v2 API (all tokens). HyperEVM/HyperCore use same chain.
COVALENT_CHAIN = {
    "ethereum": "eth-mainnet",
    "polygon": "matic-mainnet",
    "arbitrum": "arbitrum-mainnet",
    "optimism": "optimism-mainnet",
    "base": "base-mainnet",
    "avalanche": "avalanche-mainnet",
    "bsc": "bsc-mainnet",
    "hyperevm": "hyperevm-mainnet",
    "hypercore": "hyperevm-mainnet",
}

# Chains that require Covalent for token balances (no native-only fallback)
COVALENT_REQUIRED_CHAINS = frozenset({"hyperevm", "hypercore"})

# All EVM chains to query when user adds "EVM (all chains)" (hypercore same as hyperevm, skip duplicate)
EVM_CHAINS = [
    "ethereum",
    "polygon",
    "arbitrum",
    "optimism",
    "base",
    "avalanche",
    "bsc",
    "hyperevm",
]

# Display names for balance list
CHAIN_DISPLAY_NAMES = {
    "ethereum": "Ethereum",
    "polygon": "Polygon",
    "arbitrum": "Arbitrum",
    "optimism": "Optimism",
    "base": "Base",
    "avalanche": "Avalanche",
    "bsc": "BSC",
    "hyperevm": "HyperEVM",
    "hypercore": "HyperCore",
}

SOLANA_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SOLANA_RPC_DEFAULT = "https://api.mainnet-beta.solana.com"
SOLANA_SOL_MINT = "So11111111111111111111111111111111111111112"

# Rate-limit Solana public RPC: one request at a time, delay between calls, retry on 429.
# Keep the lock scope tight (only around the HTTP request + short pacing) so 429 backoffs
# don't block unrelated calls and cause cascading timeouts.
_solana_rpc_lock = asyncio.Lock()
_solana_next_allowed_at = 0.0  # event loop time (seconds)
# Public RPC endpoints can be aggressively rate-limited. A slightly larger delay
# dramatically reduces 429s and avoids cascading timeouts when multiple wallets refresh.
_SOLANA_RPC_DELAY = 1.0  # seconds between RPC calls
_SOLANA_429_RETRIES = 2
_SOLANA_429_BACKOFF = (2.0, 5.0)  # seconds before retry 1 and 2


def _get_solana_rpc_url() -> str:
    url = (get_settings().solana_rpc_url or "").strip()
    return url or SOLANA_RPC_DEFAULT


async def _solana_rpc_post(
    client: httpx.AsyncClient,
    payload: dict,
    timeout: float = 15.0,
) -> dict:
    """POST to Solana RPC with retry on 429."""
    url = _get_solana_rpc_url()
    last_err: Exception | None = None
    for attempt in range(_SOLANA_429_RETRIES + 1):
        try:
            # Rate-limit all Solana RPC calls globally across requests.
            global _solana_next_allowed_at
            loop = asyncio.get_running_loop()
            async with _solana_rpc_lock:
                now = loop.time()
                if _solana_next_allowed_at > now:
                    await asyncio.sleep(_solana_next_allowed_at - now)
                r = await client.post(url, json=payload, timeout=timeout)
                _solana_next_allowed_at = loop.time() + _SOLANA_RPC_DELAY
            if r.status_code == 429:
                last_err = httpx.HTTPStatusError(
                    "429 Too Many Requests",
                    request=r.request,
                    response=r,
                )
                if attempt < _SOLANA_429_RETRIES:
                    backoff = _SOLANA_429_BACKOFF[attempt]
                    await asyncio.sleep(backoff)
                    continue
                raise last_err
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code == 429 and attempt < _SOLANA_429_RETRIES:
                backoff = _SOLANA_429_BACKOFF[attempt]
                await asyncio.sleep(backoff)
                continue
            raise
    assert last_err is not None
    raise last_err
SOLANA_TOKEN_LIST_URL = "https://raw.githubusercontent.com/solana-labs/token-list/main/src/tokens/solana.tokenlist.json"
JUPITER_LITE_PRICE_URL = "https://lite-api.jup.ag/price/v3"

# In-memory cache for Solana token list (mint -> {symbol, name})
_solana_token_list_cache: dict[str, dict[str, str]] | None = None


async def fetch_btc_balance(address: str) -> AdapterResult:
    """Fetch Bitcoin balance via mempool.space (no API key)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://mempool.space/api/address/{address}",
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))

    chain = data.get("chain_stats", {})
    funded = chain.get("funded_txo_sum", 0)
    spent = chain.get("spent_txo_sum", 0)
    satoshi = funded - spent
    btc = satoshi / 100_000_000.0
    return AdapterResult(
        balances=[BalanceItem(asset="BTC", amount=btc, currency="BTC", raw_name=address[:16] + "...")]
    )


def _evm_native_symbol(chain: str) -> str:
    c = chain.lower()
    if c in ("ethereum", "arbitrum", "optimism", "base"):
        return "ETH"
    if c == "polygon":
        return "MATIC"
    if c == "avalanche":
        return "AVAX"
    if c == "bsc":
        return "BNB"
    if c in ("hyperevm", "hypercore"):
        return "HYPE"
    return "ETH"


async def fetch_evm_balances_covalent(chain: str, address: str) -> AdapterResult:
    """Fetch all token balances (native + ERC-20) via Covalent. Requires COVALENT_API_KEY."""
    key = get_settings().covalent_api_key
    if not key or not key.strip():
        return AdapterResult(balances=[], error="Covalent API key not set")
    chain_name = COVALENT_CHAIN.get(chain.lower()) or COVALENT_CHAIN["ethereum"]
    url = f"https://api.covalenthq.com/v1/{chain_name}/address/{address}/balances_v2/"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, params={"key": key}, timeout=20.0)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))

    items = data.get("data", {}).get("items") or []
    balances = []
    for item in items:
        try:
            balance = item.get("balance") or "0"
            decimals = item.get("contract_decimals") or 18
            amount = int(balance) / (10**decimals)
            if amount <= 0:
                continue
            symbol = (item.get("contract_ticker_symbol") or item.get("contract_name") or "?")[:20]
            quote = (item.get("quote") or 0) or 0
            balances.append(
                BalanceItem(
                    asset=symbol,
                    amount=amount,
                    currency=symbol,
                    usd_value=float(quote) if quote else None,
                    raw_name=address[:16] + "...",
                )
            )
        except (ValueError, TypeError):
            continue
    return AdapterResult(balances=balances)


async def fetch_evm_balance(chain: str, address: str, rpc_url: str | None = None) -> AdapterResult:
    """Fetch all token balances via Covalent when key set; else native-only for most chains. HyperEVM/HyperCore require Covalent (all tokens only)."""
    chain_lower = chain.lower()
    key = get_settings().covalent_api_key

    if chain_lower in COVALENT_REQUIRED_CHAINS:
        if not key or not key.strip():
            return AdapterResult(
                balances=[],
                error="HyperEVM/HyperCore require COVALENT_API_KEY in backend .env for full token balances. Get a free key at covalenthq.com",
            )
        result = await fetch_evm_balances_covalent(chain, address)
        return result

    if key and key.strip():
        result = await fetch_evm_balances_covalent(chain, address)
        if result.balances:
            return result

    # Native-only fallback for chains that are not Covalent-required
    url = rpc_url or DEFAULT_RPC.get(chain_lower, DEFAULT_RPC["ethereum"])
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getBalance",
        "params": [address, "latest"],
        "id": 1,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, timeout=15.0)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))

    hex_balance = data.get("result", "0x0")
    wei = int(hex_balance, 16)
    amount = wei / 10**18
    symbol = _evm_native_symbol(chain)
    return AdapterResult(
        balances=[
            BalanceItem(
                asset=symbol,
                amount=amount,
                currency=symbol,
                raw_name=address[:16] + "...",
            )
        ]
    )


async def fetch_evm_all_chains(address: str) -> AdapterResult:
    """Fetch token balances for one EVM address across all supported EVM chains. One address, all chains."""
    async def fetch_one(chain: str) -> AdapterResult:
        result = await fetch_evm_balance(chain, address, rpc_url=None)
        return result

    results = await asyncio.gather(
        *[fetch_one(chain) for chain in EVM_CHAINS],
        return_exceptions=True,
    )
    merged: list[BalanceItem] = []
    errors: list[str] = []
    for i, chain in enumerate(EVM_CHAINS):
        if i >= len(results):
            continue
        r = results[i]
        if isinstance(r, Exception):
            errors.append(f"{CHAIN_DISPLAY_NAMES.get(chain, chain)}: {r!s}")
            continue
        if not isinstance(r, AdapterResult):
            continue
        if r.error and not r.balances:
            errors.append(f"{CHAIN_DISPLAY_NAMES.get(chain, chain)}: {r.error}")
            continue
        chain_label = CHAIN_DISPLAY_NAMES.get(chain, chain)
        for b in r.balances:
            merged.append(
                BalanceItem(
                    asset=b.asset,
                    amount=b.amount,
                    currency=b.currency,
                    usd_value=b.usd_value,
                    raw_name=b.raw_name,
                    chain=chain_label,
                )
            )
    return AdapterResult(
        balances=merged,
        error="; ".join(errors) if errors else None,
    )


async def _fetch_solana_token_list(client: httpx.AsyncClient) -> dict[str, dict[str, str]]:
    """Return mint -> {symbol, name}. Uses in-memory cache."""
    global _solana_token_list_cache
    if _solana_token_list_cache is not None:
        return _solana_token_list_cache
    try:
        # This file is large and can be slow to download; keep it best-effort so we don't
        # time out individual account balance fetches.
        r = await client.get(SOLANA_TOKEN_LIST_URL, timeout=8.0)
        r.raise_for_status()
        data = r.json()
    except Exception:
        _solana_token_list_cache = {}
        return _solana_token_list_cache
    out: dict[str, dict[str, str]] = {}
    for t in data.get("tokens", []):
        addr = t.get("address")
        if addr:
            out[addr] = {"symbol": t.get("symbol") or "?", "name": t.get("name") or "?"}
    _solana_token_list_cache = out
    return out


async def _fetch_solana_prices(client: httpx.AsyncClient, mints: list[str]) -> dict[str, float]:
    """Fetch USD prices for given mints from Jupiter Lite. Returns mint -> usd_price."""
    if not mints:
        return {}
    out: dict[str, float] = {}
    # Keep requests small enough for URL length, but large enough to avoid many round-trips.
    batch_size = 75
    for i in range(0, len(mints), batch_size):
        batch = mints[i : i + batch_size]
        ids = ",".join(batch)
        try:
            # Best-effort: prices are optional. Fail fast so balances still return.
            r = await client.get(f"{JUPITER_LITE_PRICE_URL}?ids={ids}", timeout=6.0)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue
        for mint, info in (data or {}).items():
            if isinstance(info, dict) and "usdPrice" in info:
                try:
                    out[mint] = float(info["usdPrice"])
                except (TypeError, ValueError):
                    pass
    return out


async def fetch_solana_balance(address: str) -> AdapterResult:
    """Fetch SOL + all SPL tokens by name with USD values (token list + Jupiter Lite prices)."""
    balances: list[BalanceItem] = []
    try:
        async with httpx.AsyncClient() as client:
            # Native SOL balance
            data = await _solana_rpc_post(
                client,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [address],
                },
            )
            lamports = data.get("result", {}).get("value", 0)
            sol_amount = lamports / 1_000_000_000.0

            # SPL token accounts (best effort: return SOL even if this fails)
            spl_items: list[tuple[str, float, int]] = []  # (mint, amount, decimals)
            spl_error: str | None = None
            try:
                data2 = await _solana_rpc_post(
                    client,
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "getTokenAccountsByOwner",
                        "params": [
                            address,
                            {"programId": SOLANA_TOKEN_PROGRAM_ID},
                            {"encoding": "jsonParsed"},
                        ],
                    },
                )
            except Exception as e:
                data2 = {"result": {"value": []}}
                spl_error = str(e)
            for item in data2.get("result", {}).get("value", []):
                try:
                    parsed = (item.get("account") or {}).get("data") or {}
                    if not isinstance(parsed, dict):
                        continue
                    info = parsed.get("parsed", {}).get("info", {})
                    token_amount = info.get("tokenAmount", {})
                    raw_amount = token_amount.get("amount") or "0"
                    decimals = token_amount.get("decimals", 0)
                    ui_amount_str = token_amount.get("uiAmountString")
                    if ui_amount_str is not None:
                        amount = float(ui_amount_str)
                    else:
                        amount = int(raw_amount) / (10**decimals) if decimals else int(raw_amount)
                    if amount <= 0:
                        continue
                    mint = info.get("mint")
                    if mint:
                        spl_items.append((mint, amount, decimals))
                except (ValueError, TypeError, KeyError):
                    continue

            # Resolve names and prices
            all_mints = [SOLANA_SOL_MINT] + [m for m, _, _ in spl_items]
            token_list = await _fetch_solana_token_list(client)
            # Prices are optional; also cap how many mints we price to avoid long loops for very token-heavy wallets.
            mints_for_prices = all_mints[:120]
            prices = await _fetch_solana_prices(client, mints_for_prices)

            # SOL
            meta = token_list.get(SOLANA_SOL_MINT) or {"symbol": "SOL", "name": "Wrapped SOL"}
            price = prices.get(SOLANA_SOL_MINT)
            balances.append(
                BalanceItem(
                    asset=meta["symbol"],
                    amount=sol_amount,
                    currency=meta["symbol"],
                    usd_value=sol_amount * price if price is not None else None,
                    raw_name=meta.get("name"),
                )
            )

            # SPL tokens (by name/symbol, with USD)
            for mint, amount, _ in spl_items:
                meta = token_list.get(mint) or {"symbol": mint[:8] + "…", "name": mint[:16] + "…"}
                price = prices.get(mint)
                usd = amount * price if price is not None else None
                balances.append(
                    BalanceItem(
                        asset=meta["symbol"],
                        amount=amount,
                        currency=meta["symbol"],
                        usd_value=usd,
                        raw_name=meta.get("name"),
                    )
                )
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))
    # If SPL token fetch failed but SOL worked, return partial balances with a helpful error.
    if "spl_error" in locals() and spl_error:
        return AdapterResult(balances=balances, error=f"SPL tokens unavailable: {spl_error}")
    return AdapterResult(balances=balances)


async def fetch_wallet_balances(provider: str, credential_payload: dict) -> AdapterResult:
    """Dispatch to Bitcoin, EVM (single or all chains), or Solana by provider."""
    address = (credential_payload.get("address") or "").strip()
    if not address:
        return AdapterResult(balances=[], error="Missing wallet address")

    provider_lower = (provider or "").lower()
    if provider_lower == "bitcoin" or provider_lower == "btc":
        return await fetch_btc_balance(address)
    if provider_lower == "solana" or provider_lower == "sol":
        return await fetch_solana_balance(address)
    # EVM: one chain or all chains
    if provider_lower in ("evm", "evm-all", "evm_all"):
        return await fetch_evm_all_chains(address)
    chain = provider_lower or "ethereum"
    rpc_url = credential_payload.get("rpc_url")
    return await fetch_evm_balance(chain, address, rpc_url)


class WalletAdapter:
    @staticmethod
    async def fetch_balances(provider: str, credential_payload: dict) -> AdapterResult:
        return await fetch_wallet_balances(provider, credential_payload)
