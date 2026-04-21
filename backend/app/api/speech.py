import asyncio
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import get_current_user, get_db
from app.models.course import Course
from app.models.score import PronunciationScore
from app.schemas.common import APIResponse
from app.schemas.speech import (
    GeneratePromptsRequest,
    PracticePromptResponse,
    PronunciationGradeResponse,
    PronunciationHistoryEntry,
    WordScoreResponse,
)
from app.services.embedder import embed_query
from app.services.gamification import award_xp
from app.services.generator import generate_revision_speaking
from app.services.retriever import retrieve_chunks
from app.services.speech import grade_pronunciation
from app.services.storage import _sanitize_filename, upload_file

router = APIRouter(prefix="/speech", tags=["speech"])

_MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
_ALLOWED_AUDIO_MIMES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
}


def _audio_magic_ok(content_type: str, data: bytes) -> bool:
    """Loose magic-byte sniff: rejects obviously-wrong payloads."""
    if len(data) < 12:
        return False
    head = data[:12]
    if content_type in {"audio/wav", "audio/wave", "audio/x-wav"}:
        return head.startswith(b"RIFF") and head[8:12] == b"WAVE"
    if content_type in {"audio/mpeg", "audio/mp3"}:
        return head.startswith(b"ID3") or head[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}
    if content_type == "audio/ogg":
        return head.startswith(b"OggS")
    if content_type == "audio/webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    if content_type in {"audio/mp4", "audio/m4a", "audio/x-m4a"}:
        return head[4:8] == b"ftyp"
    return False


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
    try:
        course_uuid = uuid.UUID(course_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course_id"
        )

    await verify_enrollment(db, course_uuid, user.id)

    content_type = (audio.content_type or "").lower()
    if content_type not in _ALLOWED_AUDIO_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio type: {content_type or 'unknown'}",
        )

    audio_bytes = await audio.read()
    if len(audio_bytes) > _MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file too large (max 25MB)",
        )
    if not _audio_magic_ok(content_type, audio_bytes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio content does not match declared type",
        )

    safe_name = _sanitize_filename(audio.filename or "audio.wav")
    r2_key = f"pronunciation/{user.id}/{uuid.uuid4()}_{safe_name}"
    await asyncio.to_thread(upload_file, r2_key, audio_bytes, content_type)

    # Grade pronunciation
    result = await grade_pronunciation(audio_bytes, reference_text, language)

    # Store in DB
    score = PronunciationScore(
        user_id=user.id,
        course_id=course_uuid,
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
    await award_xp(db, user.id, course_uuid, xp=30, activity="pronunciation")
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


@router.post(
    "/generate-prompts",
    response_model=APIResponse[list[PracticePromptResponse]],
)
async def generate_prompts(
    body: GeneratePromptsRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[PracticePromptResponse]]:
    """Generate practice sentences from course materials at a chosen difficulty.

    Runs synchronously — LLM call completes in a few seconds and results
    are ephemeral (no persistence). The frontend uses these as suggestions
    that populate the reference-text input.
    """
    await verify_enrollment(db, body.course_id, user.id)

    course_row = await db.execute(
        select(Course).where(
            Course.id == body.course_id, Course.deleted_at.is_(None)
        )
    )
    course = course_row.scalar_one_or_none()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    document_uuids = list(body.document_ids) if body.document_ids else None
    difficulty_for_prompt = (
        body.difficulty if body.difficulty != "mixed" else "medium"
    )

    query_embedding = await embed_query("speaking practice sentences")
    chunks = await retrieve_chunks(
        db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=12,
        document_ids=document_uuids,
    )
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No course materials available to generate prompts from",
        )

    targets = await generate_revision_speaking(
        chunks,
        difficulty=difficulty_for_prompt,
        num_items=body.num_prompts,
        language=course.language,
    )

    data = [PracticePromptResponse(target_text=t.target_text) for t in targets]
    return APIResponse(success=True, data=data)


@router.get(
    "/courses/{course_id}/pronunciation-history",
    response_model=APIResponse[list[PronunciationHistoryEntry]],
)
async def pronunciation_history(
    course_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[PronunciationHistoryEntry]]:
    try:
        course_uuid = uuid.UUID(course_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course_id"
        )
    await verify_enrollment(db, course_uuid, user.id)
    stmt = (
        select(PronunciationScore)
        .where(
            PronunciationScore.user_id == user.id,
            PronunciationScore.course_id == course_uuid,
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
