"""Load and store credentials encrypted. Never log or expose plaintext."""
import json
from app.security.crypto import encrypt_secret, decrypt_secret


def encrypt_credential_payload(payload: dict) -> str:
    """Serialize and encrypt a credential dict for DB storage."""
    return encrypt_secret(json.dumps(payload))


def decrypt_credential_payload(encrypted: str) -> dict:
    """Decrypt and deserialize; use only in server-side adapters, never in API response."""
    if not encrypted:
        return {}
    return json.loads(decrypt_secret(encrypted))
