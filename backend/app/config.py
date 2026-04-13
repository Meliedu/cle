from pydantic import model_validator
from pydantic_settings import BaseSettings

_LOCAL_DB_DEFAULT = "postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant"


class Settings(BaseSettings):
    # Runtime environment (development | production)
    environment: str = "development"

    # Database
    database_url: str = _LOCAL_DB_DEFAULT

    # Clerk
    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""
    # Comma-separated list of authorized parties (azp claim) expected in JWTs.
    clerk_allowed_azp: str = ""
    # Optional audience (aud) to enforce when Clerk JWT templates set it.
    clerk_audience: str = ""

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

    # FSRS scheduler feature flag
    fsrs_enabled: bool = True

    # Upload limits
    max_upload_size_mb: int = 100

    # Rate limits (per hour)
    student_rate_limit: int = 10
    instructor_rate_limit: int = 50

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _require_prod_database_url(self) -> "Settings":
        if self.environment == "production" and self.database_url == _LOCAL_DB_DEFAULT:
            raise ValueError(
                "DATABASE_URL must be set explicitly when ENVIRONMENT=production"
            )
        return self


settings = Settings()
