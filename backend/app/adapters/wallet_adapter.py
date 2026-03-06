"""Blockchain wallet adapter: Bitcoin, EVM chains, Solana. Uses address only (no private keys)."""
import asyncio
import httpx
from app.adapters.base import AdapterResult, BalanceItem
from app.config import get_settings


# Public RPC endpoints (no API key). Override via env if needed.
DEFAULT_RPC = {
    "ethereum": "https://eth.llamarpc.com",
    # Public Polygon RPC (no API key). If this ever rate-limits, consider switching to a keyed provider (Alchemy, etc.).
    "polygon": "https://rpc.ankr.com/polygon",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "base": "https://mainnet.base.org",
    "bsc": "https://bsc-dataseed.binance.org",
    "hyperevm": "https://rpc.hyperliquid.xyz/evm",
    "hypercore": "https://rpc.hyperliquid.xyz/evm",
}

# Alchemy network slugs for chains we support
ALCHEMY_NETWORK = {
    "ethereum": "eth-mainnet",
    "polygon": "polygon-mainnet",
    "arbitrum": "arb-mainnet",
    "optimism": "opt-mainnet",
    "base": "base-mainnet",
    "hyperevm": "hyperliquid",
}

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

# HYPE (Hyperliquid) price sources (primary: CoinGecko, fallback: DIA)
COINGECKO_HYPE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=hyperliquid&vs_currencies=usd"
DIA_HYPE_URL = "https://api.diadata.org/v1/assetQuotation/Hyperliquid/0x0d01dc56dcaaca66ad901c959b4011ec"

# HyperCore: mainnet exchange/L1 (not EVM). Info API for balances.
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"

_hype_price_cache: tuple[float, float] | None = None  # (price, fetched_at)
_HYPE_PRICE_TTL = 60.0  # seconds

# Alchemy Prices API + DefiLlama + CoinGecko for ERC-20 USD pricing
ALCHEMY_PRICES_NETWORK = {
    "ethereum": "eth-mainnet",
    "arbitrum": "arbitrum-mainnet",
}
DEFILLAMA_COINS_URL = "https://coins.llama.fi/prices/current"
DEFILLAMA_CHAIN_IDS = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "polygon": "polygon",
    "optimism": "optimism",
    "base": "base",
    "avalanche": "avalanche",
    "bsc": "bsc",
}
COINGECKO_TOKEN_PRICE_URL = "https://api.coingecko.com/api/v3/simple/token_price"
COINGECKO_PLATFORM_IDS = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum-one",
    "polygon": "polygon-pos",
    "optimism": "optimistic-ethereum",
    "base": "base",
}

# Known ERC-20s per chain (contract, symbol, decimals) – fetched via eth_call when Alchemy omits them
KNOWN_EVM_TOKENS: dict[str, list[tuple[str, str, int]]] = {
    "arbitrum": [
        ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", "USDC", 6),
        ("0xff970a61a04b1ca14834a43f5de4533ebddb5cc8", "USDC.e", 6),
        ("0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", "USDT", 6),
    ],
}

# Fallback metadata (contract_lower -> {symbol, name, decimals?}) for common tokens when APIs miss.
KNOWN_EVM_METADATA: dict[str, dict] = {
    # Ethereum
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
    "0xdac17f958d2ee523a2206206994597c13d831ec7": {"symbol": "USDT", "name": "Tether USD", "decimals": 6},
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"symbol": "WETH", "name": "Wrapped Ether", "decimals": 18},
    "0x6b175474e89094c44da98b954eedeac495271d0f": {"symbol": "DAI", "name": "Dai Stablecoin", "decimals": 18},
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": {"symbol": "WBTC", "name": "Wrapped BTC", "decimals": 8},
    "0x514910771af9ca656af840dff83e8264ecf986ca": {"symbol": "LINK", "name": "Chainlink", "decimals": 18},
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": {"symbol": "UNI", "name": "Uniswap", "decimals": 18},
    # Arbitrum
    "0xaf88d065e77c8cc2239327c5edb3a432268e5831": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
    "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8": {"symbol": "USDC.e", "name": "Bridged USDC", "decimals": 6},
    "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": {"symbol": "USDT", "name": "Tether USD", "decimals": 6},
    "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": {"symbol": "WETH", "name": "Wrapped Ether", "decimals": 18},
    # Base
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
    "0x4200000000000000000000000000000000000006": {"symbol": "WETH", "name": "Wrapped Ether", "decimals": 18},
    # Polygon
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": {"symbol": "USDT", "name": "Tether USD", "decimals": 6},
    "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": {"symbol": "WETH", "name": "Wrapped Ether", "decimals": 18},
    # Optimism
    "0x0b2c639c533813f4aa9d7837caf62653d097ff85": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
    "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58": {"symbol": "USDT", "name": "Tether USD", "decimals": 6},
    "0x4200000000000000000000000000000000000006": {"symbol": "WETH", "name": "Wrapped Ether", "decimals": 18},
}

