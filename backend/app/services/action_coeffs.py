"""Quarterly retune of scoring coefficients from action_outcomes telemetry.

For Phase 3 ship the retune **proposes** deltas but does not apply them —
the result blob is written to Task.payload['result'] for human review.
A future change can flip ``apply=True`` once the proposals are validated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionOutcome
from app.services.scoring import DEFAULT_COEFFS


async def retune_action_coefficients(
    db: AsyncSession, *, window_days: int = 90
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    summary: dict[str, dict] = {}
    for action_type, current_coef in DEFAULT_COEFFS.items():
        on_mean = (
            await db.execute(
                select(func.avg(ActionOutcome.outcome_score)).where(
                    ActionOutcome.action_type == action_type,
                    ActionOutcome.engine_variant == "on",
                    ActionOutcome.completed.is_(True),
                    ActionOutcome.served_at >= cutoff,
                )
            )
        ).scalar_one()
        off_mean = (
            await db.execute(
                select(func.avg(ActionOutcome.outcome_score)).where(
                    ActionOutcome.action_type == action_type,
                    ActionOutcome.engine_variant == "off",
                    ActionOutcome.completed.is_(True),
                    ActionOutcome.served_at >= cutoff,
                )
            )
        ).scalar_one()

        on_f = float(on_mean) if on_mean is not None else None
        off_f = float(off_mean) if off_mean is not None else None
        if on_f is None or off_f is None or off_f == 0:
            suggested = current_coef
        else:
            # Scale the coefficient by the lift ratio (clamped to [0.5×, 2×]
            # so a single noisy quarter can't flip recommendations wildly).
            lift = on_f / off_f
            lift = max(0.5, min(2.0, lift))
            suggested = current_coef * lift

        summary[action_type] = {
            "old_coef": current_coef,
            "mean_outcome_on": on_f,
            "mean_outcome_off": off_f,
            "suggested_coef": suggested,
            "applied": False,
        }
    return {"window_days": window_days, "summary": summary}
