import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pipeline import process_document_pipeline


class TestProcessDocumentPipeline:
    @pytest.mark.asyncio
    @patch("app.services.pipeline.embed_texts")
    @patch("app.services.pipeline.chunk_text")
    @patch("app.services.pipeline.parse_document")
    @patch("app.services.pipeline.download_file")
    async def test_full_pipeline(
        self, mock_download, mock_parse, mock_chunk, mock_embed
    ):
        from app.services.parser import ParseResult, PageContent
        from app.services.chunker import ChunkData

        doc_id = uuid.uuid4()
        course_id = uuid.uuid4()

        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.course_id = course_id
        mock_doc.r2_key = "courses/xxx/documents/yyy/test.pdf"
        mock_doc.file_type = "pdf"
        mock_doc.filename = "test.pdf"
        mock_doc.status = "pending"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute.return_value = mock_result

        mock_download.return_value = b"fake file content"
        mock_parse.return_value = ParseResult(
            text="Parsed text content here.",
            pages=[PageContent(page_number=1, text="Parsed text content here.")],
            word_count=4,
            page_count=1,
        )
        mock_chunk.return_value = [
            ChunkData(content="Parsed text content here.", chunk_index=0, page_number=1, token_count=4),
        ]
        mock_embed.return_value = [[0.1] * 1536]

        result = await process_document_pipeline(mock_session, str(doc_id))

        mock_download.assert_called_once()
        mock_parse.assert_called_once()
        mock_chunk.assert_called_once()
        mock_embed.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_pipeline_fails_on_missing_document(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Document not found"):
            await process_document_pipeline(mock_session, str(uuid.uuid4()))
