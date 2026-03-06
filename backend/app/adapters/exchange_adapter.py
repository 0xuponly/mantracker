"""Centralized crypto exchange adapter via CCXT. Uses encrypted api_key/secret."""
import asyncio
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
                usd = None
                if currency in ("USDT", "USDC", "BUSD"):
                    usd = amount
                elif "USD" in currency:
                    usd = amount
                balances.append(
                    BalanceItem(
                        asset=currency,
                        amount=amount,
                        currency=currency,
                        usd_value=usd,
                    )
                )
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
