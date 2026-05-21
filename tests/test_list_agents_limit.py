"""Tests for pagination limit on list_agents."""

import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.agent.registry import AgentRegistry, AgentStatus


class TestRegistryListLimit:
    """Test AgentRegistry.list() limit parameter."""

    def setup_method(self):
        self.registry = AgentRegistry()

    def test_list_no_limit_returns_all(self):
        """Without limit, all agents are returned."""
        for i in range(150):
            self.registry.register(f"agent-{i}", "worker.processor")
        assert len(self.registry.list()) == 150

    def test_list_with_limit_caps_results(self):
        """With limit, only up to limit agents are returned."""
        for i in range(150):
            self.registry.register(f"agent-{i}", "worker.processor")
        result = self.registry.list(limit=50)
        assert len(result) == 50

    def test_list_limit_below_one_clamped_to_one(self):
        """Limit < 1 is silently clamped to 1."""
        self.registry.register("a1", "worker.processor")
        self.registry.register("a2", "worker.processor")
        result = self.registry.list(limit=0)
        assert len(result) == 1

    def test_list_limit_negative_clamped_to_one(self):
        """Negative limit is silently clamped to 1."""
        self.registry.register("a1", "worker.processor")
        self.registry.register("a2", "worker.processor")
        result = self.registry.list(limit=-5)
        assert len(result) == 1

    def test_list_limit_above_100_clamped_to_100(self):
        """Limit > 100 is silently clamped to 100."""
        for i in range(150):
            self.registry.register(f"agent-{i}", "worker.processor")
        result = self.registry.list(limit=200)
        assert len(result) == 100

    def test_list_limit_exactly_100(self):
        """Limit of exactly 100 is allowed."""
        for i in range(150):
            self.registry.register(f"agent-{i}", "worker.processor")
        result = self.registry.list(limit=100)
        assert len(result) == 100

    def test_list_limit_exactly_1(self):
        """Limit of exactly 1 is allowed."""
        self.registry.register("a1", "worker.processor")
        self.registry.register("a2", "worker.processor")
        result = self.registry.list(limit=1)
        assert len(result) == 1

    def test_list_limit_with_status_filter(self):
        """Limit works with status filter."""
        for i in range(10):
            self.registry.register(f"agent-{i}", "worker.processor")
        # Update some to RUNNING
        all_agents = self.registry.list()
        for agent in all_agents[:5]:
            self.registry.update_status(agent["id"], AgentStatus.RUNNING)
        result = self.registry.list(status=AgentStatus.RUNNING, limit=3)
        assert len(result) == 3

    def test_list_limit_with_group_filter(self):
        """Limit works with group filter."""
        for i in range(10):
            self.registry.register(f"agent-{i}", "worker.processor")
        for i in range(10):
            self.registry.register(f"agent-{i+10}", "monitor.watcher")
        result = self.registry.list(group="worker", limit=5)
        assert len(result) == 5

    def test_list_limit_more_than_available(self):
        """Limit larger than available agents returns all available."""
        self.registry.register("a1", "worker.processor")
        self.registry.register("a2", "worker.processor")
        result = self.registry.list(limit=50)
        assert len(result) == 2

    def test_list_limit_none_returns_all(self):
        """Limit=None returns all agents (backward compatible)."""
        for i in range(150):
            self.registry.register(f"agent-{i}", "worker.processor")
        result = self.registry.list(limit=None)
        assert len(result) == 150


class TestListAgentsRouteLimit:
    """Test the /agents route limit query parameter via FastAPI TestClient."""

    def setup_method(self):
        self.app = create_app()
        self.client = TestClient(self.app)
        # Clear any pre-existing agents by hitting the registry directly
        from src.api.routes import registry
        registry._agents.clear()
        registry._index.clear()
        self.registry = registry

    def _register_agents(self, count: int, agent_type: str = "worker.processor"):
        for i in range(count):
            self.registry.register(f"agent-{i}", agent_type)

    def test_default_limit_is_50(self):
        """Default limit of 50 is applied when no limit param is given."""
        self._register_agents(80)
        response = self.client.get("/api/v2/agents")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 50

    def test_explicit_limit(self):
        """Explicit limit value is respected."""
        self._register_agents(80)
        response = self.client.get("/api/v2/agents?limit=30")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 30

    def test_limit_above_100_clamped(self):
        """Limit > 100 is silently clamped to 100."""
        self._register_agents(150)
        response = self.client.get("/api/v2/agents?limit=500")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 100

    def test_limit_zero_clamped_to_one(self):
        """Limit=0 is clamped to 1."""
        self._register_agents(5)
        response = self.client.get("/api/v2/agents?limit=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 1

    def test_limit_negative_clamped_to_one(self):
        """Negative limit is clamped to 1."""
        self._register_agents(5)
        response = self.client.get("/api/v2/agents?limit=-10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 1

    def test_limit_with_status_filter(self):
        """Limit works alongside status filter."""
        self._register_agents(20)
        all_agents = self.registry.list()
        for agent in all_agents[:10]:
            self.registry.update_status(agent["id"], AgentStatus.RUNNING)
        response = self.client.get("/api/v2/agents?status=running&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 5

    def test_limit_with_group_filter(self):
        """Limit works alongside group filter."""
        self._register_agents(20, "worker.processor")
        self._register_agents(20, "monitor.watcher")
        response = self.client.get("/api/v2/agents?group=worker&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 10
