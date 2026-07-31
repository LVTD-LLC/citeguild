import hashlib
import hmac
import secrets

API_KEY_PREFIX = "ak"
API_KEY_ID_BYTES = 12
API_KEY_SECRET_BYTES = 32
API_KEY_SALT_BYTES = 16
API_KEY_HASH_VERSION = "v1"
API_KEY_HASH_CONTEXT = "django-saas-starter-api-key-v1"


def generate_api_key() -> str:
    """Generate an API key with a public lookup prefix and high-entropy secret."""
    key_id = secrets.token_urlsafe(API_KEY_ID_BYTES)
    secret = secrets.token_urlsafe(API_KEY_SECRET_BYTES)
    return f"{API_KEY_PREFIX}_{key_id}.{secret}"


def get_api_key_prefix(api_key: str) -> str:
    """Return the public key prefix used for indexed lookup before hash verification."""
    if not api_key:
        return ""

    public_part, separator, secret = api_key.strip().partition(".")
    if not separator or not secret or not public_part.startswith(f"{API_KEY_PREFIX}_"):
        return ""
    return public_part


def hash_api_key(api_key: str) -> str:
    """Hash an API key with a per-key salt for fast verification."""
    salt = secrets.token_urlsafe(API_KEY_SALT_BYTES)
    return f"{API_KEY_HASH_VERSION}${salt}${_hash_api_key_with_salt(api_key, salt)}"


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    if not api_key or not api_key_hash:
        return False

    try:
        version, salt, digest = api_key_hash.split("$", 2)
    except ValueError:
        return False

    if version != API_KEY_HASH_VERSION or not salt or not digest:
        return False

    return hmac.compare_digest(_hash_api_key_with_salt(api_key, salt), digest)


def _hash_api_key_with_salt(api_key: str, salt: str) -> str:
    return hashlib.sha256(f"{API_KEY_HASH_CONTEXT}:{salt}:{api_key}".encode()).hexdigest()
