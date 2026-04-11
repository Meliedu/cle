from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant"

    # Clerk
    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "langassistant-files"
    r2_endpoint_url: str = ""

    # OpenAI (embeddings + Whisper)
    openai_api_key: str = ""

    # OpenRouter (LLM — quiz/summary/flashcard generation)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_primary_model: str = "deepseek/deepseek-v3.2"
    openrouter_fallback_model: str = "google/gemini-2.5-flash-lite"

    # Azure Speech (pronunciation assessment)
    azure_speech_key: str = ""
    azure_speech_region: str = "eastasia"

    # iFlytek (Chinese pronunciation assessment)
    iflytek_app_id: str = ""
    iflytek_api_key: str = ""
    iflytek_api_secret: str = ""

    # App
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    allowed_email_domains: str = "connect.ust.hk,ust.hk"

    # Upload limits
    max_upload_size_mb: int = 100

    # Rate limits (per hour)
    student_rate_limit: int = 10
    instructor_rate_limit: int = 50

    # Neural spaced repetition
    fsrs_enabled: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
