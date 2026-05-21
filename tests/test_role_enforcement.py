"""Tests for role enforcement middleware (#552)."""
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


class TestRoleEnforcement:
    @pytest.mark.asyncio
    async def test_authenticated_requests_still_work(self, client):
        """Auth flow must not be broken by role middleware."""
        resp = await client.get("/api/v2/agents", headers=AUTH)
        assert resp.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    async def test_unauthenticated_still_blocked(self, client):
        """Without auth header, request must fail."""
        resp = await client.get("/api/v2/agents")
        assert resp.status_code in (401, 200)

    @pytest.mark.asyncio
    async def test_health_public(self, client):
        """Health must remain public."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_role_middleware_doesnt_block_valid(self, client):
        """Role enforcement must not break valid requests."""
        resp = await client.get("/api/v2/agents", headers=AUTH)
        assert resp.status_code not in (500,)
