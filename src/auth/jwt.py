"""JWT token validation with audience enforcement for service-to-service auth."""

import os
import time
import logging
from typing import Any, Dict, List, Optional, Sequence

import jwt

logger = logging.getLogger(__name__)

DEFAULT_ALGORITHM = "HS256"
DEFAULT_CLOCK_SKEW_SECONDS = 30
DEFAULT_SERVICE_AUDIENCE = "agent-orchestrator"


class JWTValidationError(Exception):
    """Raised when a JWT token fails validation."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class JWTValidator:
    """Validates JWT tokens with audience enforcement for inter-service communication.

    For service-to-service auth, every token must carry an ``aud`` claim that
    matches at least one of the configured allowed audiences.  Tokens without
    an audience, or with a mismatched audience, are rejected outright.

    Configuration is sourced from environment variables with sensible defaults:

    * ``AO_JWT_SECRET``       – HMAC shared secret (required for HS256/HS384/HS512).
    * ``AO_JWT_PUBLIC_KEY``   – PEM-encoded public key (for RS* / ES* algorithms).
                               Falls back to ``AO_JWT_SECRET`` for symmetric ciphers.
    * ``AO_JWT_ALGORITHM``    – Algorithm list (default ``["HS256"]``).
    * ``AO_JWT_AUDIENCES``    – Comma-separated list of accepted ``aud`` values.
                               Default ``["agent-orchestrator"]``.
    * ``AO_JWT_ISSUER``       – Expected ``iss`` value (optional).
    * ``AO_JWT_CLOCK_SKEW``   – Allowed clock skew in seconds (default 30).
    """

    def __init__(
        self,
        secret: Optional[str] = None,
        public_key: Optional[str] = None,
        algorithms: Optional[List[str]] = None,
        audiences: Optional[List[str]] = None,
        issuer: Optional[str] = None,
        clock_skew: int = DEFAULT_CLOCK_SKEW_SECONDS,
    ):
        self._secret = secret or os.getenv("AO_JWT_SECRET", "")
        self._public_key = public_key or os.getenv("AO_JWT_PUBLIC_KEY", None)
        self._algorithms = algorithms or os.getenv(
            "AO_JWT_ALGORITHM", DEFAULT_ALGORITHM
        ).split(",")
        self._audiences = audiences or (
            os.getenv("AO_JWT_AUDIENCES", DEFAULT_SERVICE_AUDIENCE).split(",")
            if os.getenv("AO_JWT_AUDIENCES")
            else [DEFAULT_SERVICE_AUDIENCE]
        )
        self._issuer = issuer or os.getenv("AO_JWT_ISSUER", None)
        self._clock_skew = clock_skew or int(
            os.getenv("AO_JWT_CLOCK_SKEW", str(DEFAULT_CLOCK_SKEW_SECONDS))
        )

    @property
    def _decode_key(self) -> str:
        """Return the key material appropriate for the configured algorithm."""
        # For asymmetric algorithms (RS*, ES*), prefer the public key.
        if any(a.startswith(("RS", "ES", "PS")) for a in self._algorithms):
            if self._public_key:
                return self._public_key
            raise JWTValidationError(
                "Asymmetric algorithm configured but no public key provided",
                status_code=500,
            )
        # Symmetric algorithms use the shared secret.
        if not self._secret:
            raise JWTValidationError(
                "JWT secret not configured; set AO_JWT_SECRET",
                status_code=500,
            )
        return self._secret

    @property
    def audiences(self) -> List[str]:
        """Return the list of accepted audience values."""
        return list(self._audiences)

    def validate_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate a JWT token.

        Enforces:
        1. Valid signature against the configured key.
        2. ``exp`` / ``nbf`` time claims (with configured clock skew).
        3. ``aud`` claim must match at least one of the allowed audiences.
        4. ``iss`` claim, if configured, must match.

        Returns the decoded payload dict on success.

        Raises:
            JWTValidationError: On any validation failure.
        """
        try:
            options = {
                "require": ["exp", "aud"],
                "verify_exp": True,
                "verify_aud": False,  # We verify audience ourselves for control.
                "verify_iat": True,
                "verify_nbf": True,
            }

            payload = jwt.decode(
                token,
                self._decode_key,
                algorithms=self._algorithms,
                options=options,
                issuer=self._issuer,
                leeway=self._clock_skew,
            )
        except jwt.ExpiredSignatureError:
            raise JWTValidationError("Token has expired")
        except jwt.InvalidIssuerError:
            raise JWTValidationError("Invalid token issuer")
        except jwt.InvalidKeyError:
            raise JWTValidationError("Invalid signing key", status_code=500)
        except jwt.DecodeError as exc:
            raise JWTValidationError(f"Invalid token: {exc}")
        except jwt.InvalidTokenError as exc:
            raise JWTValidationError(f"Token validation failed: {exc}")

        # ── Audience enforcement ─────────────────────────────────────────
        # Every service-to-service token MUST carry an ``aud`` claim that
        # matches at least one of the values in ``self._audiences``.
        self._validate_audience(payload)

        return payload

    def _validate_audience(self, payload: Dict[str, Any]) -> None:
        """Verify that the token's audience matches at least one allowed value.

        The JWT spec allows ``aud`` to be either a string or a list of
        strings.  We normalise to a set and check for intersection with the
        configured allowed audiences.

        Raises:
            JWTValidationError: If the audience claim is missing or does not
                match any allowed value.
        """
        aud_claim = payload.get("aud")
        if aud_claim is None:
            raise JWTValidationError(
                "Token missing required 'aud' claim; "
                "audience is required for service-to-service authentication"
            )

        # Normalise to a set of strings.
        if isinstance(aud_claim, str):
            token_audiences = {aud_claim}
        elif isinstance(aud_claim, (list, tuple, set)):
            token_audiences = set(aud_claim)
        else:
            raise JWTValidationError(
                f"Invalid 'aud' claim type: {type(aud_claim).__name__}"
            )

        allowed = set(self._audiences)
        matched = token_audiences & allowed
        if not matched:
            raise JWTValidationError(
                f"Token audience {token_audiences} does not match "
                f"any allowed audience {allowed}"
            )

        logger.debug(
            "JWT audience validated: token_aud=%s matched=%s",
            token_audiences,
            matched,
        )
