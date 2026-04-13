"""Symmetric encryption for third-party tokens stored at rest."""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    key = settings.integrations_encryption_key
    if not key:
        raise RuntimeError(
            "INTEGRATIONS_ENCRYPTION_KEY is not configured. Generate with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _cipher().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt secret — wrong key or tampered payload") from exc
