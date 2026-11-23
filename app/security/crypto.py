from cryptography.fernet import Fernet, InvalidToken
from app.config import settings

_fernet_instance = None


def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        key = settings.get_fernet_key()
        _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_val(value: str) -> str:
    """Encrypt a plaintext string (e.g., API key or password)."""
    if not value:
        return ""
    f = get_fernet()
    return f.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_val(encrypted_value: str) -> str:
    """Decrypt an encrypted string back to plaintext."""
    if not encrypted_value:
        return ""
    try:
        f = get_fernet()
        return f.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Fallback in case raw plaintext was stored in dev
        return encrypted_value
