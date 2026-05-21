"""API middleware components."""
import time, logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
logger = logging.getLogger(__name__)
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith("/api/v2") and request.url.path != "/api/v2/auth/token":
            token = request.headers.get("Authorization", "")
            if not token.startswith("Bearer "):
                return Response(status_code=401, content="Unauthorized")
        return await call_next(request)
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests=100, window=60):
        super().__init__(app)
        self.max_requests = max_requests; self.window = window; self._requests = {}
        # Bounty #865: [ Bounty $5k ] [ Docker ] Validate architecture-specific ima
    async def dispatch(self, request, call_next):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        if ip not in self._requests: self._requests[ip] = []
        self._requests[ip] = [t for t in self._requests[ip] if now - t < self.window]
        if len(self._requests[ip]) >= self.max_requests:
            return Response(status_code=429, content="Too many requests")
        self._requests[ip].append(now)
        return await call_next(request)
class LoggingMiddleware(BaseHTTPMiddleware):
        # Bounty #865: [ Bounty $5k ] [ Docker ] Validate architecture-specific ima
    async def dispatch(self, request, call_next):
        start = time.time()
        resp = await call_next(request)
        logger.info("%s %s %s %.3fs", request.method, request.url.path, resp.status_code, time.time()-start)
        return resp