# Native token CoinGecko ids for EVM chains (ETH, MATIC, etc.)
EVM_NATIVE_COINGECKO_IDS: dict[str, str] = {
    "ethereum": "ethereum",
    "arbitrum": "ethereum",
    "optimism": "ethereum",
    "base": "ethereum",
    "polygon": "matic-network",
    "avalanche": "avalanche-2",
    "bsc": "binancecoin",
}
COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
_evm_native_price_cache: dict[str, tuple[float, float]] = {}  # cg_id -> (price, fetched_at)
_EVM_NATIVE_PRICE_TTL = 60.0


async def _fetch_evm_native_usd_price(chain: str, client: httpx.AsyncClient) -> float | None:
    """USD price for chain native token (ETH, MATIC, etc.). HYPE uses existing fetcher."""
    chain_lower = chain.lower()
    if chain_lower in ("hyperevm", "hypercore"):
        return await _fetch_hype_usd_price(client)
    cg_id = EVM_NATIVE_COINGECKO_IDS.get(chain_lower)
    if not cg_id:
        return None
    now = asyncio.get_running_loop().time()
    cached = _evm_native_price_cache.get(cg_id)
    if cached and (now - cached[1]) < _EVM_NATIVE_PRICE_TTL:
        return cached[0]
    try:
        r = await client.get(f"{COINGECKO_SIMPLE_PRICE_URL}?ids={cg_id}&vs_currencies=usd", timeout=6.0)
        r.raise_for_status()
        data = r.json() or {}
        price = float((data.get(cg_id) or {}).get("usd") or 0)
        if price > 0:
            _evm_native_price_cache[cg_id] = (price, now)
            return price
    except Exception:
        pass
    return None


