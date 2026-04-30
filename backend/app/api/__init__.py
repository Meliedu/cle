from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.assignments import router as assignments_router
from app.api.auth import router as auth_router
from app.api.canvas import router as canvas_router
from app.api.canvas_oauth import router as canvas_oauth_router
from app.api.concept_clusters import router as concept_clusters_router
from app.api.concept_prerequisites import router as concept_prerequisites_router
from app.api.concept_tags import router as concept_tags_router
from app.api.concepts import router as concepts_router
from app.api.courses import router as courses_router
from app.api.documents import router as documents_router
from app.api.flashcards import router as flashcards_router
from app.api.instructor_alerts import router as instructor_alerts_router
from app.api.internal import router as internal_router
from app.api.live import router as live_router
from app.api.mastery import router as mastery_router
from app.api.meetings import router as meetings_router
from app.api.modules import router as modules_router
from app.api.objectives import router as objectives_router
from app.api.progress import router as progress_router
from app.api.pronunciation import router as pronunciation_router
from app.api.quizzes import router as quizzes_router
from app.api.rag import router as rag_router
from app.api.recalibration import router as recalibration_router
from app.api.revision import router as revision_router
from app.api.speech import router as speech_router
from app.api.syllabus import router as syllabus_router

api_router = APIRouter(prefix="/api")
api_router.include_router(analytics_router)
api_router.include_router(assignments_router)
api_router.include_router(auth_router)
api_router.include_router(courses_router)
api_router.include_router(documents_router)
api_router.include_router(canvas_router)
api_router.include_router(canvas_oauth_router)
api_router.include_router(rag_router)
api_router.include_router(quizzes_router)
api_router.include_router(flashcards_router)
api_router.include_router(pronunciation_router)
api_router.include_router(progress_router)
api_router.include_router(revision_router)
api_router.include_router(speech_router)
api_router.include_router(syllabus_router)
api_router.include_router(live_router)
api_router.include_router(meetings_router)
api_router.include_router(modules_router)
api_router.include_router(objectives_router)
api_router.include_router(recalibration_router)
api_router.include_router(concepts_router)
api_router.include_router(concept_prerequisites_router)
api_router.include_router(concept_clusters_router)
api_router.include_router(concept_tags_router)
api_router.include_router(internal_router)
api_router.include_router(mastery_router)
api_router.include_router(instructor_alerts_router)
