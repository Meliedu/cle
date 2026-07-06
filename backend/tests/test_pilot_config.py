import pytest
from pydantic import ValidationError


def test_cle_profile_is_valid_and_complete():
    from app.pilot import get_pilot_profile

    profile = get_pilot_profile()
    assert profile.id == "cle"
    assert profile.institution == "HKUST CLE"
    assert profile.confidence_scale.min == -2
    assert profile.confidence_scale.max == 2
    assert set(profile.confidence_scale.labels) == {-2, -1, 0, 1, 2}
    assert "reading" in profile.skill_taxonomy
    assert "pronunciation" in profile.skill_taxonomy
    assert profile.terminology["checkpoint"] == "Checkpoint"
    assert profile.role_rules["ust.hk"] == "instructor"
    assert profile.role_rules["connect.ust.hk"] == "student"
    assert profile.report_cadence.weekly is True
    assert profile.report_cadence.end_term is True
    assert len(profile.score_category_defaults) >= 1
    phases = {p.phase for p in profile.readiness}
    assert {"eligibility_survey", "ready_check"} <= phases
    for phase in profile.readiness:
        assert len(phase.questions) >= 1
    assert "recommendation" in profile.claim_limits


def test_unknown_profile_raises():
    from app.pilot import load_profile

    with pytest.raises(RuntimeError, match="Unknown PILOT_PROFILE"):
        load_profile("nonexistent")
