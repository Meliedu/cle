import pytest

from app.services.auth import detect_role_from_email


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
