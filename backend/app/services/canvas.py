"""Canvas LMS API client for course file integration.

Canvas REST API docs: https://canvas.instructure.com/doc/api/
Key endpoints:
- GET /api/v1/courses/:course_id/files — list course files
- GET /api/v1/courses/:course_id/modules — list modules
- GET /api/v1/courses/:course_id/assignments — list assignments
- GET /api/v1/files/:file_id — get file metadata + download URL
"""

import httpx


class CanvasClient:
    """Async client for Canvas LMS REST API."""

    def __init__(self, base_url: str, access_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def list_course_files(
        self, canvas_course_id: str, page: int = 1, per_page: int = 50
    ) -> list[dict]:
        """List files in a Canvas course."""
        response = await self._client.get(
            f"/courses/{canvas_course_id}/files",
            params={"page": page, "per_page": per_page},
        )
        response.raise_for_status()
        return response.json()

    async def get_file(self, file_id: str) -> dict:
        """Get file metadata including download URL."""
        response = await self._client.get(f"/files/{file_id}")
        response.raise_for_status()
        return response.json()

    async def download_file(self, download_url: str) -> bytes:
        """Download a file from Canvas using its download URL."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(download_url)
            response.raise_for_status()
            return response.content

    async def list_modules(self, canvas_course_id: str) -> list[dict]:
        """List modules in a Canvas course."""
        response = await self._client.get(
            f"/courses/{canvas_course_id}/modules"
        )
        response.raise_for_status()
        return response.json()

    async def list_module_items(
        self, canvas_course_id: str, module_id: str
    ) -> list[dict]:
        """List items within a Canvas module."""
        response = await self._client.get(
            f"/courses/{canvas_course_id}/modules/{module_id}/items"
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
