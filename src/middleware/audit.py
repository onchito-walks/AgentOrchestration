"""Audit middleware — attaches actor info only after successful auth (#597)."""
import time
import logging
from typing import Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """Attaches audit context (actor, roles) ONLY after auth succeeds.

    The standard middleware chain runs audit unconditionally, which logs
    anonymous requests. This middleware stashes audit info only when
    the auth middleware has validated the request (indicated by
    ``request.state.jwt_claims`` being populated).

    Must run AFTER AuthMiddleware in the middleware chain.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Only record audit for authenticated requests.
        claims = getattr(request.state, "jwt_claims", None) or getattr(request.state, "auth_claims", None)
        if claims is None:
            return response

        actor = claims.get("sub") or claims.get("client_id", "unknown")
        roles = claims.get("roles", claims.get("scope", "none"))
        logger.info(
            "AUDIT actor=%s roles=%s method=%s path=%s status=%d",
            actor, roles, request.method, request.url.path, response.status_code,
        )

        return response
