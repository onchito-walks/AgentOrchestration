import pytest
from src.agent.registry import AgentRegistry, AgentStatus


class TestAgentRegistry:
    def setup_method(self):
        self.registry = AgentRegistry()

    def test_register_agent(self):
        agent_id = self.registry.register("test-agent", "worker.processor")
        assert agent_id is not None
        assert self.registry.count() == 1

    def test_get_agent(self):
        agent_id = self.registry.register("test-agent", "worker.processor")
        agent = self.registry.get(agent_id)
        assert agent is not None
        assert agent["name"] == "test-agent"
        assert agent["type"] == "worker.processor"

    def test_get_nonexistent_agent(self):
        agent = self.registry.get("nonexistent-id")
        assert agent is None

    def test_list_agents(self):
        self.registry.register("agent-1", "worker.processor")
        self.registry.register("agent-2", "worker.analyzer")
        self.registry.register("agent-3", "monitor.watcher")
        assert len(self.registry.list()) == 3

    def test_list_agents_by_group(self):
        self.registry.register("agent-1", "worker.processor")
        self.registry.register("agent-2", "monitor.watcher")
        workers = self.registry.list(group="worker")
        assert len(workers) == 1

    def test_update_status(self):
        agent_id = self.registry.register("test-agent", "worker.processor")
        assert self.registry.update_status(agent_id, AgentStatus.RUNNING)
        agent = self.registry.get(agent_id)
        assert agent["status"] == "running"

    def test_delete_agent(self):
        agent_id = self.registry.register("test-agent", "worker.processor")
        assert self.registry.delete(agent_id)
        assert self.registry.count() == 0

    def test_delete_nonexistent_agent(self):
        assert not self.registry.delete("nonexistent-id")

# 2019-01-23T10:28:57 update

# 2019-01-28T18:15:57 update

# 2019-02-22T11:46:37 update

# 2019-03-27T14:43:52 update

# 2019-04-12T16:58:25 update

# 2019-05-27T15:15:18 update

# 2019-07-17T14:36:58 update

# 2019-09-06T12:29:31 update

# 2019-11-27T17:43:26 update

# 2019-11-28T08:42:43 update

# 2019-12-03T20:34:02 update

# 2019-12-26T08:15:09 update

# 2020-01-07T09:36:32 update

# 2020-01-10T12:44:52 update

# 2020-07-05T19:33:32 update

# 2020-07-07T14:16:11 update

# 2020-07-28T08:29:39 update

# 2020-08-26T18:58:21 update

# 2020-08-28T09:50:37 update

# 2020-09-17T15:23:33 update

# 2020-09-23T16:22:24 update

# 2020-10-14T13:27:24 update

# 2020-11-20T11:40:04 update

# 2020-12-10T13:55:01 update

# 2020-12-25T20:33:02 update

# 2021-03-22T19:53:48 update
