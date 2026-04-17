import pytest
from pydantic import ValidationError
from app.config import Settings


def test_weak_canvas_state_secret_rejected_in_prod():
    with pytest.raises(ValidationError, match="CANVAS_STATE_SECRET"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            canvas_client_id="abc",
            canvas_client_secret="xyz",
            canvas_state_secret="short",
            clerk_jwks_url="https://example.clerk.dev/.well-known/jwks.json",
            clerk_audience="meli-backend",
            clerk_issuer="https://example.clerk.dev",
        )


def test_missing_canvas_state_secret_rejected_when_canvas_enabled():
    with pytest.raises(ValidationError, match="CANVAS_STATE_SECRET"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            canvas_client_id="abc",
            canvas_client_secret="xyz",
            canvas_state_secret=None,
            clerk_jwks_url="https://example.clerk.dev/.well-known/jwks.json",
            clerk_audience="meli-backend",
            clerk_issuer="https://example.clerk.dev",
        )


def test_strong_settings_accepted_in_prod():
    Settings(
        environment="production",
        database_url="postgresql+asyncpg://u:p@db/x",
        integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
        canvas_client_id="abc",
        canvas_client_secret="xyz",
        canvas_state_secret="a" * 32,
        clerk_jwks_url="https://example.clerk.dev/.well-known/jwks.json",
        clerk_audience="meli-backend",
        clerk_issuer="https://example.clerk.dev",
    )


def test_invalid_fernet_key_rejected():
    with pytest.raises(ValidationError, match="Fernet"):
        Settings(
            environment="development",
            integrations_encryption_key="not-a-valid-fernet-key",
        )


def test_missing_clerk_audience_rejected_in_prod():
    with pytest.raises(ValidationError, match="CLERK_AUDIENCE"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            clerk_jwks_url="https://example.clerk.dev/.well-known/jwks.json",
            clerk_audience="",
            clerk_issuer="https://example.clerk.dev",
        )


def test_missing_clerk_issuer_rejected_in_prod():
    with pytest.raises(ValidationError, match="CLERK_ISSUER"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/x",
            integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
            clerk_jwks_url="https://example.clerk.dev/.well-known/jwks.json",
            clerk_audience="meli-backend",
            clerk_issuer="",
        )


def test_empty_clerk_allowed_azp_logs_warning_in_prod(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    Settings(
        environment="production",
        database_url="postgresql+asyncpg://u:p@db/x",
        integrations_encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",
        clerk_jwks_url="https://example.clerk.dev/.well-known/jwks.json",
        clerk_audience="meli-backend",
        clerk_issuer="https://example.clerk.dev",
        clerk_allowed_azp="",
    )
    assert any("CLERK_ALLOWED_AZP" in r.message for r in caplog.records)
