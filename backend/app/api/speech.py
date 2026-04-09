from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.score import PronunciationScore
from app.schemas.common import APIResponse
from app.schemas.speech import (
    PronunciationGradeResponse,
    PronunciationHistoryEntry,
    WordScoreResponse,
)
from app.services.gamification import award_xp
from app.services.speech import grade_pronunciation
from app.services.storage import upload_file

router = APIRouter(prefix="/speech", tags=["speech"])


@router.post(
    "/grade",
    response_model=APIResponse[PronunciationGradeResponse],
)
async def grade(
    audio: UploadFile = File(...),
    reference_text: str = Form(...),
    course_id: str = Form(...),
    language: str = Form(default="english"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[PronunciationGradeResponse]:
    audio_bytes = await audio.read()

    # Upload audio to R2
    r2_key = f"pronunciation/{user.id}/{audio.filename}"
    upload_file(r2_key, audio_bytes, audio.content_type or "audio/wav")

    # Grade pronunciation
    result = await grade_pronunciation(audio_bytes, reference_text, language)

    # Store in DB
    score = PronunciationScore(
        user_id=user.id,
        course_id=course_id,
        language=language,
        target_text=reference_text,
        audio_r2_key=r2_key,
        overall_score=result.overall_score,
        accuracy_score=result.accuracy_score,
        fluency_score=result.fluency_score,
        completeness_score=result.completeness_score,
        prosody_score=result.prosody_score,
        detailed_result={"word_scores": [asdict(w) for w in result.word_scores]},
        grading_provider=result.provider,
    )
    db.add(score)

    # Award XP
    await award_xp(db, user.id, course_id, xp=30, activity="pronunciation")
    await db.commit()
    await db.refresh(score)

    return APIResponse(
        success=True,
        data=PronunciationGradeResponse(
            id=str(score.id),
            overall_score=result.overall_score,
            accuracy_score=result.accuracy_score,
            fluency_score=result.fluency_score,
            completeness_score=result.completeness_score,
            prosody_score=result.prosody_score,
            word_scores=[
                WordScoreResponse(
                    word=w.word,
                    accuracy=w.accuracy,
                    error_type=w.error_type,
                )
                for w in result.word_scores
            ],
            provider=result.provider,
        ),
    )


@router.get(
    "/courses/{course_id}/pronunciation-history",
    response_model=APIResponse[list[PronunciationHistoryEntry]],
)
async def pronunciation_history(
    course_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[PronunciationHistoryEntry]]:
    stmt = (
        select(PronunciationScore)
        .where(
            PronunciationScore.user_id == user.id,
            PronunciationScore.course_id == course_id,
        )
        .order_by(PronunciationScore.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    scores = result.scalars().all()

    entries = [
        PronunciationHistoryEntry(
            id=str(s.id),
            target_text=s.target_text,
            overall_score=float(s.overall_score or 0),
            accuracy_score=float(s.accuracy_score or 0),
            fluency_score=float(s.fluency_score or 0),
            created_at=s.created_at.isoformat(),
        )
        for s in scores
    ]

    return APIResponse(success=True, data=entries)
