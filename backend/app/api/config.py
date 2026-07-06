"""Read-only pilot configuration for the frontend (terminology, taxonomy,
confidence scale, readiness definitions, claim-limit copy)."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.pilot import get_pilot_profile
from app.pilot.base import PilotProfile
from app.schemas.common import APIResponse

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=APIResponse[PilotProfile])
async def get_config(
    _user: User = Depends(get_current_user),
) -> APIResponse[PilotProfile]:
    return APIResponse(success=True, data=get_pilot_profile())
