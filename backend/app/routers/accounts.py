"""CRUD for accounts. Credentials stored encrypted; never returned in API."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSession, get_db
from app.models import Account, AccountType, AccountCredential
from app.security import get_current_profile
from app.services.credential_store import encrypt_credential_payload
from app.models import Profile
from app.services.portfolio_aggregator import fetch_account_balances, FETCH_ACCOUNT_TIMEOUT
from app.adapters.base import AdapterResult

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    name: str
    type: str  # bank | brokerage | exchange | wallet
    provider: str | None = None
    # Credentials: shape depends on type. Never logged.
    credentials: dict  # e.g. {"api_key":"","secret":""} or {"address":"0x..."}


class AccountResponse(BaseModel):
    id: int
    name: str
    type: str
    provider: str | None
    is_active: bool

    class Config:
        from_attributes = True


class BalanceItemResponse(BaseModel):
    asset: str
    amount: float
    currency: str | None
    usd_value: float | None = None
    chain: str | None = None
    name: str | None = None


class AccountBalancesResponse(BaseModel):
    id: int
    balances: list[BalanceItemResponse]
    error: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = None


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    q = select(Account).where(Account.profile_id == profile.id).order_by(Account.created_at.desc())
    r = await db.execute(q)
    accounts = r.scalars().all()
    return [AccountResponse(
        id=a.id,
        name=a.name,
        type=a.type.value,
        provider=a.provider,
        is_active=a.is_active,
    ) for a in accounts]


@router.get("/{account_id}/balances", response_model=AccountBalancesResponse)
async def get_account_balances(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    """
    Fetch balances for a single account. This is used by the UI to render account cards first,
    then populate balances incrementally with retries on failures.
    """
    q = (
        select(Account)
        .where(Account.id == account_id, Account.profile_id == profile.id, Account.is_active == True)
        .options(selectinload(Account.credential))
    )
    r = await db.execute(q)
    account = r.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        result = await asyncio.wait_for(fetch_account_balances(db, account), timeout=FETCH_ACCOUNT_TIMEOUT)
    except asyncio.TimeoutError:
        result = AdapterResult(balances=[], error="Request timed out")

    balances = [
        BalanceItemResponse(
            asset=b.asset,
            amount=b.amount,
            currency=b.currency,
            usd_value=b.usd_value,
            chain=b.chain,
            name=b.raw_name,
        )
        for b in (result.balances or [])
    ]
    return AccountBalancesResponse(id=account.id, balances=balances, error=result.error)


@router.post("", response_model=AccountResponse)
async def create_account(
    body: AccountCreate,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    try:
        atype = AccountType(body.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid type: {body.type}")
    provider = (body.provider or "").strip() or None
    if atype == AccountType.BANK or atype == AccountType.BROKERAGE:
        raise HTTPException(
            status_code=400,
            detail="Use /plaid/exchange to link bank or brokerage accounts",
        )
    account = Account(
        profile_id=profile.id,
        name=body.name,
        type=atype,
        provider=provider,
    )
    db.add(account)
    await db.flush()
    cred = AccountCredential(
        account_id=account.id,
        encrypted_payload=encrypt_credential_payload(body.credentials),
    )
    db.add(cred)
    await db.flush()
    return AccountResponse(
        id=account.id,
        name=account.name,
        type=account.type.value,
        provider=account.provider,
        is_active=account.is_active,
    )


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    body: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    q = select(Account).where(Account.id == account_id, Account.profile_id == profile.id)
    r = await db.execute(q)
    account = r.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Account name cannot be empty")
        account.name = name

    return AccountResponse(
        id=account.id,
        name=account.name,
        type=account.type.value,
        provider=account.provider,
        is_active=account.is_active,
    )


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    q = select(Account).where(Account.id == account_id, Account.profile_id == profile.id)
    r = await db.execute(q)
    account = r.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await db.delete(account)
    return {"ok": True}
