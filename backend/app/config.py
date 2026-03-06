"""Application configuration. Secrets from environment only."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Load from env; never log or expose secret fields."""

    app_name: str = "Portfolio Tracker"
    debug: bool = False

    # Database
    database_url: str = "sqlite+aiosqlite:///./portfolio.db"

    # Encryption for API keys and wallet addresses (required in production)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str | None = None
    # When True (default), app must be unlocked with passphrase on startup; ENCRYPTION_KEY still bypasses.
    # Set to 0 to use SECRET_KEY for credentials (no passphrase prompt).
    require_app_passphrase: bool = True

    # JWT for API auth
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Optional: Plaid (banks/brokerage)
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str = "sandbox"  # sandbox | development | production

    # Optional: Alchemy (preferred EVM token balances provider when key is set)
    alchemy_api_key: str | None = None

    # Optional: Solana RPC URL (public RPC is rate-limited; set e.g. Helius/QuickNode for higher limits)
    solana_rpc_url: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
