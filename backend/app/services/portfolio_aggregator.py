"""Aggregate balances across all account adapters. Credentials decrypted only in memory."""
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSession
from app.models import Account, AccountType
from app.services.credential_store import decrypt_credential_payload
from app.adapters import ExchangeAdapter, WalletAdapter
from app.adapters.base import AdapterResult, BalanceItem

# Per-account timeout so one stuck adapter doesn't block the whole portfolio
FETCH_ACCOUNT_TIMEOUT = 45.0


async def fetch_account_balances(db: AsyncSession, account: Account) -> AdapterResult:
    """Fetch balances for one account. Decrypts credential only here, never stored in result."""
    cred = account.credential
    if not cred:
        return AdapterResult(balances=[], error="No credentials stored")
    payload = decrypt_credential_payload(cred.encrypted_payload)
    if not payload:
        return AdapterResult(balances=[], error="Invalid credentials")

    if account.type == AccountType.BANK or account.type == AccountType.BROKERAGE:
        return AdapterResult(balances=[], error="Bank/brokerage integration has been removed")
    if account.type == AccountType.EXCHANGE:
        return await ExchangeAdapter.fetch_balances(account.provider or "binance", payload)
    if account.type == AccountType.WALLET:
        return await WalletAdapter.fetch_balances(account.provider or "ethereum", payload)
    return AdapterResult(balances=[], error=f"Unknown account type: {account.type}")


async def aggregate_portfolio(db: AsyncSession, profile_id: int) -> list[dict]:
    """Return list of account summaries with balances. No raw credentials in output."""
    q = (
        select(Account)
        .where(Account.profile_id == profile_id, Account.is_active == True)
        .options(selectinload(Account.credential))
    )
    result = await db.execute(q)
    accounts = result.scalars().all()
    out = []
    for acc in accounts:
        try:
            balances_result = await asyncio.wait_for(
                fetch_account_balances(db, acc),
                timeout=FETCH_ACCOUNT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            balances_result = AdapterResult(balances=[], error="Request timed out")
        balances_dict = [
            {
                "asset": b.asset,
                "amount": b.amount,
                "currency": b.currency,
                "usd_value": b.usd_value,
                **({"chain": b.chain} if b.chain is not None else {}),
                **({"name": b.raw_name} if b.raw_name is not None else {}),
            }
            for b in balances_result.balances
        ]
        out.append({
            "id": acc.id,
            "name": acc.name,
            "type": acc.type.value,
            "provider": acc.provider,
            "balances": balances_dict,
            "error": balances_result.error,
        })
    return out
