import pytest
from pydantic import ValidationError
from app.config import Settings


_BASE_PROD_KWARGS = dict(
    environment="production",
    database_url="postgresql+asyncpg://u:p@db/x",
    integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
    better_auth_jwks_url="https://meli.example.com/api/auth/jwks",
    better_auth_audience="meli-backend",
    better_auth_issuer="https://meli.example.com",
    better_auth_internal_secret="x" * 32,
)


def test_weak_canvas_state_secret_rejected_in_prod():
    with pytest.raises(ValidationError, match="CANVAS_STATE_SECRET"):
        Settings(
            **_BASE_PROD_KWARGS,
            canvas_client_id="abc",
            canvas_client_secret="xyz",
            canvas_state_secret="short",
        )


def test_missing_canvas_state_secret_rejected_when_canvas_enabled():
    with pytest.raises(ValidationError, match="CANVAS_STATE_SECRET"):
        Settings(
            **_BASE_PROD_KWARGS,
            canvas_client_id="abc",
            canvas_client_secret="xyz",
            canvas_state_secret=None,
        )


def test_strong_settings_accepted_in_prod():
    Settings(
        **_BASE_PROD_KWARGS,
        canvas_client_id="abc",
        canvas_client_secret="xyz",
        canvas_state_secret="a" * 32,
    )


def test_invalid_fernet_key_rejected():
    with pytest.raises(ValidationError, match="Fernet"):
        Settings(
            environment="development",
            integrations_encryption_key="not-a-valid-fernet-key",
        )


def test_missing_better_auth_audience_rejected_in_prod():
    with pytest.raises(ValidationError, match="BETTER_AUTH_AUDIENCE"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            better_auth_jwks_url="https://meli.example.com/api/auth/jwks",
            better_auth_audience="",
            better_auth_issuer="https://meli.example.com",
            better_auth_internal_secret="x" * 32,
        )


def test_missing_better_auth_issuer_rejected_in_prod():
    with pytest.raises(ValidationError, match="BETTER_AUTH_ISSUER"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            better_auth_jwks_url="https://meli.example.com/api/auth/jwks",
            better_auth_audience="meli-backend",
            better_auth_issuer="",
            better_auth_internal_secret="x" * 32,
        )


def test_missing_better_auth_jwks_url_rejected_in_prod():
    with pytest.raises(ValidationError, match="BETTER_AUTH_JWKS_URL"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            better_auth_jwks_url="",
            better_auth_audience="meli-backend",
            better_auth_issuer="https://meli.example.com",
            better_auth_internal_secret="x" * 32,
        )


def test_missing_better_auth_internal_secret_rejected_in_prod():
    with pytest.raises(ValidationError, match="BETTER_AUTH_INTERNAL_SECRET"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            better_auth_jwks_url="https://meli.example.com/api/auth/jwks",
            better_auth_audience="meli-backend",
            better_auth_issuer="https://meli.example.com",
            better_auth_internal_secret="",
        )
