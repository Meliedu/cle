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

    # Symmetric key for encrypting third-party tokens at rest (Canvas, etc.).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    integrations_encryption_key: str = ""

    # Allowlist of permitted Canvas LMS hostnames (comma-separated).
    # Example: "canvas.ust.hk,hkust.instructure.com". Empty in dev permits HTTPS to any non-private host.
    canvas_allowed_hosts: str = ""

    # Canvas OAuth 2.0 (Phase 1)
    canvas_client_id: str = ""
    canvas_client_secret: str = ""
    canvas_base_url: str = "https://canvas.ust.hk"
    canvas_redirect_uri: str = "http://localhost:8000/api/canvas/oauth/callback"
    # Signing key for OAuth state JWT; 32+ random bytes.
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    canvas_state_secret: str | None = None
    canvas_scopes: str = (
        "url:GET|/api/v1/users/self "
        "url:GET|/api/v1/users/self/courses "
        "url:GET|/api/v1/users/self/enrollments "
        "url:GET|/api/v1/courses/:id "
        "url:GET|/api/v1/courses/:id/enrollments "
        "url:GET|/api/v1/courses/:id/files "
        "url:GET|/api/v1/files/:id"
    )

    # App
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    allowed_email_domains: str = "connect.ust.hk,ust.hk"

    # FSRS scheduler feature flag
    fsrs_enabled: bool = True

    # Upload limits
    max_upload_size_mb: int = 100

    # Run the document-processing worker + Canvas scheduler inside the API
    # process. Default True for dev (single container). In prod we run the
    # worker as a separate Railway service and set this to False on the API
    # container so a worker OOM can't kill the API.
    run_worker_in_api: bool = True

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
        if self.environment == "production" and not self.integrations_encryption_key:
            raise ValueError(
                "INTEGRATIONS_ENCRYPTION_KEY must be set when ENVIRONMENT=production"
            )
        # Validate canvas_base_url on every environment. SSRF is a runtime
        # concern, and we want the process to fail fast if someone points
        # Canvas at a non-https or internal URL.
        # Imported inline to avoid a circular import: url_safety would
        # otherwise try to import ``settings`` before this module finishes
        # initializing.
        from app.services.url_safety import validate_canvas_base_url

        object.__setattr__(
            self,
            "canvas_base_url",
            validate_canvas_base_url(
                self.canvas_base_url, self.canvas_allowed_hosts
            ),
        )
        return self


settings = Settings()