async def _fetch_erc20_usd_prices_alchemy(chain: str, contracts: list[str]) -> dict[str, float]:
    """
    Fetch USD prices for ERC-20 contracts: Alchemy Prices API, then DefiLlama, then CoinGecko.
    Returns mapping contract_address_lower -> price. Fallbacks run even when Alchemy key is missing.
    """
    if not contracts:
        return {}
    chain_lower = chain.lower()
    norm_contracts = sorted({(c or "").strip().lower() for c in contracts if c})
    if not norm_contracts:
        return {}
    out: dict[str, float] = {}
    try:
        async with httpx.AsyncClient() as client:
            # Primary: Alchemy Prices API (only when key and network available)
            key = (get_settings().alchemy_api_key or "").strip()
            network = ALCHEMY_PRICES_NETWORK.get(chain_lower)
            if key and network:
                try:
                    body = {"addresses": [{"network": network, "address": addr} for addr in norm_contracts]}
                    r = await client.post(
                        f"https://api.g.alchemy.com/prices/v1/{key}/tokens/by-address",
                        json=body,
                        timeout=8.0,
                    )
                    r.raise_for_status()
                    data = r.json() or {}
                    for entry in data.get("data", []):
                        try:
                            if entry.get("error"):
                                continue
                            addr = (entry.get("address") or "").lower()
                            for p in entry.get("prices") or []:
                                if p.get("currency") == "USD":
                                    v = float(p.get("value") or 0)
                                    if addr and v > 0:
                                        out[addr] = v
                                    break
                        except (TypeError, ValueError):
                            continue
                except Exception:
                    pass

            # First fallback: DefiLlama
            missing = [c for c in norm_contracts if c not in out]
            llama_chain = DEFILLAMA_CHAIN_IDS.get(chain_lower)
            if missing and llama_chain:
                try:
                    coins_param = ",".join(f"{llama_chain}:{a}" for a in missing)
                    r2 = await client.get(f"{DEFILLAMA_COINS_URL}/{coins_param}", timeout=8.0)
                    r2.raise_for_status()
                    coins = (r2.json() or {}).get("coins") or {}
                    for key_str, info in coins.items():
                        try:
                            parts = key_str.split(":", 1)
                            if len(parts) != 2:
                                continue
                            addr = parts[1].lower()
                            price = float(info.get("price") or 0)
                            if addr and price > 0:
                                out.setdefault(addr, price)
                        except (TypeError, ValueError):
                            continue
                except Exception:
                    pass

            # Second fallback: CoinGecko token price by contract
            missing2 = [c for c in norm_contracts if c not in out]
            platform = COINGECKO_PLATFORM_IDS.get(chain_lower)
            if missing2 and platform:
                try:
                    addrs = ",".join(missing2)
                    r3 = await client.get(
                        f"{COINGECKO_TOKEN_PRICE_URL}/{platform}?contract_addresses={addrs}&vs_currencies=usd",
                        timeout=8.0,
                    )
                    r3.raise_for_status()
                    data3 = r3.json() or {}
                    for addr, obj in data3.items():
                        try:
                            v = float((obj or {}).get("usd") or 0)
                            if v > 0:
                                out.setdefault(addr.lower(), v)
                        except (TypeError, ValueError):
                            continue
                except Exception:
                    pass
    except Exception:
        pass
    return out


def _evm_metadata_fallback_display(contract: str) -> str:
    """Fallback display when no symbol/name available (truncated address)."""
    c = (contract or "").strip()
    if len(c) <= 16:
        return c or "?"
    return c[:10] + "…"


_DEFILLAMA_METADATA_BATCH = 20  # avoid URL length limits and timeouts


