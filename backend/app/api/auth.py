from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.user import NotificationPrefsUpdate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=APIResponse[UserResponse])
async def get_me(current_user: User = Depends(get_current_user)):
    return APIResponse(success=True, data=UserResponse.model_validate(current_user))


@router.patch("/me/preferences", response_model=APIResponse[UserResponse])
async def update_notification_prefs(
    body: NotificationPrefsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Merge the submitted (non-None) notification preference keys over the
    stored dict. Unknown keys are rejected upstream by ``extra="forbid"`` (422).
    """
    submitted = body.notification_prefs.model_dump(exclude_none=True)
    # Immutable merge: build a fresh dict rather than mutating the stored one.
    current_user.notification_prefs = {**(current_user.notification_prefs or {}), **submitted}
    await db.commit()
    await db.refresh(current_user)
    return APIResponse(success=True, data=UserResponse.model_validate(current_user))
