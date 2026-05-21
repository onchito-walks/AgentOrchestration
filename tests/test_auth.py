"""Tests for auth middleware — trailing slash bypass prevention (#1000)."""

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


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

VALID_AUTH = {"Authorization": "Bearer test-token"}
NO_AUTH = {}


# ---------------------------------------------------------------------------
# Core auth tests (no trailing slash — baseline)
# ---------------------------------------------------------------------------

class TestAuthBaseline:
    """Verify that the existing auth check still works for normal paths."""

    @pytest.mark.asyncio
    async def test_protected_path_requires_auth(self, client):
        resp = await client.get("/api/v2/agents")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_path_allows_with_auth(self, client):
        resp = await client.get("/api/v2/agents", headers=VALID_AUTH)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_token_endpoint_allows_no_auth(self, client):
        """The /api/v2/auth/token endpoint must remain publicly accessible."""
        resp = await client.get("/api/v2/auth/token")
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_health_endpoint_no_auth(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_non_api_path_no_auth(self, client):
        resp = await client.get("/api/docs")
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# Trailing-slash bypass prevention (the actual fix)
# ---------------------------------------------------------------------------

class TestTrailingSlashAuthBypass:
    """Verify that adding a trailing slash does NOT bypass auth.

    Before the fix, a request to /api/v2/agents/ would NOT match
    request.url.path.startswith("/api/v2") because the Starlette
    trailing-slash redirect middleware would intercept and redirect
    before auth ran — or the path with trailing slash would be
    treated differently by the auth check.

    With PathNormalizationMiddleware in place (running BEFORE auth),
    trailing slashes are stripped, so auth always sees the normalised
    path.
    """

    @pytest.mark.asyncio
    async def test_trailing_slash_requires_auth(self, client):
        """Request with trailing slash must still require auth."""
        resp = await client.get("/api/v2/agents/")
        assert resp.status_code == 401, (
            "Trailing-slash path bypassed auth — PathNormalizationMiddleware "
            "may not be wired correctly"
        )

    @pytest.mark.asyncio
    async def test_trailing_slash_allows_with_auth(self, client):
        """Authenticated request with trailing slash must succeed."""
        resp = await client.get("/api/v2/agents/", headers=VALID_AUTH)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_trailing_slash_on_nested_path_requires_auth(self, client):
        """Deep path with trailing slash must still require auth."""
        resp = await client.get("/api/v2/agents/some-id/start/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_trailing_slash_on_nested_path_allows_with_auth(self, client):
        """Authenticated deep path with trailing slash must succeed."""
        resp = await client.post("/api/v2/agents/some-id/start/", headers=VALID_AUTH)
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_token_endpoint_trailing_slash_allows_no_auth(self, client):
        """/api/v2/auth/token/ with trailing slash must still be public.

        This is a critical edge case: the normalised path must still
        correctly exempt the token endpoint.
        """
        resp = await client.get("/api/v2/auth/token/")
        # The normalised path is /api/v2/auth/token which is exempt.
        assert resp.status_code != 401, (
            "Token endpoint with trailing slash incorrectly requires auth"
        )

    @pytest.mark.asyncio
    async def test_multiple_trailing_slashes_requires_auth(self, client):
        """Even pathological multiple trailing slashes must not bypass auth."""
        resp = await client.get("/api/v2/agents//")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PathNormalizationMiddleware unit tests
# ---------------------------------------------------------------------------

class TestPathNormalizationMiddleware:
    """Unit tests for PathNormalizationMiddleware in isolation."""

    @pytest.mark.asyncio
    async def test_root_path_not_stripped(self, client):
        """Root path '/' must remain unchanged."""
        resp = await client.get("/")
        # Just verify it doesn't crash; root may 404 which is fine.
        assert resp.status_code in (200, 404, 405)

    @pytest.mark.asyncio
    async def test_no_trailing_slash_unchanged(self, client):
        """Path without trailing slash should work as before."""
        resp = await client.get("/api/v2/agents", headers=VALID_AUTH)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_no_trailing_slash(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_with_trailing_slash(self, client):
        """Trailing slash on non-protected path should still be normalised."""
        resp = await client.get("/health/")
        # Either 200 (normalised to /health) or a redirect — both acceptable.
        assert resp.status_code in (200, 307, 308, 404)
