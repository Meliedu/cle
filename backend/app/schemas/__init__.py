from app.schemas.common import APIResponse, ErrorDetail, PaginatedResponse, PaginationMeta
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate, EnrollmentCreate, EnrollmentResponse
from app.schemas.document import DocumentResponse
from app.schemas.flashcard import (
    FlashcardCardResponse,
    FlashcardProgressResponse,
    FlashcardProgressUpdate,
    FlashcardSetDetailResponse,
    FlashcardSetResponse,
)
from app.schemas.quiz import (
    QuestionResponse,
    QuestionWithAnswerResponse,
    QuizAttemptCreate,
    QuizAttemptResponse,
    QuizAttemptResult,
    QuizDetailResponse,
    QuizResponse,
    QuizUpdate,
)
from app.schemas.rag import (
    ChunkResult,
    GenerateFlashcardsRequest,
    GenerateQuizRequest,
    GenerateSummaryRequest,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.schemas.user import UserResponse
