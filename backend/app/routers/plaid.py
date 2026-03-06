"""Plaid link token and exchange. Keeps access_token server-side only."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db import AsyncSession, get_db
from app.models import Account, AccountType, AccountCredential
from app.security import get_current_profile
from app.services.credential_store import encrypt_credential_payload
from app.models import Profile

router = APIRouter(prefix="/plaid", tags=["plaid"])


class ExchangeTokenRequest(BaseModel):
    public_token: str
    account_name: str
    account_type: str = "bank"  # bank | brokerage


def _create_link_token(profile_id: int) -> str:
    from plaid.api import plaid_api
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode
    from plaid import Configuration, ApiClient
    from app.adapters.plaid_adapter import get_plaid_host

    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise HTTPException(status_code=503, detail="Plaid not configured")
    config = Configuration(
        host=get_plaid_host(settings.plaid_env),
        api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
    )
    client = ApiClient(config)
    api = plaid_api.PlaidApi(client)
    req = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=str(profile_id)),
        client_name="Portfolio Tracker",
        products=[Products("auth")],
        country_codes=[CountryCode("US")],
        language="en",
    )
    try:
        resp = api.link_token_create(req)
        return resp.link_token
    finally:
        client.close()


def _exchange_public_token(public_token: str) -> str:
    from plaid.api import plaid_api
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid import Configuration, ApiClient
    from app.adapters.plaid_adapter import get_plaid_host

    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise HTTPException(status_code=503, detail="Plaid not configured")
    config = Configuration(
        host=get_plaid_host(settings.plaid_env),
        api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
    )
    client = ApiClient(config)
    api = plaid_api.PlaidApi(client)
    try:
        req = ItemPublicTokenExchangeRequest(public_token=public_token)
        resp = api.item_public_token_exchange(req)
        return resp.access_token
    finally:
        client.close()


@router.get("/link_token")
async def link_token(profile: Profile = Depends(get_current_profile)):
    """Return a link_token for Plaid Link (client-side)."""
    try:
        token = _create_link_token(profile.id)
        return {"link_token": token}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/exchange")
async def exchange(
    body: ExchangeTokenRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    """Exchange public_token for access_token and store encrypted. Create bank/brokerage account."""
    try:
        access_token = _exchange_public_token(body.public_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    atype = AccountType.BANK if body.account_type == "bank" else AccountType.BROKERAGE
    account = Account(
        profile_id=profile.id,
        name=body.account_name,
        type=atype,
        provider="plaid",
    )
    db.add(account)
    await db.flush()
    cred = AccountCredential(
        account_id=account.id,
        encrypted_payload=encrypt_credential_payload({"access_token": access_token}),
    )
    db.add(cred)
    await db.flush()
    return {"id": account.id, "name": account.name, "type": account.type.value}
