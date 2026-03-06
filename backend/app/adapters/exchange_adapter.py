"""Centralized crypto exchange adapter via CCXT. Uses encrypted api_key/secret."""
import asyncio
from typing import Any

from app.adapters.base import AdapterResult, BalanceItem


async def _get_ccxt():
    """
    Import CCXT, supporting both async_support (older style) and the
    modern sync-only package. Returns (module, is_async).
    """
    try:
        import ccxt.async_support as ccxt  # type: ignore[attr-defined]
        return ccxt, True
    except Exception:
        try:
            import ccxt  # type: ignore[import]
            return ccxt, False
        except Exception:
            return None, False


async def _ensure_markets(exchange: Any, is_async: bool) -> dict[str, Any] | None:
    """
    Make sure exchange.markets is populated (load_markets) so we can map
    tickers to base/quote pairs reliably across exchanges (e.g. Bybit).
    """
    markets = getattr(exchange, "markets", None)
    if markets:
        return markets
    load_markets = getattr(exchange, "load_markets", None)
    if not load_markets:
        return None
    try:
        if is_async:
            markets = await load_markets()
        else:
            markets = await asyncio.to_thread(load_markets)
    except Exception:
        return None
    return markets


def _price_from_ticker(ticker: dict[str, Any]) -> float | None:
    """Extract last price from a CCXT ticker dict."""
    if not ticker:
        return None
    last = ticker.get("last")
    if last is not None:
        try:
            return float(last)
        except (TypeError, ValueError):
            pass
    close = ticker.get("close")
    if close is not None:
        try:
            return float(close)
        except (TypeError, ValueError):
            pass
    return None


async def _fetch_usd_prices(exchange: Any, currencies: list[str], is_async: bool) -> dict[str, float]:
    """
    Fetch USD-denominated prices for the given currencies via exchange tickers.
    Tries USDT, USD, then BUSD quote pairs. Returns dict of currency -> price.
    """
    if not currencies:
        return {}

    # Ensure markets are loaded so we can resolve base/quote properly.
    markets = await _ensure_markets(exchange, is_async)

    try:
        if is_async:
            tickers = await exchange.fetch_tickers()
        else:
            tickers = await asyncio.to_thread(exchange.fetch_tickers)
    except Exception:
        return {}
    if not tickers:
        return {}

    quote_order = ("USDT", "USD", "BUSD")
    result: dict[str, float] = {}

    for currency in currencies:
        for quote in quote_order:
            # Candidate symbols, ordered by preference.
            symbols: list[str] = []

            # Use markets metadata when available (handles Bybit-style symbols like "S/USDT:USDT").
            if isinstance(markets, dict):
                for m in markets.values():
                    base = m.get("base")
                    q = m.get("quote")
                    if base == currency and q == quote:
                        sym = m.get("symbol")
                        if isinstance(sym, str):
                            symbols.append(sym)

            # Fallback guesses for exchanges without detailed markets metadata.
            symbols.extend(
                [
                    f"{currency}/{quote}",
                    f"{currency}/{quote}:{quote}",
                    f"{currency}{quote}",
                ]
            )

            for sym in symbols:
                ticker = tickers.get(sym) if isinstance(tickers, dict) else None
                if ticker is None:
                    # As a last resort, try fetching a single ticker for that symbol.
                    try:
                        if is_async:
                            ticker = await exchange.fetch_ticker(sym)
                        else:
                            ticker = await asyncio.to_thread(exchange.fetch_ticker, sym)
                        # If that worked, optionally cache it back into tickers dict.
                        if isinstance(tickers, dict):
                            tickers[sym] = ticker
                    except Exception:
                        ticker = None

                price = _price_from_ticker(ticker) if ticker else None
                if price is not None and price > 0:
                    result[currency] = price
                    break

            if currency in result:
                break

    return result


async def fetch_exchange_balances(provider: str, credential_payload: dict) -> AdapterResult:
    """Fetch balances from a supported exchange. Credentials from encrypted payload only."""
    ccxt, is_async = await _get_ccxt()
    if ccxt is None:
        return AdapterResult(balances=[], error="Exchange support not available (ccxt import failed)")

    api_key = credential_payload.get("api_key") or credential_payload.get("apiKey")
    secret = credential_payload.get("secret") or credential_payload.get("api_secret")
    password = credential_payload.get("password") or credential_payload.get("passphrase")
    sandbox = credential_payload.get("sandbox", False)

    if not api_key or not secret:
        return AdapterResult(balances=[], error="Missing api_key or secret")

    exchange_id = provider.lower() if provider else "binance"
    if exchange_id not in ccxt.exchanges:
        return AdapterResult(balances=[], error=f"Unsupported exchange: {exchange_id}")

    config = {
        "apiKey": api_key,
        "secret": secret,
        "enableRateLimit": True,
        "options": {},
    }
    if password:
        config["password"] = password
    if sandbox:
        config["sandbox"] = True

    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class(config)
        try:
            if is_async:
                balance = await exchange.fetch_balance()
            else:
                balance = await asyncio.to_thread(exchange.fetch_balance)
            balances = []
            for currency, data in (balance.get("total") or {}).items():
                if data is None or (isinstance(data, (int, float)) and data == 0):
                    continue
                amount = float(data) if data else 0
                if amount <= 0:
                    continue
                balances.append(
                    BalanceItem(
                        asset=currency,
                        amount=amount,
                        currency=currency,
                        usd_value=None,
                    )
                )
            # Resolve USD value for all assets (including stablecoins) via exchange tickers
            need_price = [b.asset for b in balances]
            if need_price:
                prices = await _fetch_usd_prices(exchange, need_price, is_async)
                if prices:
                    new_balances = []
                    for b in balances:
                        if b.asset in prices:
                            new_balances.append(
                                BalanceItem(
                                    asset=b.asset,
                                    amount=b.amount,
                                    currency=b.currency,
                                    usd_value=round(b.amount * prices[b.asset], 2),
                                )
                            )
                        else:
                            new_balances.append(b)
                    balances = new_balances
            return AdapterResult(balances=balances)
        finally:
            # Async CCXT clients have an async close; sync ones don't.
            close = getattr(exchange, "close", None)
            if close:
                if asyncio.iscoroutinefunction(close):
                    await close()
                else:
                    await asyncio.to_thread(close)
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))


class ExchangeAdapter:
    @staticmethod
    async def fetch_balances(provider: str, credential_payload: dict) -> AdapterResult:
        return await fetch_exchange_balances(provider, credential_payload)
