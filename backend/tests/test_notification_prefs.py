import pytest


@pytest.mark.asyncio
async def test_patch_notification_prefs_roundtrip(async_client, logged_in_user):
    payload = {"checkpoint_published": True, "report_ready": True, "follow_up_assigned": False}
    resp = await async_client.patch(
        "/api/auth/me/preferences", json={"notification_prefs": payload}
    )
    assert resp.status_code == 200
    me = await async_client.get("/api/auth/me")
    body = me.json()["data"]
    # PATCH merges over defaults: submitted keys take the submitted values
    for key, value in payload.items():
        assert body["notification_prefs"][key] == value


@pytest.mark.asyncio
async def test_patch_rejects_unknown_keys(async_client, logged_in_user):
    resp = await async_client.patch(
        "/api/auth/me/preferences", json={"notification_prefs": {"evil_key": True}}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_requires_auth(client):
    resp = await client.patch(
        "/api/auth/me/preferences", json={"notification_prefs": {"report_ready": True}}
    )
    assert resp.status_code in (401, 403)
