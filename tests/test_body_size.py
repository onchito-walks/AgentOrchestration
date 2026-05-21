"""Tests for max body size enforcement (bounty #1542)."""
from src.api.middleware import BodySizeMiddleware


def test_max_upload_default():
    assert BodySizeMiddleware.MAX_UPLOAD_BYTES == 10 * 1024 * 1024


def test_max_allowed():
    assert BodySizeMiddleware.MAX_ALLOWED == 100 * 1024 * 1024


def test_limits_ordered():
    assert BodySizeMiddleware.MAX_UPLOAD_BYTES < BodySizeMiddleware.MAX_ALLOWED
