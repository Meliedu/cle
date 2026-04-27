import logging
from dataclasses import dataclass
from typing import Literal

import jwt
from jwt import PyJWKClient

from app.config import settings

logger = logging.getLogger(__name__)

_JWKS_CACHE_LIFESPAN_SECONDS = 3600

_jwks_client: PyJWKClient | None = None


# Provider literal kept for downstream compatibility (a few call sites still
# pattern-match on it). Only one value is meaningful post-cutover.
Provider = Literal["better_auth"]


@dataclass(frozen=True)
class VerifiedToken:
    provider: Provider
    claims: dict


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not settings.better_auth_jwks_url:
            raise jwt.InvalidTokenError("BETTER_AUTH_JWKS_URL not configured")
        _jwks_client = PyJWKClient(
            settings.better_auth_jwks_url,
            cache_keys=True,
            lifespan=_JWKS_CACHE_LIFESPAN_SECONDS,
        )
    return _jwks_client


def verify_jwt(token: str) -> VerifiedToken:
    """Verify a Better Auth JWT and return its claims.

    Better Auth's JWT plugin signs with EdDSA (Ed25519) by default. We
    accept the common asymmetric algorithms so a key rotation onto RS256
    or ES256 wouldn't require a code change.
    """
    jwks_client = _get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    audience = settings.better_auth_audience or None
    issuer = settings.better_auth_issuer or None

    required = ["sub", "exp", "iat"]
    if issuer:
        required.append("iss")

    decode_options = {
        "require": required,
        "verify_aud": bool(audience),
        "verify_iss": bool(issuer),
    }

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["EdDSA", "RS256", "ES256"],
        audience=audience,
        issuer=issuer,
        options=decode_options,
        leeway=30,
    )

    return VerifiedToken("better_auth", claims)


def detect_role_from_email(email: str) -> str:
    domain = email.split("@")[-1].lower()
    allowed = [d.strip().lower() for d in settings.allowed_email_domains.split(",")]
    if domain not in allowed:
        raise ValueError(f"Email domain {domain} not allowed")
    if domain == "connect.ust.hk":
        return "student"
    if domain == "ust.hk":
        return "instructor"
    raise ValueError(f"No role mapping configured for domain {domain}")
