import hashlib
import secrets


def generate_api_key() -> tuple[str, str, str]:
    """
    Returns (raw_key, key_prefix, key_hash).
    raw_key is shown once to the user and never stored.
    """
    raw = "jp_" + secrets.token_urlsafe(32)
    prefix = raw[:11]  # "jp_" + 8 chars
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, key_hash


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
