"""Portfolio aggregation. No credentials in response."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from app.db import AsyncSession, get_db
from app.security import get_current_profile
from app.services.portfolio_aggregator import aggregate_portfolio
from app.models import Profile

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# Overall timeout so the endpoint never hangs indefinitely
PORTFOLIO_TIMEOUT = 120.0


@router.get("")
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    """Aggregated balances per account. Credentials never included."""
    try:
        return await asyncio.wait_for(
            aggregate_portfolio(db, profile.id),
            timeout=PORTFOLIO_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Portfolio aggregation timed out. Try again.",
        )
