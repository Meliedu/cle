import httpx
import openai

from app.config import settings

EMBEDDING_MODEL = "openai/text-embedding-3-large"
EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 100
# Explicit per-request timeout so a hung upstream can never deadlock the worker.
_EMBED_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=_EMBED_TIMEOUT,
            max_retries=2,
        )
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = _get_client()
    embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        embeddings.extend([item.embedding for item in response.data])

    return embeddings


async def embed_query(query: str) -> list[float]:
    result = await embed_texts([query])
    return result[0]


CONCEPT_EMBEDDING_DIMENSIONS = 3072  # native size of text-embedding-3-large


async def embed_concept_texts(texts: list[str]) -> list[list[float]]:
    """Embed concept candidate names/descriptions at native 3072 dims.

    The chunk embedder uses 1536 (reduced) for storage cost. Concepts use the
    full 3072 — they're far fewer rows and we want maximum semantic resolution
    for cluster dedup.
    """
    if not texts:
        return []
    client = _get_client()
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        # Note: no `dimensions=` arg — return native size.
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        embeddings.extend([item.embedding for item in response.data])
    return embeddings
