from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.canvas import router as canvas_router
from app.api.courses import router as courses_router
from app.api.documents import router as documents_router
from app.api.flashcards import router as flashcards_router
from app.api.progress import router as progress_router
from app.api.quizzes import router as quizzes_router
from app.api.rag import router as rag_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(courses_router)
api_router.include_router(documents_router)
api_router.include_router(canvas_router)
api_router.include_router(rag_router)
api_router.include_router(quizzes_router)
api_router.include_router(flashcards_router)
api_router.include_router(progress_router)
