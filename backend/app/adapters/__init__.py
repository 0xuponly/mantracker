"""Data source adapters: Plaid, CCXT, blockchain. Each returns normalized positions/balances."""
from .base import AdapterResult, BalanceItem
from .plaid_adapter import PlaidAdapter
from .exchange_adapter import ExchangeAdapter
from .wallet_adapter import WalletAdapter

__all__ = [
    "AdapterResult",
    "BalanceItem",
    "PlaidAdapter",
    "ExchangeAdapter",
    "WalletAdapter",
]