async def _fetch_evm_token_metadata(
    chain: str, contracts: list[str]
) -> dict[str, dict]:
    """
    Fetch symbol, name, and decimals for ERC-20 contracts. Returns dict[contract_lower, {"symbol", "name", "decimals"}].
    Order: known-token map -> Alchemy getTokenMetadata (all) -> DefiLlama in batches for missing.
    """
    if not contracts:
        return {}
    chain_lower = chain.lower()
    unique = sorted({(c or "").strip().lower() for c in contracts if c})
    if not unique:
        return {}
    out: dict[str, dict] = {}

    # 1) Known-token fallback so common tokens always have a name (and decimals)
    for addr in unique:
        known = KNOWN_EVM_METADATA.get(addr)
        if known:
            out[addr] = {k: v for k, v in known.items() if v is not None}

    async with httpx.AsyncClient() as client:
        # 2) Alchemy getTokenMetadata for ALL contracts (best source for name + symbol on this chain)
        key = (get_settings().alchemy_api_key or "").strip()
        network = ALCHEMY_NETWORK.get(chain_lower)
        if key and network:
            url = f"https://{network}.g.alchemy.com/v2/{key}"
            sem = asyncio.Semaphore(8)

            async def one_meta(addr: str) -> tuple[str, dict | None]:
                async with sem:
                    try:
                        r = await client.post(
                            url,
                            json={
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "alchemy_getTokenMetadata",
                                "params": [addr],
                            },
                            timeout=8.0,
                        )
                        r.raise_for_status()
                        res = (r.json() or {}).get("result")
                        if isinstance(res, dict) and (res.get("symbol") or res.get("name")):
                            return (
                                addr,
                                {
                                    "symbol": (res.get("symbol") or "").strip() or None,
                                    "name": (res.get("name") or "").strip() or None,
                                    "decimals": res.get("decimals"),
                                },
                            )
                    except Exception:
                        pass
                return (addr, None)

            results = await asyncio.gather(*(one_meta(a) for a in unique))
            for addr, meta in results:
                if meta:
                    if addr not in out:
                        out[addr] = {}
                    if meta.get("symbol"):
                        out[addr]["symbol"] = meta["symbol"]
                    if meta.get("name"):
                        out[addr]["name"] = meta["name"]
                    if meta.get("decimals") is not None:
                        try:
                            out[addr]["decimals"] = int(meta["decimals"])
                        except (TypeError, ValueError):
                            pass

        # 3) DefiLlama in batches for contracts still missing symbol/decimals (avoids long URLs)
        llama_chain = DEFILLAMA_CHAIN_IDS.get(chain_lower)
        missing = [a for a in unique if not (out.get(a) and out[a].get("symbol"))]
        if llama_chain and missing:
            for i in range(0, len(missing), _DEFILLAMA_METADATA_BATCH):
                batch = missing[i : i + _DEFILLAMA_METADATA_BATCH]
                try:
                    coins_param = ",".join(f"{llama_chain}:{a}" for a in batch)
                    r = await client.get(f"{DEFILLAMA_COINS_URL}/{coins_param}", timeout=10.0)
                    r.raise_for_status()
                    data = r.json() or {}
                    for key, info in (data.get("coins") or {}).items():
                        if not isinstance(info, dict):
                            continue
                        parts = key.split(":", 1)
                        if len(parts) != 2:
                            continue
                        addr = parts[1].lower()
                        sym = (info.get("symbol") or "").strip()
                        dec = info.get("decimals")
                        if sym or dec is not None:
                            if addr not in out:
                                out[addr] = {}
                            if sym:
                                out[addr]["symbol"] = sym
                            if dec is not None:
                                try:
                                    out[addr]["decimals"] = int(dec)
                                except (TypeError, ValueError):
                                    pass
                except Exception:
                    pass

    for addr in list(out):
        entry = out[addr]
        if not entry.get("symbol") and entry.get("name"):
            entry["symbol"] = (entry["name"] or "")[:12] or None
    return out

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
        balances=[BalanceItem(asset="BTC", amount=btc, currency="BTC", raw_name="Bitcoin")]
    )


async def fetch_hypercore_balance(address: str) -> AdapterResult:
    """
    Fetch balances on HyperCore (Hyperliquid mainnet exchange/L1), not HyperEVM.
    Queries the main account via clearinghouseState and spotClearinghouseState (same address);
    then adds any sub-account balances from subAccounts so all activity is visible.
    """
    total_withdrawable = 0.0
    coin_totals: dict[str, float] = {}
    try:
        async with httpx.AsyncClient() as client:
            # Main account: clearinghouseState (withdrawable, margin) and spotClearinghouseState (spot balances)
            for req_type in ("clearinghouseState", "spotClearinghouseState"):
                try:
                    r = await client.post(
                        HYPERLIQUID_INFO_URL,
                        json={"type": req_type, "user": address},
                        timeout=12.0,
                    )
                    r.raise_for_status()
                    data = r.json()
                except Exception:
                    continue
                if req_type == "clearinghouseState" and isinstance(data, dict):
                    w = data.get("withdrawable")
                    if w is not None:
                        try:
                            total_withdrawable += float(w)
                        except (TypeError, ValueError):
                            pass
                elif req_type == "spotClearinghouseState":
                    # Response can be dict with "balances" or direct list of balances
                    if isinstance(data, dict):
                        bal_list = data.get("balances") or data.get("balance") or []
                    elif isinstance(data, list):
                        bal_list = data
                    else:
                        bal_list = []
                    for b in bal_list:
                        if not isinstance(b, dict):
                            continue
                        coin = (b.get("coin") or "").strip()
                        if not coin:
                            continue
                        total = b.get("total")
                        if total is None:
                            continue
                        try:
                            coin_totals[coin] = coin_totals.get(coin, 0) + float(total)
                        except (TypeError, ValueError):
                            pass

            # Sub-accounts: aggregate so we show full picture if user also uses sub-accounts
            try:
                r2 = await client.post(
                    HYPERLIQUID_INFO_URL,
                    json={"type": "subAccounts", "user": address},
                    timeout=12.0,
                )
                r2.raise_for_status()
                sub_data = r2.json()
            except Exception:
                sub_data = []
            if isinstance(sub_data, list):
                for item in sub_data:
                    if not isinstance(item, dict):
                        continue
                    ch = item.get("clearinghouseState") or {}
                    if isinstance(ch, dict):
                        w = ch.get("withdrawable")
                        if w is not None:
                            try:
                                total_withdrawable += float(w)
                            except (TypeError, ValueError):
                                pass
                    spot = item.get("spotState") or {}
                    for b in spot.get("balances") or []:
                        if not isinstance(b, dict):
                            continue
                        coin = (b.get("coin") or "").strip()
                        if not coin:
                            continue
                        total = b.get("total")
                        if total is None:
                            continue
                        try:
                            coin_totals[coin] = coin_totals.get(coin, 0) + float(total)
                        except (TypeError, ValueError):
                            pass
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))

    balances: list[BalanceItem] = []
    hype_price: float | None = None
    try:
        async with httpx.AsyncClient() as client:
            hype_price = await _fetch_hype_usd_price(client)
    except Exception:
        pass

    for coin, amount in coin_totals.items():
        if amount <= 0:
            continue
        usd_value = None
        if coin == "USDC":
            usd_value = amount
        elif coin == "HYPE" and hype_price is not None:
            usd_value = amount * hype_price
        balances.append(
            BalanceItem(
                asset=coin,
                amount=amount,
                currency=coin,
                usd_value=usd_value,
                raw_name=coin,
            )
        )

    if total_withdrawable > 0:
        balances.append(
            BalanceItem(
                asset="Account value",
                amount=total_withdrawable,
                currency="USD",
                usd_value=total_withdrawable,
                raw_name="USD",
            )
        )

    return AdapterResult(balances=balances)


