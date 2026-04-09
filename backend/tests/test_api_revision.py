import pytest
from unittest.mock import AsyncMock, patch


class TestStartRevision:
    @pytest.mark.asyncio
    async def test_start_returns_preparing_when_pool_empty(self):
        """When no pool items exist, should return status=preparing."""
        # Requires test DB with enrolled user, course with chunks
        pass  # Implement with test fixtures

    @pytest.mark.asyncio
    async def test_start_returns_ready_with_pool(self):
        """When pool has items, should return status=ready with first_item."""
        pass

    @pytest.mark.asyncio
    async def test_start_requires_enrollment(self):
        """Non-enrolled user should get 403."""
        pass


class TestSubmitAnswer:
    @pytest.mark.asyncio
    async def test_quiz_correct_answer_scores_1(self):
        """Correct quiz answer should return score=1.0, is_correct=true."""
        pass

    @pytest.mark.asyncio
    async def test_quiz_wrong_answer_scores_0(self):
        """Wrong quiz answer should return score=0.0, is_correct=false."""
        pass

    @pytest.mark.asyncio
    async def test_bandit_updates_after_threshold(self):
        """After COLD_START_THRESHOLD attempts, bandit weights should change."""
        pass

    @pytest.mark.asyncio
    async def test_next_item_returned_in_response(self):
        """Response should include next_item for continued practice."""
        pass


class TestEndSession:
    @pytest.mark.asyncio
    async def test_end_returns_summary(self):
        """Ending a session should return stats with scores_by_difficulty."""
        pass
