"""Path normalization middleware to prevent trailing-slash auth bypass (#1000)."""
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class PathNormalizationMiddleware(BaseHTTPMiddleware):
    """Strips trailing slashes from request paths before downstream
    middleware (auth, rate limiting) runs.

    This prevents auth bypass via trailing-slash redirect: without
    normalisation, ``/api/v2/agents/`` does not match
    ``startswith("/api/v2")`` in AuthMiddleware, bypassing auth.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only normalise API paths under the protected prefix.
        path = request.url.path
        if path.startswith(("/api/", "/health")) and len(path) > 1 and path.endswith("/"):
            # Reconstruct URL with normalised path.
            new_url = str(request.url).rstrip("/")
            scope = dict(request.scope)
            scope["path"] = path.rstrip("/")
            scope["raw_path"] = path.rstrip("/").encode()
            scope["root_path"] = scope.get("root_path", "").rstrip("/")
            # Build a new request from the modified scope.
            from starlette.requests import Request as NewRequest
            modified_request = NewRequest(scope)
            modified_request.state = request.state
            return await call_next(modified_request)

        return await call_next(request)
