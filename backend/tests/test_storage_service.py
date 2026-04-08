import uuid
from unittest.mock import MagicMock, patch

from app.services.storage import build_r2_key, upload_file, download_file, delete_file


class TestBuildR2Key:
    def test_key_format(self):
        course_id = uuid.UUID("12345678-1234-1234-1234-123456789012")
        doc_id = uuid.UUID("abcdefab-abcd-abcd-abcd-abcdefabcdef")
        key = build_r2_key(course_id, doc_id, "lecture.pdf")
        assert key == "courses/12345678-1234-1234-1234-123456789012/documents/abcdefab-abcd-abcd-abcd-abcdefabcdef/lecture.pdf"


class TestUploadFile:
    @patch("app.services.storage.get_s3_client")
    def test_upload_calls_put_object(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        upload_file("test/key.pdf", b"content", "application/pdf")
        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "test/key.pdf"
        assert call_kwargs["Body"] == b"content"


class TestDownloadFile:
    @patch("app.services.storage.get_s3_client")
    def test_download_returns_bytes(self, mock_get_client):
        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_get_client.return_value = mock_client
        result = download_file("test/key.pdf")
        assert result == b"file content"


class TestDeleteFile:
    @patch("app.services.storage.get_s3_client")
    def test_delete_calls_delete_object(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        delete_file("test/key.pdf")
        mock_client.delete_object.assert_called_once()
