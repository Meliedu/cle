from unittest.mock import MagicMock

import jwt
import pytest

from app.services.auth import detect_role_from_email, verify_jwt


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
    monkeypatch.setattr(
        "app.services.auth.settings.better_auth_jwks_url",
        "http://localhost:3000/api/auth/jwks",
    )
    monkeypatch.setattr("app.services.auth._get_jwks_client", lambda: client)


def test_token_without_iss_claim_rejected(_stub_jwks, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth.settings.better_auth_issuer", "http://localhost:3000"
    )
    monkeypatch.setattr(
        "app.services.auth.jwt.decode",
        MagicMock(side_effect=jwt.MissingRequiredClaimError("iss")),
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        verify_jwt("fake-token")


def test_token_without_required_claim_rejected(_stub_jwks, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth.jwt.decode",
        MagicMock(side_effect=jwt.MissingRequiredClaimError("exp")),
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        verify_jwt("fake-token")


def test_token_with_valid_claims_passes(_stub_jwks, monkeypatch):
    """Happy-path: well-formed token returns a VerifiedToken with claims."""
    expected = {
        "sub": "user_1",
        "exp": 9999999999,
        "iat": 1,
        "iss": "http://localhost:3000",
        "email": "a@ust.hk",
    }
    monkeypatch.setattr(
        "app.services.auth.jwt.decode",
        MagicMock(return_value=expected),
    )
    result = verify_jwt("fake-token")
    assert result.provider == "better_auth"
    assert result.claims == expected
