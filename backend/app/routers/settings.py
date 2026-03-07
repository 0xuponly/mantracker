"""App-level settings: manage encrypted API keys (Alchemy, Solana RPC, etc.)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.db import AsyncSession, get_db
from app.models import AppSetting
from app.security.crypto import encrypt_secret


router = APIRouter(prefix="/settings", tags=["settings"])


API_KEYS = [
    "alchemy_api_key",
]


class ApiKeysUpdate(BaseModel):
    alchemy_api_key: str | None = None


class ApiKeysStatus(BaseModel):
    alchemy_api_key: bool


@router.get("/api-keys", response_model=ApiKeysStatus)
async def get_api_keys_status(
    db: AsyncSession = Depends(get_db),
):
    q = select(AppSetting).where(AppSetting.key.in_(API_KEYS))
    r = await db.execute(q)
    rows = {s.key: s for s in r.scalars().all()}
    return ApiKeysStatus(
        alchemy_api_key="alchemy_api_key" in rows,
    )


@router.put("/api-keys", response_model=ApiKeysStatus)
async def update_api_keys(
    body: ApiKeysUpdate,
    db: AsyncSession = Depends(get_db),
):
    if body.alchemy_api_key is not None and body.alchemy_api_key.strip():
        key = "alchemy_api_key"
        value = encrypt_secret(body.alchemy_api_key.strip())
        existing = await db.get(AppSetting, key)
        if existing:
            existing.encrypted_value = value
        else:
            db.add(AppSetting(key=key, encrypted_value=value))

    return await get_api_keys_status(db)

