from dataclasses import dataclass
from typing import Optional


@dataclass
class BalanceItem:
    """Single balance line: asset name and amount (and optional value in USD if known)."""
    asset: str
    amount: float
    currency: Optional[str] = None
    usd_value: Optional[float] = None
    raw_name: Optional[str] = None  # e.g. account mask "0004"
    chain: Optional[str] = None  # e.g. "Ethereum", "Arbitrum" when showing multi-chain EVM


@dataclass
class AdapterResult:
    """Result from an account adapter: list of balances and optional error."""
    balances: list[BalanceItem]
    error: Optional[str] = None
