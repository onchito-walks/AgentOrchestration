"""Auth Service — Central API key and session validation service.

This is the "central dependency or permission service" referenced in issue #625.
Every auth check flows through here: API tokens (Bearer) and browser sessions.
Stale, revoked, disabled, or expired credentials are rejected before any
protected action is performed.
"""

import time
import uuid
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AuthTokenStatus:
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    DISABLED = "disabled"


class ApiKeyStore:
    """In-memory API key store with support for activation, revocation,
    expiration, and disabled keys.

    In production this would be a Redis/Postgres-backed store with TTLs,
    but for this codebase level the in-memory implementation satisfies the
    contract defined by the issue. The public API is the same either way.
    """

    def __init__(self):
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._revoked_tokens: set = set()

    # ── API Key management ───────────────────────────────────────────

    def create_key(
        self,
        owner: str,
        scopes: Optional[List[str]] = None,
        expires_in: Optional[int] = None,
    ) -> str:
        """Generate a new API key for *owner* with optional *scopes*.

        Returns the raw key string. The raw key is returned once at creation
        time; only its SHA-256 hash is stored internally so that a leak of
        the store does not expose active credentials.
        """
        raw_key = f"ao_{uuid.uuid4().hex}"
        key_hash = self._hash_key(raw_key)
        expires_at = (time.time() + expires_in) if expires_in else None
        self._keys[key_hash] = {
            "hash": key_hash,
            "owner": owner,
            "scopes": scopes or ["*"],
            "status": AuthTokenStatus.ACTIVE,
            "created_at": time.time(),
            "expires_at": expires_at,
        }
        logger.info("Created API key for %s (hash=%s...)", owner, key_hash[:8])
        return raw_key

    def revoke_key(self, raw_key_or_hash: str) -> bool:
        """Revoke an API key by its raw value or its hash."""
        key_hash = (
            raw_key_or_hash
            if len(raw_key_or_hash) == 64 and all(c in "0123456789abcdef" for c in raw_key_or_hash)
            else self._hash_key(raw_key_or_hash)
        )
        entry = self._keys.get(key_hash)
        if entry and entry["status"] == AuthTokenStatus.ACTIVE:
            entry["status"] = AuthTokenStatus.REVOKED
            self._revoked_tokens.add(key_hash)
            logger.info("Revoked API key for %s (hash=%s...)", entry["owner"], key_hash[:8])
            return True
        return False

    def disable_key(self, raw_key_or_hash: str) -> bool:
        """Disable an API key (can be re-enabled later)."""
        key_hash = self._resolve_key_hash(raw_key_or_hash)
        entry = self._keys.get(key_hash)
        if entry and entry["status"] == AuthTokenStatus.ACTIVE:
            entry["status"] = AuthTokenStatus.DISABLED
            logger.info("Disabled API key for %s (hash=%s...)", entry["owner"], key_hash[:8])
            return True
        return False

    def enable_key(self, raw_key_or_hash: str) -> bool:
        """Re-enable a previously disabled key."""
        key_hash = self._resolve_key_hash(raw_key_or_hash)
        entry = self._keys.get(key_hash)
        if entry and entry["status"] == AuthTokenStatus.DISABLED:
            entry["status"] = AuthTokenStatus.ACTIVE
            logger.info("Enabled API key for %s (hash=%s...)", entry["owner"], key_hash[:8])
            return True
        return False

    def validate_key(self, raw_key: str) -> Tuple[bool, str, Optional[Dict]]:
        """Validate an API key.

        Returns (is_valid, reason, key_entry).
        ``is_valid`` is True only when the key exists, is active, and is not
        expired. Stale, revoked, disabled, and expired keys all return False
        with a descriptive reason.
        """
        key_hash = self._hash_key(raw_key)
        entry = self._keys.get(key_hash)
        if not entry:
            return False, "invalid_api_key", None

        status = entry["status"]
        if status == AuthTokenStatus.REVOKED:
            return False, "api_key_revoked", entry
        if status == AuthTokenStatus.DISABLED:
            return False, "api_key_disabled", entry
        if status == AuthTokenStatus.EXPIRED:
            return False, "api_key_expired", entry

        if entry["expires_at"] and time.time() > entry["expires_at"]:
            entry["status"] = AuthTokenStatus.EXPIRED
            return False, "api_key_expired", entry

        return True, "ok", entry

    def list_keys(self, owner: Optional[str] = None) -> List[Dict]:
        """List all keys, optionally filtered by owner."""
        keys = list(self._keys.values())
        if owner:
            keys = [k for k in keys if k["owner"] == owner]
        return [
            {
                "hash": k["hash"][:16] + "...",
                "owner": k["owner"],
                "scopes": k["scopes"],
                "status": k["status"],
                "created_at": k["created_at"],
                "expires_at": k["expires_at"],
            }
            for k in keys
        ]

    # ── Session management (browser clients) ─────────────────────────

    def create_session(self, owner: str, scopes: Optional[List[str]] = None) -> str:
        """Create a browser session for *owner*.

        Returns a session token (cookie value). Internally tracked by hash.
        """
        session_id = uuid.uuid4().hex
        session_hash = self._hash_key(session_id)
        self._sessions[session_hash] = {
            "session_id": session_id[:16],
            "owner": owner,
            "scopes": scopes or ["*"],
            "status": AuthTokenStatus.ACTIVE,
            "created_at": time.time(),
            "expires_at": time.time() + 86400,  # 24h default
        }
        logger.info("Created session for %s (id=%s...)", owner, session_id[:8])
        return session_id

    def validate_session(self, session_token: str) -> Tuple[bool, str, Optional[Dict]]:
        """Validate a browser session token."""
        session_hash = self._hash_key(session_token)
        entry = self._sessions.get(session_hash)
        if not entry:
            return False, "invalid_session", None

        if entry["status"] == AuthTokenStatus.REVOKED:
            return False, "session_revoked", entry

        if entry["expires_at"] and time.time() > entry["expires_at"]:
            entry["status"] = AuthTokenStatus.EXPIRED
            return False, "session_expired", entry

        return True, "ok", entry

    def revoke_session(self, session_token: str) -> bool:
        """Revoke a browser session."""
        session_hash = self._hash_key(session_token)
        entry = self._sessions.get(session_hash)
        if entry and entry["status"] == AuthTokenStatus.ACTIVE:
            entry["status"] = AuthTokenStatus.REVOKED
            logger.info("Revoked session for %s (id=%s...)", entry["owner"], entry["session_id"][:8])
            return True
        return False

    def is_revoked(self, token_hash: str) -> bool:
        """Check whether a token hash has been explicitly revoked."""
        return token_hash in self._revoked_tokens

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def _resolve_key_hash(self, raw_or_hash: str) -> str:
        if len(raw_or_hash) == 64 and all(c in "0123456789abcdef" for c in raw_or_hash):
            return raw_or_hash
        return self._hash_key(raw_or_hash)


# Module-level singleton — the auth store is shared across middleware,
# routes, and tests.
auth_store = ApiKeyStore()
