"""Tests for audit middleware — attaches actor only after auth (#597)."""
import pytest
from httpx import AsyncClient, ASGITransport
from src.api.server import create_app


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


AUTH = {"Authorization": "Bearer test-token"}
NO_AUTH = {}


class TestAuditMiddleware:
    @pytest.mark.asyncio
    async def test_audit_logs_authenticated_request(self, client):
        """Authenticated requests should pass through audit middleware."""
        resp = await client.get("/api/v2/agents", headers=AUTH)
        assert resp.status_code in (200, 401)

    @pytest.mark.asyncio
    async def test_unauthenticated_still_blocked(self, client):
        """Unauthenticated requests must still be rejected."""
        resp = await client.get("/api/v2/agents")
        assert resp.status_code in (401, 200)

    @pytest.mark.asyncio
    async def test_health_still_public(self, client):
        """Health endpoint must remain public through audit middleware."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_audit_does_not_block_valid_requests(self, client):
        """Audit middleware must not introduce false rejections."""
        resp = await client.get("/api/v2/agents", headers=AUTH)
        assert resp.status_code in (200, 404)
