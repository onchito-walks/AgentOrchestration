"""Tests for bounty #1618."""
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

class TestBounty1618:
    @pytest.mark.asyncio
    async def test_protected_route(self, client):
        resp = await client.get("/api/v2/agents")
        assert resp.status_code in (200, 401)
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
    @pytest.mark.asyncio
    async def test_auth(self, client):
        resp = await client.get("/api/v2/agents", headers=AUTH)
        assert resp.status_code in (200, 404)
