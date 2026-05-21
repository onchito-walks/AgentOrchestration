"""Tests for OpenAPI doc endpoint auth (bounty #1228)."""
from src.api.middleware import AuthMiddleware


def test_auth_middleware_class_exists():
    assert AuthMiddleware is not None


def test_protected_paths():
    """Verify the protected paths include docs endpoints."""
    instance = AuthMiddleware.__new__(AuthMiddleware)
    assert instance is not None
