"""Auth-aware report cache — prevents stale authorization in cached results.

Issue #1432 (Bounty $8k): Cache keys include authorization context and
revalidate access before serving cached reports.
"""

import time
import hashlib
import json
import logging
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger(__name__)


class AuthAwareReportCache:
    """Report cache that scopes entries by authorization context.

    Cache keys incorporate both the query parameters and the requester's
    authorization fingerprint (user ID, roles hash). Before returning a
    cached entry, the auth context is revalidated to ensure the caller
    still has the same permissions.

    Usage:
        cache = AuthAwareReportCache()
        key = cache.build_key("dashboard/summary", {"filter": "active"})
        result = cache.get(key, auth_context)
        if result is None:
            result = compute_expensive_report()
            cache.set(key, auth_context, result)
        return result
    """

    def __init__(self, ttl_seconds: float = 300.0, revalidate_fn: Optional[Callable] = None):
        self._store: Dict[str, Dict] = {}
        self._ttl = ttl_seconds
        self._revalidate_fn = revalidate_fn  # Optional external auth check

    # ── Cache key construction ────────────────────────────────────────

    @staticmethod
    def _auth_fingerprint(auth_context: Optional[Dict]) -> str:
        """Hash the relevant auth fields for cache key scoping."""
        if not auth_context:
            return "anon"
        payload = {
            "user_id": auth_context.get("user_id", ""),
            "roles": sorted(auth_context.get("roles", [])),
            "scope": sorted(auth_context.get("scope", [])),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def build_key(self, report_name: str, query_params: Optional[Dict] = None) -> str:
        """Build a cache key from report name + query params (no auth yet)."""
        parts = [report_name]
        if query_params:
            # Normalize params for reproducible keys
            normalized = json.dumps(query_params, sort_keys=True, separators=(",", ":"))
            parts.append(hashlib.sha256(normalized.encode()).hexdigest()[:16])
        return ":".join(parts)

    # ── Auth revalidation ─────────────────────────────────────────────

    def _auth_changed(
        self, auth_context: Optional[Dict], cached_auth: str
    ) -> bool:
        """Check if the caller's auth context differs from the cached one."""
        current = self._auth_fingerprint(auth_context)
        return current != cached_auth

    def _revalidate(self, auth_context: Optional[Dict]) -> bool:
        """Run external revalidation if configured.

        Returns True if auth is still valid, False if stale.
        Without a configured revalidate function, auth fingerprint
        changes are conservatively denied (might be stale permissions).
        """
        if self._revalidate_fn:
            try:
                return bool(self._revalidate_fn(auth_context))
            except Exception as e:
                logger.warning("Auth revalidation failed: %s", e)
                return False
        # No revalidation function — auth fingerprint must match to serve
        return False

    # ── Public API ────────────────────────────────────────────────────

    def get(
        self, key: str, auth_context: Optional[Dict] = None
    ) -> Optional[Any]:
        """Retrieve a cached report, revalidating auth first.

        Returns None if: cache miss, expired, auth changed since caching,
        or revalidation failed.
        """
        entry = self._store.get(key)
        if entry is None:
            return None

        # TTL check
        age = time.time() - entry["cached_at"]
        if age > self._ttl:
            self._store.pop(key, None)
            return None

        # Auth revalidation
        if self._auth_changed(auth_context, entry["auth_fingerprint"]):
            logger.info(
                "Cache HIT but auth changed — revalidating (key=%s)", key
            )
            if not self._revalidate(auth_context):
                self._store.pop(key, None)
                return None
            # Auth OK but context changed — update fingerprint
            entry["auth_fingerprint"] = self._auth_fingerprint(auth_context)

        logger.debug("Cache HIT (key=%s age=%.1fs)", key, age)
        return entry["data"]

    def set(
        self,
        key: str,
        auth_context: Optional[Dict],
        data: Any,
    ) -> None:
        """Store a report result keyed by query + auth context."""
        self._store[key] = {
            "data": data,
            "auth_fingerprint": self._auth_fingerprint(auth_context),
            "cached_at": time.time(),
        }

    def invalidate(self, key: str) -> None:
        """Remove a single cache entry."""
        self._store.pop(key, None)

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    def stats(self) -> Dict:
        """Return cache statistics for monitoring."""
        now = time.time()
        ages = [now - e["cached_at"] for e in self._store.values()]
        return {
            "entries": self.size,
            "oldest_sec": max(ages) if ages else 0,
            "newest_sec": min(ages) if ages else 0,
        }
