import base64
import logging

import jwt
from jwt import PyJWKClient

from app.config import settings

logger = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None


def _resolve_jwks_url() -> str:
    if settings.clerk_jwks_url:
        return settings.clerk_jwks_url
    # Derive from Clerk secret key — the Frontend API domain is needed
    # Clerk dev instances use: https://<frontend-api-domain>/.well-known/jwks.json
    # The frontend API domain can be derived from the publishable key
    # but we don't have that in backend. Use the Clerk convention instead.
    sk = settings.clerk_secret_key
    if not sk:
        raise ValueError("CLERK_SECRET_KEY not configured")
    # For development, we can fetch JWKS from Clerk's Backend API with auth
    # But the proper way is to set CLERK_JWKS_URL in .env
    raise ValueError(
        "CLERK_JWKS_URL not configured. Set it to "
        "https://<your-clerk-frontend-api>/.well-known/jwks.json"
    )


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = _resolve_jwks_url()
        logger.info("Using JWKS URL: %s", url)
        _jwks_client = PyJWKClient(url)
    return _jwks_client


def verify_clerk_token(token: str) -> dict:
    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    return claims


def detect_role_from_email(email: str) -> str:
    domain = email.split("@")[-1].lower()
    allowed = settings.allowed_email_domains.split(",")
    if domain not in allowed:
        raise ValueError(f"Email domain {domain} not allowed")
    if domain == "connect.ust.hk":
        return "student"
    elif domain == "ust.hk":
        return "instructor"
    return "student"
