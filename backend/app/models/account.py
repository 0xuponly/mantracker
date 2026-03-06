"""Account and encrypted credentials. Credentials never exposed in API responses."""
import enum
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class AccountType(str, enum.Enum):
    BANK = "bank"
    BROKERAGE = "brokerage"
    EXCHANGE = "exchange"   # centralized crypto
    WALLET = "wallet"       # blockchain wallet (BTC, EVM, Solana, etc.)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "Chase Checking"
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    # Optional provider id (e.g. "plaid", "binance", "ethereum", "bitcoin", "solana")
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="accounts")
    credential: Mapped["AccountCredential | None"] = relationship(
        "AccountCredential",
        back_populates="account",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AccountCredential(Base):
    """Encrypted API keys / wallet addresses. Never return raw fields to API."""
    __tablename__ = "account_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # Encrypted JSON: e.g. {"access_token": "..."} for Plaid, {"api_key":"","secret":""} for exchange, {"address": "0x..."} for wallet
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account: Mapped["Account"] = relationship("Account", back_populates="credential")
