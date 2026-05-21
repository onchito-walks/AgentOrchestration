"""Tests for token revocation detection on long-poll endpoints (#625)."""

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.server import create_app
from src.api.middleware import revocation


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def transport(app):
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport):
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    revocation.clear()


AUTH_HEADER = {"Authorization": "Bearer test-token-123"}


class TestTokenRevalidation:
    """Verify that long-poll / monitor endpoints check revocation."""

    @pytest.mark.asyncio
    async def test_normal_endpoint_does_not_check_revocation(self, client):
        """Regular API endpoints should not be affected by revocation."""
        # Revoke a fingerprint that won't match test-token-123
        revocation.revoke("nonexistent-fingerprint")
        resp = await client.get("/api/v2/agents", headers=AUTH_HEADER)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_monitor_endpoint_rejects_revoked_token(self, client):
        """A monitor endpoint must return 401 when the token is revoked."""
        # Pre-compute the fingerprint for "test-token-123"
        import hashlib
        fp = hashlib.sha256(b"test-token-123").hexdigest()[:16]
        revocation.revoke(fp)
        resp = await client.get("/api/v2/tasks/monitor", headers=AUTH_HEADER)
        assert resp.status_code == 401
        assert "revoked" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_monitor_endpoint_allows_valid_token(self, client):
        """A monitor path must succeed with a valid (non-revoked) token.
        
        We test a sub-path that contains the word 'monitor' but falls
        through to the agent list handler.
        """
        resp = await client.get("/api/v2/monitor/agents", headers=AUTH_HEADER)
        # This path triggers the revocation check but has no route handler;
        # we just verify it's not a 401 from revocation.
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_poll_endpoint_rejects_revoked_token(self, client):
        """A poll endpoint must also check revocation."""
        import hashlib
        fp = hashlib.sha256(b"test-token-123").hexdigest()[:16]
        revocation.revoke(fp)
        resp = await client.get("/api/v2/agents/poll", headers=AUTH_HEADER)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_poll_endpoint_allows_valid_token(self, client):
        """A poll path must succeed with a valid token."""
        resp = await client.get("/api/v2/agents/poll", headers=AUTH_HEADER)
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_clear_revocation_resets_check(self, client):
        """After clearing revocation, a previously revoked token should not be rejected by revocation logic."""
        import hashlib
        fp = hashlib.sha256(b"test-token-123").hexdigest()[:16]
        revocation.revoke(fp)
        resp = await client.get("/api/v2/tasks/monitor", headers=AUTH_HEADER)
        assert resp.status_code == 401
        revocation.clear()
        resp = await client.get("/api/v2/tasks/monitor", headers=AUTH_HEADER)
        # After clear, the revocation check passes (route may 404, but not 401 from revocation)
        assert resp.status_code != 401
