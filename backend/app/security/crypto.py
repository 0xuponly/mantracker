"""Encrypt/decrypt API keys and wallet addresses at rest. Never log plaintext."""
import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import get_settings

# In-memory key set by app passphrase (unlock). Never persisted.
_unlock_key: bytes | None = None

# Fixed salt for deriving Fernet key from app passphrase (same passphrase -> same key).
APP_PASSPHRASE_SALT = b"mantracker_app_passphrase_v1"


class AppLockedError(Exception):
    """Raised when credentials cannot be decrypted because the app is locked (no passphrase provided)."""


class CredentialDecryptError(Exception):
    """Raised when decryption fails (wrong key, e.g. after changing passphrase or ENCRYPTION_KEY)."""


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def set_app_passphrase(passphrase: str) -> None:
    """Set the in-memory encryption key from the user's app passphrase. Call on unlock."""
    global _unlock_key
    if not passphrase or not passphrase.strip():
        raise ValueError("Passphrase cannot be empty")
    _unlock_key = _derive_key(passphrase.strip(), APP_PASSPHRASE_SALT)


def clear_app_passphrase() -> None:
    """Clear the in-memory key (e.g. on lock or shutdown)."""
    global _unlock_key
    _unlock_key = None


def is_unlocked() -> bool:
    """True if we can decrypt credentials (unlock key, ENCRYPTION_KEY, or secret_key when not requiring passphrase)."""
    if _unlock_key is not None:
        return True
    settings = get_settings()
    if settings.encryption_key and settings.encryption_key.strip():
        return True
    if getattr(settings, "require_app_passphrase", False):
        return False
    if settings.secret_key and settings.secret_key.strip():
        return True
    return False


def ensure_fernet() -> Fernet:
    """Return a Fernet instance. Prefers in-memory unlock key, then ENCRYPTION_KEY, then SECRET_KEY."""
    global _unlock_key
    if _unlock_key is not None:
        return Fernet(_unlock_key)
    settings = get_settings()
    if settings.encryption_key:
        key = settings.encryption_key.encode()
        if len(key) != 44:  # Fernet key is 44 bytes base64
            key = base64.urlsafe_b64encode(
                PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b"mantracker_portfolio",
                    iterations=480000,
                ).derive(settings.encryption_key.encode())
            )
        return Fernet(key)
    # Fallback: derive from secret_key (backward compat)
    salt = b"mantracker_fernet_salt"
    derived = _derive_key(settings.secret_key, salt)
    return Fernet(derived)


def ensure_fernet_or_raise() -> Fernet:
    """Return Fernet for encrypt/decrypt. Raises AppLockedError when require_app_passphrase and not unlocked."""
    if _unlock_key is not None:
        return Fernet(_unlock_key)
    settings = get_settings()
    if settings.encryption_key and settings.encryption_key.strip():
        key = settings.encryption_key.encode()
        if len(key) != 44:
            key = base64.urlsafe_b64encode(
                PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b"mantracker_portfolio",
                    iterations=480000,
                ).derive(settings.encryption_key.encode())
            )
        return Fernet(key)
    if getattr(settings, "require_app_passphrase", False):
        raise AppLockedError("App locked. Enter passphrase to unlock.")
    if settings.secret_key:
        salt = b"mantracker_fernet_salt"
        return Fernet(_derive_key(settings.secret_key, salt))
    raise AppLockedError("App locked. Enter passphrase to unlock.")


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns base64 ciphertext."""
    if not plaintext:
        return ""
    f = ensure_fernet_or_raise()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored secret. Returns plaintext; never log it. Raises AppLockedError if locked, CredentialDecryptError if wrong key."""
    if not ciphertext:
        return ""
    f = ensure_fernet_or_raise()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise CredentialDecryptError(
            "Cannot decrypt stored credentials (wrong key or corrupted). "
            "If you changed your passphrase or ENCRYPTION_KEY, re-add the account credentials."
        )
