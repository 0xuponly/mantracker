"""Profile-scoped access: client sends X-Profile-Id. No passwords, no cloud."""
from fastapi import Depends, Header, HTTPException

from app.db import AsyncSession, get_db
from app.models import Profile


async def get_current_profile(
    x_profile_id: str | None = Header(None, alias="X-Profile-Id"),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Require X-Profile-Id header; load profile. All data is local to that profile."""
    if not x_profile_id or not x_profile_id.strip():
        raise HTTPException(status_code=400, detail="Missing X-Profile-Id header")
    try:
        profile_id = int(x_profile_id.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Profile-Id")
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile
