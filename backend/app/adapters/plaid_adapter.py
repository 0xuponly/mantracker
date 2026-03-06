"""Plaid adapter for bank and brokerage accounts. Uses stored access_token only."""
import asyncio
from app.adapters.base import AdapterResult, BalanceItem
from app.config import get_settings


def get_plaid_host(env: str) -> str:
    hosts = {
        "sandbox": "https://sandbox.plaid.com",
        "development": "https://development.plaid.com",
        "production": "https://production.plaid.com",
    }
    return hosts.get(env, hosts["sandbox"])


def _plaid_balances_sync(access_token: str) -> AdapterResult:
    """Fetch balances from Plaid using access_token. No credentials in logs."""
    try:
        from plaid.api import plaid_api
        from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
        from plaid.model.accounts_get_request import AccountsGetRequest
        from plaid import Configuration, ApiClient
    except ImportError:
        return AdapterResult(balances=[], error="Plaid SDK not installed or Plaid not configured")

    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        return AdapterResult(balances=[], error="Plaid not configured (missing client_id or secret)")

    config = Configuration(
        host=get_plaid_host(settings.plaid_env),
        api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
    )
    client = ApiClient(config)
    api = plaid_api.PlaidApi(client)

    try:
        # Get accounts (names, types)
        req = AccountsGetRequest(access_token=access_token)
        accounts_resp = api.accounts_get(req)
        accounts = {a.account_id: a for a in accounts_resp.accounts}

        # Get balances
        balance_req = AccountsBalanceGetRequest(access_token=access_token)
        balance_resp = api.accounts_balance_get(balance_req)
        balances = []
        for acc in balance_resp.accounts:
            meta = accounts.get(acc.account_id)
            name = (meta.name if meta else "") or acc.account_id
            mask = f" ({meta.mask})" if meta and getattr(meta, "mask", None) else ""
            amount = 0.0
            if acc.balances.current is not None:
                amount = float(acc.balances.current)
            elif acc.balances.available is not None:
                amount = float(acc.balances.available)
            currency = getattr(acc.balances, "iso_currency_code", None) or "USD"
            balances.append(
                BalanceItem(
                    asset=name + mask,
                    amount=amount,
                    currency=currency,
                    usd_value=amount if currency == "USD" else None,
                    raw_name=meta.mask if meta and getattr(meta, "mask", None) else None,
                )
            )
        return AdapterResult(balances=balances)
    except Exception as e:
        return AdapterResult(balances=[], error=str(e))
    finally:
        client.close()


async def fetch_plaid_balances(access_token: str) -> AdapterResult:
    """Run sync Plaid client in thread to avoid blocking."""
    return await asyncio.to_thread(_plaid_balances_sync, access_token)


class PlaidAdapter:
    @staticmethod
    async def fetch_balances(credential_payload: dict) -> AdapterResult:
        access_token = credential_payload.get("access_token")
        if not access_token:
            return AdapterResult(balances=[], error="Missing access_token")
        return await fetch_plaid_balances(access_token)