async def _fetch_hype_usd_price(client: httpx.AsyncClient) -> float | None:
    """Fetch HYPE/USD price, with small in-memory cache. Primary: CoinGecko; fallback: DIA."""
    global _hype_price_cache
    now = asyncio.get_running_loop().time()
    if _hype_price_cache is not None:
        price, ts = _hype_price_cache
        if now - ts < _HYPE_PRICE_TTL:
            return price

    # Primary: CoinGecko
    try:
        r = await client.get(COINGECKO_HYPE_URL, timeout=6.0)
        r.raise_for_status()
        data = r.json()
        price = float((data.get("hyperliquid") or {}).get("usd") or 0)
        if price > 0:
            _hype_price_cache = (price, now)
            return price
    except Exception:
        pass

    # Fallback: DIA
    try:
        r = await client.get(DIA_HYPE_URL, timeout=6.0)
        r.raise_for_status()
        data = r.json()
        # DIA typically returns {"Price": 30.0, ...}
        price = float(data.get("Price") or 0)
        if price > 0:
            _hype_price_cache = (price, now)
            return price
    except Exception:
        pass

    return None


def _erc20_balance_of_calldata(owner: str) -> str:
    """ERC-20 balanceOf(address) calldata: selector + padded address."""
    owner = (owner or "").strip().lower()
    if not owner.startswith("0x"):
        owner = "0x" + owner
    return "0x70a08231" + owner[2:].zfill(64)


