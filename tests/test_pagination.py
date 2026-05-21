"""Tests for pagination cap on list_agents (bounty #1106)."""
import pytest
from src.agent.registry import AgentRegistry, AgentStatus


def test_list_with_default_limit():
    reg = AgentRegistry()
    for i in range(200):
        reg.register(f"agent-{i}", "worker")
    result = reg.list()
    assert len(result) == 200  # default: no limit from registry


def test_list_with_explicit_limit():
    reg = AgentRegistry()
    for i in range(200):
        reg.register(f"agent-{i}", "worker")
    result = reg.list(limit=10)
    assert len(result) == 10


def test_list_caps_at_100():
    reg = AgentRegistry()
    for i in range(200):
        reg.register(f"agent-{i}", "worker")
    result = reg.list(limit=500)
    assert len(result) == 100


def test_list_min_limit_is_1():
    reg = AgentRegistry()
    for i in range(200):
        reg.register(f"agent-{i}", "worker")
    result = reg.list(limit=-5)
    assert len(result) == 1


def test_list_limit_none_returns_all():
    reg = AgentRegistry()
    for i in range(200):
        reg.register(f"agent-{i}", "worker")
    result = reg.list(limit=None)
    assert len(result) == 200
