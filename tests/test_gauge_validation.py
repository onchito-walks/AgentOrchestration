"""Tests for gauge value validation (bounty #811)."""
import pytest
from src.common.metrics import MetricsCollector


def test_gauge_accepts_int():
    mc = MetricsCollector()
    mc.gauge("test", 42)
    assert mc._gauges["test"] == 42.0


def test_gauge_accepts_float():
    mc = MetricsCollector()
    mc.gauge("test", 3.14)
    assert mc._gauges["test"] == 3.14


def test_gauge_rejects_string():
    mc = MetricsCollector()
    with pytest.raises(TypeError, match="must be numeric"):
        mc.gauge("test", "not_a_number")


def test_gauge_rejects_list():
    mc = MetricsCollector()
    with pytest.raises(TypeError, match="must be numeric"):
        mc.gauge("test", [1, 2, 3])


def test_gauge_rejects_none():
    mc = MetricsCollector()
    with pytest.raises(TypeError, match="must be numeric"):
        mc.gauge("test", None)


def test_gauge_accepts_negative():
    mc = MetricsCollector()
    mc.gauge("test", -1.5)
    assert mc._gauges["test"] == -1.5