async def _fetch_evm_known_token_balances(
    chain: str, address: str, rpc_url: str | None
) -> list[tuple[str, BalanceItem]]:
    """Fetch balances for known tokens (e.g. USDC on Arbitrum) via eth_call. Returns (contract_lower, BalanceItem)."""
    chain_lower = chain.lower()
    tokens = KNOWN_EVM_TOKENS.get(chain_lower)
    if not tokens:
        return []
    url = rpc_url or DEFAULT_RPC.get(chain_lower, DEFAULT_RPC["ethereum"])
    data_hex = _erc20_balance_of_calldata(address)
    out: list[tuple[str, BalanceItem]] = []
    try:
        async with httpx.AsyncClient() as client:
            for contract, symbol, decimals in tokens:
                try:
                    r = await client.post(
                        url,
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "eth_call",
                            "params": [{"to": contract, "data": data_hex}, "latest"],
                        },
                        timeout=10.0,
                    )
                    r.raise_for_status()
                    j = r.json()
                    if j.get("error"):
                        continue
                    raw = (j.get("result") or "0x0").strip()
                    if not raw or raw == "0x":
                        continue
                    value = int(raw, 16)
                    if value <= 0:
                        continue
                    amount = value / (10**decimals)
                    if amount <= 0:
                        continue
                    out.append(
                        (
                            contract.lower(),
                            BalanceItem(
                                asset=symbol,
                                amount=amount,
                                currency=symbol,
                                usd_value=None,
                                raw_name=symbol,
                            ),
                        )
                    )
                except Exception:
                    continue
    except Exception:
        pass
    return out


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


async def fetch_evm_balances_alchemy(chain: str, address: str) -> AdapterResult:
    """Fetch ERC-20 token balances via Alchemy's Token API, and enrich with USD prices via Alchemy Prices API when available."""
    settings = get_settings()
    key = (settings.alchemy_api_key or "").strip()
    if not key:
        return AdapterResult(balances=[], error="Alchemy API key not set")
    network = ALCHEMY_NETWORK.get(chain.lower())
    if not network:
        return AdapterResult(balances=[], error=f"Alchemy does not support chain: {chain}")
    url = f"https://{network}.g.alchemy.com/v2/{key}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "alchemy_getTokenBalances",
        "params": [address, "erc20"],
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, timeout=20.0)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))

    result = data.get("result") or {}
    tokens = result.get("tokenBalances") or []

    # Collect non-zero balances: (contract_lower, raw_balance_int) so we can apply decimals from metadata.
    items: list[tuple[str, int]] = []
    for t in tokens:
        try:
            raw = t.get("tokenBalance")
            if not raw:
                continue
            if isinstance(raw, str) and raw.startswith("0x"):
                value = int(raw, 16)
            else:
                value = int(raw)
            if value <= 0:
                continue
            contract = (t.get("contractAddress") or "").lower()
            if not contract:
                continue
            items.append((contract, value))
        except (ValueError, TypeError):
            continue

    if not items:
        return AdapterResult(balances=[])

    contracts_list = [c for (c, _) in items]
    metadata = await _fetch_evm_token_metadata(chain, contracts_list)
    prices = await _fetch_erc20_usd_prices_alchemy(chain, contracts_list)

    balances: list[BalanceItem] = []
    for contract, raw_value in items:
        meta = metadata.get(contract) or {}
        decimals = meta.get("decimals")
        if decimals is None:
            decimals = 18
        amount = raw_value / (10**decimals)
        if amount <= 0:
            continue
        symbol = (meta.get("symbol") or "").strip() or _evm_metadata_fallback_display(contract)
        raw_name = (meta.get("name") or "").strip() or None
        usd_price = prices.get(contract)
        usd_value = amount * usd_price if usd_price is not None else None
        balances.append(
            BalanceItem(
                asset=symbol,
                amount=amount,
                currency=symbol,
                usd_value=usd_value,
                raw_name=raw_name,
            )
        )
    return AdapterResult(balances=balances)


async def _fetch_evm_native_balance(chain: str, address: str, rpc_url: str | None) -> BalanceItem | None:
    """Fetch native token balance (ETH, HYPE, etc.) and its USD value when possible."""
    chain_lower = chain.lower()
    url = rpc_url or DEFAULT_RPC.get(chain_lower, DEFAULT_RPC["ethereum"])
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                json={"jsonrpc": "2.0", "method": "eth_getBalance", "params": [address, "latest"], "id": 1},
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    try:
        wei = int(data.get("result", "0x0"), 16)
    except (ValueError, TypeError):
        return None
    amount = wei / 10**18
    symbol = _evm_native_symbol(chain)
    usd_value = None
    if amount > 0:
        try:
            async with httpx.AsyncClient() as client:
                price = await _fetch_evm_native_usd_price(chain, client)
            if price is not None:
                usd_value = amount * price
        except Exception:
            pass
    return BalanceItem(
        asset=symbol,
        amount=amount,
        currency=symbol,
        usd_value=usd_value,
        raw_name=symbol,
    )


