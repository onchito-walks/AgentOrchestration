"""Role-based access control middleware (#552) enforces tenant role checks."""

from typing import Callable, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Mapping of allowed roles per resource prefix
_ROLE_ACCESS: dict = {
    "/api/v2/agents": {"admin", "operator", "viewer"},
    "/api/v2/tasks": {"admin", "operator"},
    "/api/v2/runs": {"admin", "operator"},
    "/api/v2/config": {"admin"},
    "/api/v2/deploy": {"admin"},
    "/api/v2/secrets": {"admin"},
    "/api/v2/tenants": {"admin"},
}

DEFAULT_ROLE = "viewer"
DEFAULT_PATH_ROLES = {"viewer"}


class RoleEnforcementMiddleware(BaseHTTPMiddleware):
    """Enforces that the authenticated actor has the required role
    for the requested resource path.

    Expects ``request.state.auth_claims`` or ``request.state.jwt_claims``
    to contain a ``roles`` (list) or ``role`` (str) field, set by the
    auth middleware that ran before this.

    Must run AFTER AuthMiddleware.
    """

    def __init__(self, app, role_map: Optional[dict] = None):
        super().__init__(app)
        self._role_map = role_map or _ROLE_ACCESS

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        claims = getattr(request.state, "auth_claims", None) or getattr(request.state, "jwt_claims", None)

        # If there are no claims (unauthenticated), let auth handle rejection.
        if claims is None:
            return await call_next(request)

        # Extract roles from claims (supports "role" string, "roles" list, "scope" space-separated)
        raw_roles: List[str] = []
        if isinstance(claims.get("roles"), list):
            raw_roles = claims["roles"]
        elif claims.get("role"):
            raw_roles = [claims["role"]]
        elif claims.get("scope"):
            raw_roles = claims["scope"].split()

        user_roles = set(raw_roles) if raw_roles else {DEFAULT_ROLE}

        # Find the required roles for this path
        path = request.url.path
        required = DEFAULT_PATH_ROLES
        for prefix, allowed_roles in self._role_map.items():
            if path.startswith(prefix):
                required = allowed_roles
                break

        if not user_roles.intersection(required):
            return Response(
                status_code=403,
                content=f"Forbidden: user roles {user_roles} do not grant access to {path}",
            )

        return await call_next(request)
