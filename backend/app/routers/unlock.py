"""App-level unlock: passphrase gates decryption of stored credentials."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.security.crypto import set_app_passphrase, is_unlocked, AppLockedError

router = APIRouter(prefix="/unlock", tags=["unlock"])


class UnlockBody(BaseModel):
    passphrase: str


@router.get("/status")
def unlock_status() -> dict:
    """Return whether the app can decrypt credentials (unlocked or ENCRYPTION_KEY set)."""
    return {"unlocked": is_unlocked()}


@router.post("")
def unlock(body: UnlockBody) -> dict:
    """Set the in-memory key from the user's passphrase. Required if ENCRYPTION_KEY is not set."""
    try:
        set_app_passphrase(body.passphrase)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
