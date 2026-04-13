import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api._helpers import verify_enrollment
from app.api.deps import get_current_user, get_db, require_instructor
from app.database import async_session_factory
from app.models.course import Enrollment
from app.models.quiz import Question, Quiz
from app.models.session import LiveSession
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.live import CreateLiveSessionRequest, LiveSessionResponse
from app.services.auth import verify_clerk_token
from app.services.live_quiz import calculate_points, generate_join_code, manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-quiz"])


class LiveAnswerRequest(BaseModel):
    question_index: int
    answer: str
    elapsed_seconds: float = 0.0


def _session_to_response(
    session: LiveSession, current_user_id: uuid.UUID | None = None
) -> LiveSessionResponse:
    return LiveSessionResponse(
        id=str(session.id),
        quiz_id=str(session.quiz_id),
        course_id=str(session.course_id),
        host_id=str(session.host_id),
        join_code=session.join_code or "",
        status=session.status,
        participant_count=session.participant_count,
        time_limit_seconds=session.time_limit_seconds or 30,
        created_at=session.created_at.isoformat(),
        is_host=current_user_id is not None and session.host_id == current_user_id,
    )


async def _get_session_or_404(db: AsyncSession, session_id: str) -> LiveSession:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(select(LiveSession).where(LiveSession.id == session_uuid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/courses/{course_id}/live-sessions")
async def create_live_session(
    course_id: uuid.UUID,
    req: CreateLiveSessionRequest,
    user=Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[LiveSessionResponse]:
    """Create a new live quiz session for an instructor."""
    await verify_enrollment(db, course_id, user.id)
    quiz_result = await db.execute(
        select(Quiz).where(Quiz.id == req.quiz_id, Quiz.course_id == course_id)
    )
    quiz = quiz_result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found"
        )

    join_code = generate_join_code()

    session = LiveSession(
        quiz_id=req.quiz_id,
        course_id=course_id,
        host_id=user.id,
        join_code=join_code,
        time_limit_seconds=req.time_limit_seconds,
        settings=req.settings,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    q_result = await db.execute(
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .where(Quiz.id == req.quiz_id)
    )
    quiz_with_questions = q_result.scalar_one()
    total_questions = len(quiz_with_questions.questions)

    manager.create_session(
        str(session.id), total_questions, req.time_limit_seconds
    )

    return APIResponse(
        success=True, data=_session_to_response(session, user.id)
    )


@router.get("/courses/{course_id}/live-sessions")
async def list_live_sessions(
    course_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[LiveSessionResponse]]:
    """List active or waiting live sessions for a course."""
    await verify_enrollment(db, course_id, user.id)
    stmt = (
        select(LiveSession)
        .where(
            LiveSession.course_id == course_id,
            LiveSession.status.in_(["waiting", "active"]),
        )
        .order_by(LiveSession.created_at.desc())
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return APIResponse(
        success=True,
        data=[_session_to_response(s, user.id) for s in sessions],
    )


@router.get("/live-sessions/by-code/{code}")
async def get_live_session_by_code(
    code: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[LiveSessionResponse]:
    """Look up an active live session by its join code. Student-facing."""
    normalized = (code or "").strip().upper()
    if len(normalized) != 6:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        select(LiveSession).where(
            LiveSession.join_code == normalized,
            LiveSession.status.in_(["waiting", "active"]),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await verify_enrollment(db, session.course_id, user.id)
    return APIResponse(success=True, data=_session_to_response(session, user.id))


@router.get("/live-sessions/{session_id}")
async def get_live_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[LiveSessionResponse]:
    """Get a single live session by ID."""
    session = await _get_session_or_404(db, session_id)
    await verify_enrollment(db, session.course_id, user.id)
    return APIResponse(success=True, data=_session_to_response(session, user.id))


@router.delete("/live-sessions/{session_id}", response_model=APIResponse[None])
async def delete_live_session(
    session_id: str,
    user=Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[None]:
    """Delete a live session (host only)."""
    session = await _get_session_or_404(db, session_id)
    if session.host_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not session host"
        )
    await db.delete(session)
    await db.commit()
    manager.remove_session(session_id)
    return APIResponse(success=True, data=None)


@router.get("/live-sessions/{session_id}/state")
async def get_live_state(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll the current in-memory state of a live session."""
    session = await _get_session_or_404(db, session_id)
    await verify_enrollment(db, session.course_id, user.id)

    state = manager.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session state not found")

    return APIResponse(
        success=True,
        data={
            "status": state.status,
            "current_question_index": state.current_question_index,
            "time_limit": state.time_limit,
            "leaderboard": state.get_leaderboard(),
            "participant_count": len(state.player_scores),
        },
    )


@router.post("/live-sessions/{session_id}/next-question")
async def live_next_question(
    session_id: str,
    user=Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Advance to the next question (host only)."""
    session = await _get_session_or_404(db, session_id)
    if session.host_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not session host"
        )

    state = manager.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session state not found")

    state.next_question()
    return APIResponse(
        success=True,
        data={
            "status": state.status,
            "current_question_index": state.current_question_index,
        },
    )


@router.post("/live-sessions/{session_id}/answer")
async def live_answer(
    session_id: str,
    body: LiveAnswerRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer. The server verifies correctness and computes points;
    user_id is taken from the authenticated JWT (never the request body)."""
    session = await _get_session_or_404(db, session_id)
    await verify_enrollment(db, session.course_id, user.id)

    state = manager.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session state not found")

    question = await _load_question(db, session.quiz_id, body.question_index)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    is_correct = _answer_is_correct(body.answer, question.correct_answer)
    points = calculate_points(is_correct, body.elapsed_seconds, state.time_limit)
    state.record_answer(str(user.id), body.answer, points)

    return APIResponse(
        success=True,
        data={"is_correct": is_correct, "points": points},
    )


@router.post("/live-sessions/{session_id}/end")
async def live_end_session(
    session_id: str,
    user=Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """End the session (host only)."""
    session = await _get_session_or_404(db, session_id)
    if session.host_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not session host"
        )

    state = manager.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session state not found")

    state.status = "finished"
    return APIResponse(
        success=True,
        data={"final_leaderboard": state.get_leaderboard()},
    )


async def _load_question(
    db: AsyncSession, quiz_id: uuid.UUID, question_index: int
) -> Question | None:
    result = await db.execute(
        select(Question).where(
            Question.quiz_id == quiz_id,
            Question.question_index == question_index,
        )
    )
    return result.scalar_one_or_none()


def _answer_is_correct(submitted: str, correct: str) -> bool:
    return (submitted or "").strip().lower() == (correct or "").strip().lower()


## ------------------------------------------------------------------ ##
##  WebSocket endpoint                                                  ##
## ------------------------------------------------------------------ ##


async def _resolve_ws_user(
    db: AsyncSession, clerk_sub: str
) -> User | None:
    result = await db.execute(select(User).where(User.clerk_id == clerk_sub))
    return result.scalar_one_or_none()


async def _is_enrolled(
    db: AsyncSession, course_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


@router.websocket("/live/{session_id}")
async def websocket_live(
    websocket: WebSocket,
    session_id: str,
    token: str = "",
):
    """WebSocket handler for live quiz sessions.

    Auth: pass Clerk JWT as ?token= query param. The authenticated user is
    resolved server-side — messages can never spoof user_id or is_correct.
    """
    logger.info("WS connect attempt for session %s, token length=%d", session_id, len(token))
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        claims = verify_clerk_token(token)
    except Exception as e:
        logger.warning("WS auth failed for session %s: %s", session_id, e)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    clerk_sub = claims.get("sub")
    if not clerk_sub:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    async with async_session_factory() as db:
        user = await _resolve_ws_user(db, clerk_sub)
        if user is None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

        session = await _get_session_or_404(db, session_id)
        if not await _is_enrolled(db, session.course_id, user.id):
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    is_host = session.host_id == user.id

    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            state = manager.get_session(session_id)

            if not state:
                await websocket.send_json(
                    {"type": "error", "message": "Session not found"}
                )
                continue

            if msg_type == "next_question":
                if not is_host:
                    await websocket.send_json(
                        {"type": "error", "message": "Host only"}
                    )
                    continue
                state.next_question()
                if state.status == "finished":
                    await manager.broadcast(
                        session_id,
                        {
                            "type": "session_ended",
                            "final_leaderboard": state.get_leaderboard(),
                        },
                    )
                else:
                    await manager.broadcast(
                        session_id,
                        {
                            "type": "question",
                            "index": state.current_question_index,
                            "time_limit": state.time_limit,
                        },
                    )

            elif msg_type == "answer":
                try:
                    question_index = int(data.get("question_index", 0))
                except (TypeError, ValueError):
                    await websocket.send_json(
                        {"type": "error", "message": "Invalid question_index"}
                    )
                    continue
                answer = str(data.get("answer", ""))
                try:
                    elapsed = float(data.get("elapsed_seconds", 0))
                except (TypeError, ValueError):
                    elapsed = 0.0

                async with async_session_factory() as db:
                    question = await _load_question(db, session.quiz_id, question_index)
                if question is None:
                    await websocket.send_json(
                        {"type": "error", "message": "Question not found"}
                    )
                    continue

                is_correct = _answer_is_correct(answer, question.correct_answer)
                points = calculate_points(is_correct, elapsed, state.time_limit)
                state.record_answer(str(user.id), answer, points)

                await manager.broadcast(
                    session_id,
                    {
                        "type": "answer_received",
                        "user_id": str(user.id),
                        "leaderboard": state.get_leaderboard(),
                    },
                )

            elif msg_type == "end_session":
                if not is_host:
                    await websocket.send_json(
                        {"type": "error", "message": "Host only"}
                    )
                    continue
                state.status = "finished"
                await manager.broadcast(
                    session_id,
                    {
                        "type": "session_ended",
                        "final_leaderboard": state.get_leaderboard(),
                    },
                )

    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
