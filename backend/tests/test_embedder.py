from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import embedder
from app.services.embedder import embed_query, embed_texts


def _make_embedding(dim: int = 1536) -> list[float]:
    return [0.01] * dim


def _make_response(count: int) -> MagicMock:
    response = MagicMock()
    items = []
    for _ in range(count):
        item = MagicMock()
        item.embedding = _make_embedding()
        items.append(item)
    response.data = items
    return response


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level singleton before each test."""
    embedder._client = None
    yield
    embedder._client = None


@pytest.mark.asyncio
async def test_embed_single_text():
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(return_value=_make_response(1))

    with patch.object(embedder, "_get_client", return_value=mock_client):
        result = await embed_texts(["hello world"])

    assert len(result) == 1
    assert len(result[0]) == 1536
    mock_client.embeddings.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_multiple_texts():
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(return_value=_make_response(3))

    with patch.object(embedder, "_get_client", return_value=mock_client):
        result = await embed_texts(["one", "two", "three"])

    assert len(result) == 3
    for vec in result:
        assert len(vec) == 1536
    mock_client.embeddings.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_batches_large_input():
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        side_effect=[_make_response(100), _make_response(50)]
    )

    with patch.object(embedder, "_get_client", return_value=mock_client):
        texts = [f"text {i}" for i in range(150)]
        result = await embed_texts(texts)

    assert len(result) == 150
    assert mock_client.embeddings.create.await_count == 2


@pytest.mark.asyncio
async def test_embed_empty_list():
    result = await embed_texts([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_query_returns_single_vector():
    fake_vector = _make_embedding()

    with patch.object(
        embedder, "embed_texts", new_callable=AsyncMock, return_value=[fake_vector]
    ) as mock_embed:
        result = await embed_query("search query")

    assert result == fake_vector
    mock_embed.assert_awaited_once_with(["search query"])


def test_concept_embedding_dim_constant():
    from app.services import embedder
    assert embedder.CONCEPT_EMBEDDING_DIMENSIONS == 3072
