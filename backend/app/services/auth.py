import logging

import jwt
from jwt import PyJWKClient

from app.config import settings

logger = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None
_JWKS_CACHE_LIFESPAN_SECONDS = 3600


def _resolve_jwks_url() -> str:
    if settings.clerk_jwks_url:
        return settings.clerk_jwks_url
    if not settings.clerk_secret_key:
        raise ValueError("CLERK_SECRET_KEY not configured")
    raise ValueError(
        "CLERK_JWKS_URL not configured. Set it to "
        "https://<your-clerk-frontend-api>/.well-known/jwks.json"
    )


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = _resolve_jwks_url()
        logger.debug("Initializing JWKS client")
        _jwks_client = PyJWKClient(
            url,
            cache_keys=True,
            lifespan=_JWKS_CACHE_LIFESPAN_SECONDS,
        )
    return _jwks_client


def _allowed_azp() -> list[str]:
    raw = settings.clerk_allowed_azp or ""
    return [a.strip() for a in raw.split(",") if a.strip()]


def verify_clerk_token(token: str) -> dict:
    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    audience = settings.clerk_audience or None
    decode_options = {
        "require": ["sub", "exp", "iat"],
        "verify_aud": bool(audience),
    }

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        options=decode_options,
        leeway=30,
    )

    allowed_azp = _allowed_azp()
    if allowed_azp:
        azp = claims.get("azp")
        if azp not in allowed_azp:
            raise jwt.InvalidTokenError(f"Unauthorized azp claim: {azp!r}")

    return claims


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
