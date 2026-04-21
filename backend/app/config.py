import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

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
    # Expected issuer (iss) claim — set to the Clerk Frontend API URL.
    clerk_issuer: str = ""

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

    # Vision LLM (figure captioning for PDF/PPTX images, via OpenRouter)
    vlm_model: str = "google/gemini-2.5-flash"
    enable_figure_captions: bool = True
    vlm_timeout_seconds: int = 30

    # Low-text page rescue: render PDF pages whose extracted text is below
    # `page_rescue_min_words` to an image and ask the VLM to transcribe them
    # verbatim. Catches scanned/image-only PDFs and slide decks exported as
    # PDF. Capped at `page_rescue_max_pages` to bound cost on long docs.
    enable_page_rescue: bool = True
    page_rescue_min_words: int = 30
    page_rescue_max_pages: int = 40
    page_rescue_render_dpi: int = 144

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

    # Hard wall-clock cap on a single parse job (Docling, pymupdf, etc.)
    parser_timeout_seconds: int = 300

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

        if self.environment == "production":
            # JWKS URL is the only hard requirement — without it, JWT verification
            # cannot happen at all. audience/issuer/azp are defense-in-depth
            # checks; each claim is enforced in verify_clerk_token only when the
            # corresponding setting is populated. Warn loudly on missing values
            # but don't block boot.
            if not self.clerk_jwks_url:
                raise ValueError(
                    "CLERK_JWKS_URL must be set when ENVIRONMENT=production"
                )
            if not self.clerk_audience:
                logger.warning(
                    "CLERK_AUDIENCE is unset in production — audience claim "
                    "will not be verified. Set this to your Clerk JWT template "
                    "audience for defense in depth."
                )
            if not self.clerk_issuer:
                logger.warning(
                    "CLERK_ISSUER is unset in production — issuer claim will "
                    "not be verified. Set this to your Clerk frontend-api URL "
                    "for defense in depth."
                )
            if not self.clerk_allowed_azp.strip():
                logger.warning(
                    "CLERK_ALLOWED_AZP is empty in production — any authorized "
                    "party will be accepted. Set to a comma-separated list of "
                    "allowed frontend origins for defense in depth."
                )

        canvas_enabled = bool(self.canvas_client_id)
        if canvas_enabled:
            if not self.canvas_state_secret:
                raise ValueError(
                    "CANVAS_STATE_SECRET must be set when CANVAS_CLIENT_ID is configured"
                )
            if len(self.canvas_state_secret.encode()) < 32:
                raise ValueError(
                    "CANVAS_STATE_SECRET must be at least 32 bytes "
                    "(generate with: python -c 'import secrets; print(secrets.token_urlsafe(48))')"
                )

        if self.integrations_encryption_key:
            from cryptography.fernet import Fernet
            try:
                Fernet(self.integrations_encryption_key.encode())
            except Exception as exc:
                raise ValueError(
                    f"INTEGRATIONS_ENCRYPTION_KEY is not a valid Fernet key: {exc}"
                )

        # Validate canvas_base_url on every environment. SSRF is a runtime
        # concern, and we want the process to fail fast if someone points
        # Canvas at a non-https or internal URL.
        # Imported inline to avoid a circular import: url_safety would
        # otherwise try to import ``settings`` before this module finishes
        # initializing.
        from app.services.url_safety import (
            validate_canvas_base_url,
            validate_frontend_url,
        )

        object.__setattr__(
            self,
            "canvas_base_url",
            validate_canvas_base_url(
                self.canvas_base_url, self.canvas_allowed_hosts
            ),
        )
        # Validate frontend_url so the OAuth callback redirect can't be
        # shaped into something malformed by operator misconfiguration.
        object.__setattr__(
            self,
            "frontend_url",
            validate_frontend_url(self.frontend_url),
        )

        # Warn (not raise) in dev when the integrations encryption key is
        # unset — production already raises above. Encrypted columns
        # (Canvas tokens, etc.) will fail at runtime without a key, so
        # surface the issue loudly at startup.
        if (
            self.environment != "production"
            and not self.integrations_encryption_key
        ):
            logger.warning(
                "INTEGRATIONS_ENCRYPTION_KEY is unset; third-party token "
                "encryption/decryption (Canvas, etc.) will fail. Generate "
                "one with: python -c \"from cryptography.fernet import "
                "Fernet; print(Fernet.generate_key().decode())\""
            )

        # Warn when CANVAS_ALLOWED_HOSTS is unset. Canvas deployments that
        # redirect file downloads to S3-signed URLs (e.g. canvas-*.s3.*.
        # amazonaws.com) will fail host-validation unless the operator
        # allowlists those hosts here.
        if not self.canvas_allowed_hosts.strip():
            logger.warning(
                "CANVAS_ALLOWED_HOSTS is unset; file downloads from Canvas "
                "deployments that redirect to S3 signed URLs will be "
                "rejected. Set CANVAS_ALLOWED_HOSTS to a comma-separated "
                "list of permitted hostnames if your Canvas delivers files "
                "via S3 or another CDN."
            )
        return self


settings = Settings()
