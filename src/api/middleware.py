"""API middleware components.

#625: AuthMiddleware now validates every request against the central auth
service. Stale, revoked, disabled, and expired credentials are rejected
before any protected action is performed. Both browser (cookie/session)
and token (Bearer) clients are covered.
"""

import time
import logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .auth_service import auth_store

logger = logging.getLogger(__name__)

# Routes that do not require authentication
PUBLIC_ROUTES = frozenset({
    "/api/v2/auth/token",
    "/api/v2/auth/session",
    "/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
})


def _extract_bearer_token(request: Request) -> str | None:
    """Extract a Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _extract_session_token(request: Request) -> str | None:
    """Extract a session token from the ``x-session-token`` header or
    ``session`` cookie."""
    token = request.headers.get("x-session-token")
    if token:
        return token
    cookies = request.cookies
    return cookies.get("session")


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates authentication on every protected request.

    Two auth modes supported:
      1. Bearer token — API / SDK clients via ``Authorization: Bearer <key>``
      2. Session token — browser clients via ``x-session-token`` header or
         ``session`` cookie

    Public routes (auth token issue, health, docs) are exempt. All other
    ``/api/v2/*`` routes require valid, non-revoked, non-expired credentials.

    This middleware is the enforcement layer. Every protected request —
    including each tick of a long-poll connection — is checked afresh.
    """

    def __init__(self, app):
        super().__init__(app)
        self._protected_prefixes = ("/api/v2",)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Let public routes through without auth
        if path in PUBLIC_ROUTES:
            return await call_next(request)

        # Only protect /api/v2/* paths
        if not any(path.startswith(p) for p in self._protected_prefixes):
            return await call_next(request)

        # ── Try Bearer token first ───────────────────────────────────
        bearer_token = _extract_bearer_token(request)
        if bearer_token:
            is_valid, reason, entry = auth_store.validate_key(bearer_token)
            if is_valid:
                # Attach resolved identity to request state so downstream
                # handlers can inspect it
                request.state.user = entry["owner"]
                request.state.scopes = entry["scopes"]
                request.state.auth_method = "bearer"
                return await call_next(request)
            else:
                logger.warning(
                    "Auth rejected for %s: %s (path=%s)",
                    request.client.host if request.client else "unknown",
                    reason,
                    path,
                )
                return Response(
                    status_code=401,
                    content=f'{{"error":"{reason}","message":"Authentication failed — key is {reason.replace(chr(95), " ")}"}}',
                    media_type="application/json",
                )

        # ── Try session token (browser clients) ──────────────────────
        session_token = _extract_session_token(request)
        if session_token:
            is_valid, reason, session = auth_store.validate_session(session_token)
            if is_valid:
                request.state.user = session["owner"]
                request.state.scopes = session["scopes"]
                request.state.auth_method = "session"
                return await call_next(request)
            else:
                logger.warning(
                    "Session rejected for %s: %s (path=%s)",
                    request.client.host if request.client else "unknown",
                    reason,
                    path,
                )
                return Response(
                    status_code=401,
                    content=f'{{"error":"{reason}","message":"Session auth failed — {reason.replace(chr(95), " ")}"}}',
                    media_type="application/json",
                )

        # ── No credentials provided ──────────────────────────────────
        return Response(
            status_code=401,
            content=(
                '{"error":"missing_credentials","message":"Authentication required — '
                'provide a Bearer token via Authorization header or a session token '
                'via x-session-token header or session cookie"}'
            ),
            media_type="application/json",
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self._requests = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        if client_ip not in self._requests:
            self._requests[client_ip] = []

        self._requests[client_ip] = [t for t in self._requests[client_ip] if now - t < self.window]

        if len(self._requests[client_ip]) >= self.max_requests:
            return Response(status_code=429, content="Too many requests")

        self._requests[client_ip].append(now)
        return await call_next(request)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s")
        return response
