"""JWT validation with audience enforcement."""
import os, time, logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JWTValidationError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class JWTValidator:
    """Validates JWT tokens with audience enforcement."""
    
    def __init__(self, secret: Optional[str] = None, audiences: Optional[List[str]] = None):
        import jwt as pyjwt
        self._jwt = pyjwt
        self._secret = secret or os.getenv("AO_JWT_SECRET", "dev-secret")
        self._audiences = audiences or ["agent-orchestrator"]
        self._algorithms = (os.getenv("AO_JWT_ALGORITHM", "HS256")).split(",")
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT and enforce audience claim."""
        try:
            payload = self._jwt.decode(
                token,
                self._secret,
                algorithms=self._algorithms,
                options={"require": ["exp", "aud"], "verify_exp": True, "verify_aud": False},
                leeway=30,
            )
        except Exception as exc:
            raise JWTValidationError(f"Token validation failed: {exc}")
        
        # Audience enforcement
        aud = payload.get("aud")
        if aud is None:
            raise JWTValidationError("Token missing required 'aud' claim")
        token_auds = {aud} if isinstance(aud, str) else set(aud)
        allowed = set(self._audiences)
        if not (token_auds & allowed):
            raise JWTValidationError(f"Token audience {token_auds} does not match allowed {allowed}")
        
        return payload
