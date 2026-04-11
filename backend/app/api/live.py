import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.quiz import Quiz
from app.models.session import LiveSession
from app.schemas.common import APIResponse
from app.schemas.live import CreateLiveSessionRequest, LiveSessionResponse
from app.services.auth import verify_clerk_token
from app.services.live_quiz import calculate_points, generate_join_code, manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-quiz"])


def _session_to_response(session: LiveSession) -> LiveSessionResponse:
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
    )


@router.post("/courses/{course_id}/live-sessions")
async def create_live_session(
    course_id: str,
    req: CreateLiveSessionRequest,
    user=Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[LiveSessionResponse]:
    """Create a new live quiz session for an instructor."""
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

    # Load questions to get the total count for in-memory session state
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
        success=True, data=_session_to_response(session)
    )


@router.get("/courses/{course_id}/live-sessions")
async def list_live_sessions(
    course_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[LiveSessionResponse]]:
    """List active or waiting live sessions for a course."""
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
        data=[_session_to_response(s) for s in sessions],
    )


@router.get("/live-sessions/{session_id}")
async def get_live_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[LiveSessionResponse]:
    """Get a single live session by ID."""
    result = await db.execute(
        select(LiveSession).where(LiveSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return APIResponse(
        success=True, data=_session_to_response(session)
    )


## ------------------------------------------------------------------ ##
##  REST endpoints for polling-based live quiz (WebSocket alternative)  ##
## ------------------------------------------------------------------ ##


@router.get("/live-sessions/{session_id}/state")
async def get_live_state(
    session_id: str,
    user=Depends(get_current_user),
):
    """Poll the current in-memory state of a live session."""
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
):
    """Advance to the next question (host only)."""
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
    body: dict,
    user=Depends(get_current_user),
):
    """Submit an answer (student)."""
    state = manager.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session state not found")

    user_id = body.get("user_id", str(user.id))
    answer = body.get("answer", "")
    is_correct = body.get("is_correct", False)
    elapsed = body.get("elapsed_seconds", 0)
    points = calculate_points(is_correct, elapsed, state.time_limit)
    state.record_answer(user_id, answer, points)

    return APIResponse(success=True, data={"points": points})


@router.post("/live-sessions/{session_id}/end")
async def live_end_session(
    session_id: str,
    user=Depends(require_instructor),
):
    """End the session (host only)."""
    state = manager.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session state not found")

    state.status = "finished"
    return APIResponse(
        success=True,
        data={"final_leaderboard": state.get_leaderboard()},
    )


## ------------------------------------------------------------------ ##
##  WebSocket endpoint (kept for non-WSL2 / production use)            ##
## ------------------------------------------------------------------ ##


@router.websocket("/live/{session_id}")
async def websocket_live(
    websocket: WebSocket,
    session_id: str,
    token: str = "",
):
    """WebSocket handler for live quiz sessions.

    Auth: pass Clerk JWT as ?token= query param (browser WebSocket API
    cannot send custom headers).

    Message types:
      - next_question: advance to the next question (host only)
      - answer: submit an answer (student)
      - end_session: end the session early (host only)
    """
    logger.info("WS connect attempt for session %s, token length=%d", session_id, len(token))
    if not token:
        logger.warning("WS rejected: no token for session %s", session_id)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        verify_clerk_token(token)
    except Exception as e:
        logger.warning("WS auth failed for session %s: %s", session_id, e)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

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
                question_index = data.get("question_index", 0)
                answer = data.get("answer", "")
                user_id = data.get("user_id", "")

                is_correct = data.get("is_correct", False)
                elapsed = data.get("elapsed_seconds", 0)
                points = calculate_points(
                    is_correct, elapsed, state.time_limit
                )
                state.record_answer(user_id, answer, points)

                await manager.broadcast(
                    session_id,
                    {
                        "type": "answer_received",
                        "user_id": user_id,
                        "leaderboard": state.get_leaderboard(),
                    },
                )

            elif msg_type == "end_session":
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
