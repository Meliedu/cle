"""Integration test stubs for recalibration API endpoints.

These tests validate the API contract. They require the test database
with recalibration tables migrated (alembic upgrade head on langassistant_test).
"""

import pytest


class TestRecalibrationOverview:
    """GET /api/courses/{id}/recalibration/overview"""

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_summaries_per_content_type(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_transition_matrices(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_requires_instructor_role(self):
        pass


class TestRecalibrationItems:
    """GET /api/courses/{id}/recalibration/items"""

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_paginated_items(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_filters_by_content_type(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_requires_instructor_role(self):
        pass


class TestToggleOverride:
    """POST /api/courses/{id}/recalibration/items/{itemId}/override"""

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_toggles_override_flag(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_clears_recalibrated_label_on_override(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_404_for_missing_item(self):
        pass
