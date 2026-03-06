"""Local profiles: CRUD and import/export via file. No cloud, no email."""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSession, get_db
from app.models import Profile, Account, AccountType, AccountCredential
from app.security import get_current_profile

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileCreate(BaseModel):
    name: str


class ProfileUpdate(BaseModel):
    name: str


class ProfileResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[ProfileResponse])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    """List all local profiles. No auth; caller picks profile via X-Profile-Id for other routes."""
    q = select(Profile).order_by(Profile.created_at.desc())
    r = await db.execute(q)
    return [ProfileResponse(id=p.id, name=p.name) for p in r.scalars().all()]


@router.post("", response_model=ProfileResponse)
async def create_profile(body: ProfileCreate, db: AsyncSession = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name required")
    profile = Profile(name=name)
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return ProfileResponse(id=profile.id, name=profile.name)


@router.patch("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: int,
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name required")
    profile.name = name
    await db.flush()
    await db.refresh(profile)
    return ProfileResponse(id=profile.id, name=profile.name)


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int, db: AsyncSession = Depends(get_db)):
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.delete(profile)
    return {"ok": True}


# --- Export: profile + accounts + encrypted credentials as JSON file ---
EXPORT_VERSION = 1


@router.get("/{profile_id}/export")
async def export_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Export profile and all its accounts (with encrypted credentials) as JSON. Import on another machine requires the same ENCRYPTION_KEY in .env."""
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    q = (
        select(Account)
        .where(Account.profile_id == profile_id)
        .options(selectinload(Account.credential))
    )
    r = await db.execute(q)
    accounts = r.scalars().all()
    account_data = []
    for acc in accounts:
        account_data.append({
            "name": acc.name,
            "type": acc.type.value,
            "provider": acc.provider,
            "encrypted_payload": acc.credential.encrypted_payload if acc.credential else "",
        })
    payload = {
        "version": EXPORT_VERSION,
        "profile": {"name": profile.name},
        "accounts": account_data,
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="profile-{profile.name.replace(" ", "-")}.json"'
        },
    )


@router.post("/import", response_model=ProfileResponse)
async def import_profile(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Import a profile from an exported JSON file. Creates a new profile with the same name and accounts. Requires same ENCRYPTION_KEY as when exported."""
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Upload a .json file")
    try:
        body = json.loads(await file.read())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    if body.get("version") != EXPORT_VERSION:
        raise HTTPException(status_code=400, detail="Unsupported export version")
    profile_data = body.get("profile") or {}
    name = (profile_data.get("name") or "Imported").strip() or "Imported"
    accounts_data = body.get("accounts") or []
    profile = Profile(name=name)
    db.add(profile)
    await db.flush()
    for a in accounts_data:
        try:
            atype = AccountType(a.get("type", "wallet"))
        except ValueError:
            continue
        acc = Account(
            profile_id=profile.id,
            name=(a.get("name") or "Account").strip() or "Account",
            type=atype,
            provider=(a.get("provider") or "").strip() or None,
        )
        db.add(acc)
        await db.flush()
        enc = (a.get("encrypted_payload") or "").strip()
        if enc:
            cred = AccountCredential(account_id=acc.id, encrypted_payload=enc)
            db.add(cred)
    await db.flush()
    await db.refresh(profile)
    return ProfileResponse(id=profile.id, name=profile.name)
