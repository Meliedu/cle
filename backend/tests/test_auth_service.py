from unittest.mock import MagicMock

import jwt
import pytest

from app.services.auth import detect_role_from_email, verify_clerk_token


class TestDetectRoleFromEmail:
    def test_student_domain(self):
        assert detect_role_from_email("alice@connect.ust.hk") == "student"

    def test_instructor_domain(self):
        assert detect_role_from_email("prof@ust.hk") == "instructor"

    def test_disallowed_domain_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            detect_role_from_email("user@gmail.com")

    def test_case_insensitive(self):
        assert detect_role_from_email("Alice@CONNECT.UST.HK") == "student"


@pytest.fixture
def _stub_jwks(monkeypatch):
    key = MagicMock()
    key.key = "stub-key"
    client = MagicMock()
    client.get_signing_key_from_jwt.return_value = key
    monkeypatch.setattr("app.services.auth.get_jwks_client", lambda: client)


def test_token_without_iss_claim_rejected(_stub_jwks, monkeypatch):
    # Force issuer to be configured so iss is required.
    monkeypatch.setattr("app.services.auth.settings.clerk_issuer", "https://example.clerk.dev")
    monkeypatch.setattr(
        "app.services.auth.jwt.decode",
        MagicMock(side_effect=jwt.MissingRequiredClaimError("iss")),
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        verify_clerk_token("fake-token")


def test_token_without_nbf_claim_rejected(_stub_jwks, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth.jwt.decode",
        MagicMock(side_effect=jwt.MissingRequiredClaimError("nbf")),
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        verify_clerk_token("fake-token")


def test_token_with_email_unverified_rejected(_stub_jwks, monkeypatch):
    # Simulate jwt.decode returning claims where email_verified is False.
    monkeypatch.setattr(
        "app.services.auth.jwt.decode",
        MagicMock(return_value={
            "sub": "user_1", "exp": 9999999999, "iat": 1, "nbf": 1,
            "iss": "https://example.clerk.dev", "email": "a@ust.hk",
            "email_verified": False, "azp": "http://localhost:3000",
        }),
    )
    with pytest.raises(jwt.InvalidTokenError, match="email_verified"):
        verify_clerk_token("fake-token")


def test_token_with_email_verified_passes(_stub_jwks, monkeypatch):
    """Happy-path: verified email returns claims unchanged."""
    expected = {
        "sub": "user_1", "exp": 9999999999, "iat": 1, "nbf": 1,
        "iss": "https://example.clerk.dev", "email": "a@ust.hk",
        "email_verified": True, "azp": "http://localhost:3000",
    }
    monkeypatch.setattr(
        "app.services.auth.jwt.decode",
        MagicMock(return_value=expected),
    )
    assert verify_clerk_token("fake-token") == expected
