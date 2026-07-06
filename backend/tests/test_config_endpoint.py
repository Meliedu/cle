import pytest


@pytest.mark.asyncio
async def test_config_returns_pilot_profile(async_client, logged_in_user):
    resp = await async_client.get("/api/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["id"] == "cle"
    assert data["confidence_scale"]["min"] == -2
    assert "terminology" in data and "skill_taxonomy" in data


@pytest.mark.asyncio
async def test_config_requires_auth(client):
    resp = await client.get("/api/config")
    assert resp.status_code in (401, 403)
