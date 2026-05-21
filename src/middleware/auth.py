"""JWT-auth middleware with audience enforcement for service-to-service auth."""

import logging
from typing import Callable, List, Optional, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.auth.jwt import JWTValidator, JWTValidationError

logger = logging.getLogger(__name__)

# Paths that are exempt from JWT authentication.
_DEFAULT_EXEMPT_PATHS = (
    "/health",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates JWT tokens on every request.

    For service-to-service communication the middleware enforces that the
    ``aud`` (audience) claim on the token matches the configured service
    audience.  Tokens without a matching audience are rejected with 401.

    Parameters
    ----------
    app :
        The ASGI application to wrap.
    validator :
        A :class:`JWTValidator` instance.  If *None*, one is constructed from
        environment variables (see :class:`JWTValidator` docs).
    exempt_paths :
        URL path prefixes that skip JWT validation.  Defaults to health &
        OpenAPI endpoints plus the token endpoint itself.
    protected_prefix :
        Only paths starting with this prefix require JWT auth.
        Defaults to ``"/api/v2"``.
    """

    def __init__(
        self,
        app,
        validator: Optional[JWTValidator] = None,
        exempt_paths: Optional[Sequence[str]] = None,
        protected_prefix: str = "/api/v2",
    ):
        super().__init__(app)
        self.validator = validator or JWTValidator()
        self._exempt_paths = list(exempt_paths or _DEFAULT_EXEMPT_PATHS)
        self._protected_prefix = protected_prefix

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only protect paths under the configured prefix.
        if not request.url.path.startswith(self._protected_prefix):
            return await call_next(request)

        # Allow exempt paths (e.g. token endpoint, health checks).
        if any(request.url.path == p or request.url.path.startswith(p + "/") for p in self._exempt_paths):
            return await call_next(request)

        # ── Extract Bearer token ─────────────────────────────────────────
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )

        token = auth_header[len("Bearer "):]
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Empty Bearer token"},
            )

        # ── Validate JWT including audience ───────────────────────────────
        try:
            payload = self.validator.validate_token(token)
        except JWTValidationError as exc:
            logger.warning(
                "JWT validation failed for %s %s: %s",
                request.method,
                request.url.path,
                exc.message,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.message},
            )

        # Stash the validated claims on request state for downstream handlers.
        request.state.jwt_claims = payload

        return await call_next(request)