async def fetch_evm_balance(chain: str, address: str, rpc_url: str | None = None) -> AdapterResult:
    """Fetch native + ERC-20 balances. Alchemy for tokens when key set; always include native with USD price."""
    chain_lower = chain.lower()
    native = await _fetch_evm_native_balance(chain, address, rpc_url)

    combined: list[BalanceItem] = []
    if native is not None:
        combined.append(native)

    if (get_settings().alchemy_api_key or "").strip() and chain_lower in ALCHEMY_NETWORK:
        result = await fetch_evm_balances_alchemy(chain, address)
        combined.extend(result.balances)

    # Merge in known tokens (e.g. USDC on Arbitrum) so they always show when Alchemy omits or misreports them
    existing_assets = {b.asset.upper() for b in combined}
    if chain_lower in KNOWN_EVM_TOKENS:
        known_list = await _fetch_evm_known_token_balances(chain, address, rpc_url)
        if known_list:
            contracts = [c for c, _ in known_list]
            prices = await _fetch_erc20_usd_prices_alchemy(chain, contracts)
            for contract, b in known_list:
                if b.asset.upper() in existing_assets:
                    continue
                existing_assets.add(b.asset.upper())
                p = prices.get(contract)
                usd_value = (b.amount * p) if p else None
                combined.append(
                    BalanceItem(
                        asset=b.asset,
                        amount=b.amount,
                        currency=b.currency,
                        usd_value=usd_value,
                        raw_name=b.raw_name,
                    )
                )

    if combined:
        return AdapterResult(balances=combined)
    if native is not None:
        return AdapterResult(balances=[native])
    return AdapterResult(balances=[], error="Failed to fetch balance")


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

    # Also include HyperCore balances for all EVM addresses (Hyperliquid mainnet / exchange)
    try:
        hypercore_result = await fetch_hypercore_balance(address)
        if hypercore_result.balances:
            for b in hypercore_result.balances:
                merged.append(
                    BalanceItem(
                        asset=b.asset,
                        amount=b.amount,
                        currency=b.currency,
                        usd_value=b.usd_value,
                        raw_name=b.raw_name,
                        chain=CHAIN_DISPLAY_NAMES.get("hypercore", "HyperCore"),
                    )
                )
        if hypercore_result.error and not hypercore_result.balances:
            errors.append(f"{CHAIN_DISPLAY_NAMES.get('hypercore', 'HyperCore')}: {hypercore_result.error}")
    except Exception as e:
        errors.append(f"{CHAIN_DISPLAY_NAMES.get('hypercore', 'HyperCore')}: {e!s}")
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

            # SPL tokens: only include if we have BOTH a real name (from token list) AND a non-zero price
            for mint, amount, _ in spl_items:
                meta = token_list.get(mint)
                has_name = False
                if meta is not None:
                    symbol_str = (meta.get("symbol") or "").strip()
                    name_str = (meta.get("name") or "").strip()
                    # Treat "?" or empty as "no name"
                    if symbol_str not in ("", "?") or name_str not in ("", "?"):
                        has_name = True
                price = prices.get(mint)
                has_price = price is not None and price > 0
                # Skip tokens that don't have BOTH a usable name and a positive price.
                if not (has_name and has_price):
                    continue
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
    # HyperCore: mainnet exchange (L1), not HyperEVM – use info API
    if provider_lower == "hypercore":
        return await fetch_hypercore_balance(address)
    # EVM: one chain or all chains (HyperEVM is one of these)
    if provider_lower in ("evm", "evm-all", "evm_all"):
        return await fetch_evm_all_chains(address)
    chain = provider_lower or "ethereum"
    rpc_url = credential_payload.get("rpc_url")
    return await fetch_evm_balance(chain, address, rpc_url)


class WalletAdapter:
    @staticmethod
    async def fetch_balances(provider: str, credential_payload: dict) -> AdapterResult:
        return await fetch_wallet_balances(provider, credential_payload)
