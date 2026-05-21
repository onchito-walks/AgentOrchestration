"""Tests for auth-aware report cache (issue #1432, bounty $8k)."""

import time
import pytest
from src.common.report_cache import AuthAwareReportCache


class TestAuthFingerprint:
    def test_anon_context(self):
        fp = AuthAwareReportCache._auth_fingerprint(None)
        assert fp == "anon"

    def test_user_context(self):
        ctx = {"user_id": "user-1", "roles": ["admin"], "scope": ["read"]}
        fp = AuthAwareReportCache._auth_fingerprint(ctx)
        assert fp != "anon"
        assert len(fp) == 16  # sha256 hex[:16]

    def test_different_users_different_fingerprints(self):
        fp1 = AuthAwareReportCache._auth_fingerprint({"user_id": "a", "roles": [], "scope": []})
        fp2 = AuthAwareReportCache._auth_fingerprint({"user_id": "b", "roles": [], "scope": []})
        assert fp1 != fp2

    def test_role_change_changes_fingerprint(self):
        fp1 = AuthAwareReportCache._auth_fingerprint(
            {"user_id": "u1", "roles": ["viewer"], "scope": []}
        )
        fp2 = AuthAwareReportCache._auth_fingerprint(
            {"user_id": "u1", "roles": ["admin"], "scope": []}
        )
        assert fp1 != fp2


class TestBuildKey:
    def test_no_params(self):
        cache = AuthAwareReportCache()
        key = cache.build_key("dashboard/summary")
        assert key == "dashboard/summary"

    def test_with_params(self):
        cache = AuthAwareReportCache()
        key = cache.build_key("r", {"a": 1, "b": 2})
        assert "r:" in key
        assert key != "r"

    def test_params_order_independent(self):
        cache = AuthAwareReportCache()
        k1 = cache.build_key("r", {"a": 1, "b": 2})
        k2 = cache.build_key("r", {"b": 2, "a": 1})
        assert k1 == k2


class TestCacheGetSet:
    def test_miss_returns_none(self):
        cache = AuthAwareReportCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        cache = AuthAwareReportCache()
        ctx = {"user_id": "u1", "roles": ["admin"], "scope": ["read", "reports"]}
        key = cache.build_key("report/usage")
        cache.set(key, ctx, {"users": 42})
        result = cache.get(key, ctx)
        assert result == {"users": 42}

    def test_expired_entry_returns_none(self):
        cache = AuthAwareReportCache(ttl_seconds=0.01)
        ctx = {"user_id": "u1", "roles": [], "scope": []}
        key = cache.build_key("fast-expire")
        cache.set(key, ctx, "data")
        time.sleep(0.02)
        assert cache.get(key, ctx) is None

    def test_auth_change_revalidates(self):
        revalidated = []

        def reval(ctx):
            revalidated.append(ctx)
            return False  # deny

        cache = AuthAwareReportCache(revalidate_fn=reval)
        admin_ctx = {"user_id": "u1", "roles": ["admin"], "scope": ["read"]}
        viewer_ctx = {"user_id": "u1", "roles": ["viewer"], "scope": ["read"]}

        key = cache.build_key("r")
        cache.set(key, admin_ctx, "secret-admin-data")

        # Viewer tries to access — auth changed + revalidate fails
        result = cache.get(key, viewer_ctx)
        assert result is None  # denied
        assert len(revalidated) == 1

    def test_auth_change_but_still_valid(self):
        def reval(ctx):
            return True  # still valid

        cache = AuthAwareReportCache(revalidate_fn=reval)
        ctx1 = {"user_id": "u1", "roles": ["role-a"], "scope": []}
        ctx2 = {"user_id": "u1", "roles": ["role-b"], "scope": []}

        key = cache.build_key("r")
        cache.set(key, ctx1, "data")

        # Same user, role changed but revalidation passes
        result = cache.get(key, ctx2)
        assert result == "data"  # still served

    def test_invalidate_removes_entry(self):
        cache = AuthAwareReportCache()
        key = cache.build_key("r")
        cache.set(key, None, "x")
        assert cache.get(key) == "x"
        cache.invalidate(key)
        assert cache.get(key) is None

    def test_invalidate_all(self):
        cache = AuthAwareReportCache()
        cache.set("k1", None, 1)
        cache.set("k2", None, 2)
        assert cache.size == 2
        cache.invalidate_all()
        assert cache.size == 0

    def test_auth_change_after_ttl_still_denied(self):
        cache = AuthAwareReportCache(ttl_seconds=3600)
        admin = {"user_id": "u1", "roles": ["admin"], "scope": []}

        key = cache.build_key("r")
        cache.set(key, admin, "sensitive")
        result = cache.get(key, admin)
        assert result == "sensitive"

        # Same user, downgraded role - no revalidate_fn so trusts fingerprint change
        viewer = {"user_id": "u1", "roles": ["viewer"], "scope": []}
        result = cache.get(key, viewer)
        assert result is None  # fingerprint mismatch, no reval fn

    def test_stats(self):
        cache = AuthAwareReportCache()
        cache.set("k1", None, 1)
        cache.set("k2", None, 2)
        s = cache.stats()
        assert s["entries"] == 2
        assert s["oldest_sec"] >= 0
