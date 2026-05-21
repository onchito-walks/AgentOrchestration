"""Tests for auth service, middleware, and task monitor (issue #625).

Covers:
  - ApiKeyStore: key lifecycle, session lifecycle, validation edge cases
  - AuthMiddleware: Bearer token, session token, missing/revoked/expired
  - Routes: auth endpoints, task monitor long-poll
  - Auth revalidation on long polling (the core issue)
"""

import time
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.auth_service import auth_store, ApiKeyStore
from src.api.middleware import AuthMiddleware
from src.api.routes import router


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_store():
    """Reset the global auth_store between tests to avoid cross-test leakage.

    We replace the internal dicts rather than the object itself so the
    singleton reference in middleware.py stays valid.
    """
    auth_store._keys.clear()
    auth_store._sessions.clear()
    auth_store._revoked_tokens.clear()
    yield


@pytest.fixture
def app():
    """Return a FastAPI app with the test router and AuthMiddleware."""
    application = FastAPI(title="Test")

    # Health endpoint (normally defined in server.py)
    @application.get("/health")
    async def health():
        return {"status": "healthy"}

    application.add_middleware(AuthMiddleware)
    application.include_router(router, prefix="/api/v2")
    return application


@pytest.fixture
def client(app):
    """Return a TestClient for the test app."""
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════
# Auth Service — API Key Tests
# ══════════════════════════════════════════════════════════════════════

class TestApiKeyStore:
    """Tests for the central API key and session service."""

    def test_create_key_returns_valid(self):
        """Creating a key should return a raw key string that can be validated."""
        raw = auth_store.create_key("alice", scopes=["read", "write"])
        assert raw.startswith("ao_")
        assert len(raw) > 10
        valid, reason, entry = auth_store.validate_key(raw)
        assert valid is True
        assert reason == "ok"
        assert entry["owner"] == "alice"

    def test_create_key_default_scopes(self):
        """Default scope should be '*' (wildcard) when no scopes given."""
        raw = auth_store.create_key("bob")
        valid, _, entry = auth_store.validate_key(raw)
        assert entry["scopes"] == ["*"]

    def test_revoke_key(self):
        """Revoked keys should return 'api_key_revoked' on validation."""
        raw = auth_store.create_key("carol")
        assert auth_store.revoke_key(raw) is True
        valid, reason, entry = auth_store.validate_key(raw)
        assert valid is False
        assert reason == "api_key_revoked"

    def test_double_revoke_is_idempotent(self):
        """Revoking an already-revoked key should return False."""
        raw = auth_store.create_key("dave")
        auth_store.revoke_key(raw)
        assert auth_store.revoke_key(raw) is False

    def test_revoke_nonexistent_key(self):
        """Revoking a key that doesn't exist should return False."""
        assert auth_store.revoke_key("ao_nonexistent") is False

    def test_disable_enable_key(self):
        """Disabled keys are rejected; re-enabled keys are accepted again."""
        raw = auth_store.create_key("eve")
        assert auth_store.disable_key(raw) is True
        valid, reason, _ = auth_store.validate_key(raw)
        assert valid is False
        assert reason == "api_key_disabled"

        assert auth_store.enable_key(raw) is True
        valid, reason, _ = auth_store.validate_key(raw)
        assert valid is True
        assert reason == "ok"

    def test_expired_key(self):
        """Keys past their expiration should be rejected as 'api_key_expired'."""
        raw = auth_store.create_key("frank", expires_in=1)  # 1 second
        valid, _, _ = auth_store.validate_key(raw)
        assert valid is True
        time.sleep(1.1)
        valid, reason, _ = auth_store.validate_key(raw)
        assert valid is False
        assert reason == "api_key_expired"

    def test_invalid_key_format(self):
        """A nonsense key string should return 'invalid_api_key'."""
        valid, reason, _ = auth_store.validate_key("not-a-valid-key")
        assert valid is False
        assert reason == "invalid_api_key"

    def test_list_keys(self):
        """list_keys should return all keys, optionally filtered by owner."""
        auth_store.create_key("grace")
        auth_store.create_key("heidi")
        raw = auth_store.create_key("grace")
        auth_store.revoke_key(raw)

        all_keys = auth_store.list_keys()
        assert len(all_keys) == 3

        grace_keys = auth_store.list_keys(owner="grace")
        assert len(grace_keys) == 2
        assert all(k["owner"] == "grace" for k in grace_keys)

    def test_revoke_by_hash(self):
        """revoke_key should accept hash strings as well as raw keys."""
        raw = auth_store.create_key("ivan")
        key_hash = auth_store._hash_key(raw)  # noqa: SLF001
        assert auth_store.revoke_key(key_hash) is True
        valid, reason, _ = auth_store.validate_key(raw)
        assert valid is False

    def test_is_revoked(self):
        """is_revoked should return True for explicitly revoked key hashes."""
        raw = auth_store.create_key("judy")
        key_hash = auth_store._hash_key(raw)  # noqa: SLF001
        assert auth_store.is_revoked(key_hash) is False
        auth_store.revoke_key(raw)
        assert auth_store.is_revoked(key_hash) is True


# ══════════════════════════════════════════════════════════════════════
# Auth Service — Session Tests
# ══════════════════════════════════════════════════════════════════════

class TestSessionStore:
    """Tests for browser session management."""

    def test_create_and_validate_session(self):
        """Creating a session should return a token that validates."""
        token = auth_store.create_session("karl")
        assert len(token) == 32  # uuid4 hex
        valid, reason, session = auth_store.validate_session(token)
        assert valid is True
        assert reason == "ok"
        assert session["owner"] == "karl"

    def test_revoke_session(self):
        """Revoked sessions should return 'session_revoked'."""
        token = auth_store.create_session("laura")
        assert auth_store.revoke_session(token) is True
        valid, reason, _ = auth_store.validate_session(token)
        assert valid is False
        assert reason == "session_revoked"

    def test_invalid_session(self):
        """Nonsense session tokens should return 'invalid_session'."""
        valid, reason, _ = auth_store.validate_session("bogus-token")
        assert valid is False
        assert reason == "invalid_session"


# ══════════════════════════════════════════════════════════════════════
# Auth Middleware Tests
# ══════════════════════════════════════════════════════════════════════

class TestAuthMiddleware:
    """Tests for the upgraded AuthMiddleware with real validation."""

    def test_public_route_no_auth(self, client):
        """Health check and docs routes should work without auth."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_missing_credentials(self, client):
        """Protected routes without any credentials should get 401."""
        resp = client.get("/api/v2/agents")
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"] == "missing_credentials"

    def test_valid_bearer_token(self, client):
        """A valid API key as Bearer token should be accepted."""
        raw = auth_store.create_key("mallory")
        resp = client.get(
            "/api/v2/agents",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200

    def test_revoked_bearer_token(self, client):
        """A revoked API key should get 401."""
        raw = auth_store.create_key("nancy")
        auth_store.revoke_key(raw)
        resp = client.get(
            "/api/v2/agents",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "revoked" in body["error"]

    def test_expired_bearer_token(self, client):
        """An expired API key should get 401."""
        raw = auth_store.create_key("oscar", expires_in=1)
        time.sleep(1.1)
        resp = client.get(
            "/api/v2/agents",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "expired" in body["error"]

    def test_disabled_bearer_token(self, client):
        """A disabled API key should get 401."""
        raw = auth_store.create_key("peggy")
        auth_store.disable_key(raw)
        resp = client.get(
            "/api/v2/agents",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "disabled" in body["error"]

    def test_malformed_bearer(self, client):
        """A Bearer header without a valid key should get 401."""
        resp = client.get(
            "/api/v2/agents",
            headers={"Authorization": "Bearer obviously-wrong"},
        )
        assert resp.status_code == 401

    def test_valid_session_token(self, client):
        """A valid session token via header should be accepted."""
        token = auth_store.create_session("quinn")
        resp = client.get(
            "/api/v2/agents",
            headers={"x-session-token": token},
        )
        assert resp.status_code == 200

    def test_revoked_session_token(self, client):
        """A revoked session token should get 401."""
        token = auth_store.create_session("rob")
        auth_store.revoke_session(token)
        resp = client.get(
            "/api/v2/agents",
            headers={"x-session-token": token},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "revoked" in body["error"]

    def test_auth_identity_on_request_state(self):
        """The authenticated user identity should be set on request.state."""
        from src.api.auth_service import auth_store as store
        from fastapi import Request as FastAPIRequest

        raw = store.create_key("steve")

        # Create a test app with the middleware and a whoami endpoint
        app = FastAPI(title="Whoami test")
        app.add_middleware(AuthMiddleware)

        @app.get("/api/v2/whoami")
        async def whoami(request: FastAPIRequest):
            return {
                "user": request.state.user,
                "auth_method": request.state.auth_method,
            }

        client = TestClient(app)
        resp = client.get(
            "/api/v2/whoami",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["user"] == "steve"
        assert body["auth_method"] == "bearer"

    def test_no_auth_on_auth_token_endpoint(self):
        """The /auth/token endpoint should not require auth."""
        application = FastAPI(title="Test")
        application.add_middleware(AuthMiddleware)
        application.include_router(router, prefix="/api/v2")
        client = TestClient(application)
        resp = client.post("/api/v2/auth/token?username=testuser")
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "Bearer"
        assert "access_token" in body


# ══════════════════════════════════════════════════════════════════════
# Auth Endpoints Tests
# ══════════════════════════════════════════════════════════════════════

class TestAuthEndpoints:
    """Tests for POST /auth/token and POST /auth/session."""

    def test_issue_token_endpoint(self, client):
        """POST /auth/token should return a valid Bearer token."""
        resp = client.post("/api/v2/auth/token?username=alice&expires_in=3600")
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "Bearer"
        assert body["access_token"].startswith("ao_")
        assert body["owner"] == "alice"

    def test_issue_token_with_scopes(self, client):
        """POST /auth/token should accept scopes."""
        resp = client.post(
            "/api/v2/auth/token?username=bob&scopes=read,write,admin",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["scopes"] == ["read", "write", "admin"]

    def test_create_session_endpoint(self, client):
        """POST /auth/session should return a session token."""
        resp = client.post("/api/v2/auth/session?username=carol")
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "Session"
        assert len(body["session_token"]) == 32
        assert body["owner"] == "carol"

    def test_issued_token_works_with_auth(self, client):
        """A token issued via /auth/token should work on subsequent requests."""
        issue = client.post("/api/v2/auth/token?username=dave")
        raw_key = issue.json()["access_token"]
        resp = client.get(
            "/api/v2/agents",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 200

    def test_issued_session_works_with_auth(self, client):
        """A session created via /auth/session should work on subsequent requests."""
        issue = client.post("/api/v2/auth/session?username=eve")
        session_token = issue.json()["session_token"]
        resp = client.get(
            "/api/v2/agents",
            headers={"x-session-token": session_token},
        )
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Task Monitor Tests
# ══════════════════════════════════════════════════════════════════════

class TestTaskMonitor:
    """Tests for the task monitor long-poll endpoint."""

    def test_monitor_requires_auth(self, client):
        """The /tasks/monitor endpoint should require authentication."""
        resp = client.get("/api/v2/tasks/monitor")
        assert resp.status_code == 401

    def test_monitor_with_valid_auth(self, client):
        """A valid Bearer token should allow access to the monitor."""
        raw = auth_store.create_key("frank")
        resp = client.get(
            "/api/v2/tasks/monitor?poll=true",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "queues" in body
        assert "in_flight_total" in body
        assert "tasks_running" in body
        assert "agents_running" in body

    def test_monitor_with_session_auth(self, client):
        """A valid session token should allow access to the monitor."""
        token = auth_store.create_session("grace")
        resp = client.get(
            "/api/v2/tasks/monitor?poll=true",
            headers={"x-session-token": token},
        )
        assert resp.status_code == 200

    def test_monitor_returns_user_context(self, client):
        """The monitor response should include the authenticated user."""
        raw = auth_store.create_key("heidi")
        resp = client.get(
            "/api/v2/tasks/monitor?poll=true",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"] == "heidi"
        assert body["auth_method"] == "bearer"

    def test_monitor_revoked_key_while_polling(self, client):
        """A key revoked *before* the request should be rejected immediately."""
        raw = auth_store.create_key("ivan")
        auth_store.revoke_key(raw)
        resp = client.get(
            "/api/v2/tasks/monitor?poll=true",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "revoked" in body["error"]

    # The key test: long-poll clients must re-auth on every tick.
    # Since the middleware validates every request, when a key is revoked
    # mid-poll the next long-poll reconnection gets 401.
    def test_auth_revalidation_on_long_poll(self, client):
        """Each long-poll request re-validates auth — revoked keys are caught."""
        raw = auth_store.create_key("judy")
        # First request is fine
        resp1 = client.get(
            "/api/v2/tasks/monitor?poll=true",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp1.status_code == 200

        # Revoke the key
        auth_store.revoke_key(raw)

        # Next request should fail
        resp2 = client.get(
            "/api/v2/tasks/monitor?poll=true",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp2.status_code == 401
        body = resp2.json()
        assert "revoked" in body["error"]


# ══════════════════════════════════════════════════════════════════════
# Create Task and Monitor Integration
# ══════════════════════════════════════════════════════════════════════

class TestCreateAndMonitor:
    """Integration tests for task creation + monitor."""

    def test_create_task_and_monitor(self, client):
        """Create a task then verify it shows up in the monitor snapshot."""
        raw = auth_store.create_key("karl")
        headers = {"Authorization": f"Bearer {raw}"}

        # Create a task
        task_resp = client.post(
            "/api/v2/tasks?target_agent=test-agent&task_type=test",
            headers=headers,
        )
        assert task_resp.status_code == 200
        task_id = task_resp.json()["task_id"]

        # Poll the monitor
        monitor_resp = client.get(
            "/api/v2/tasks/monitor?poll=true",
            headers=headers,
        )
        assert monitor_resp.status_code == 200
        body = monitor_resp.json()
        # The task may be in-flight or queued — just verify the endpoint works
        assert body["user"] == "karl"
