"""Tests for per-tenant concurrency enforcement in scheduler (#1079, #950)."""
import pytest
from src.orchestrator.scheduler import TaskScheduler


class TestPerTenantConcurrency:
    def setup_method(self):
        self.scheduler = TaskScheduler(max_per_tenant=2)

    @pytest.mark.asyncio
    async def test_tenant_limited_by_concurrency(self):
        """A tenant should not exceed the max concurrent tasks."""
        self.scheduler.enqueue({"tenant": "tenant-A", "name": "t1"}, "default", 1)
        self.scheduler.enqueue({"tenant": "tenant-A", "name": "t2"}, "default", 2)
        self.scheduler.enqueue({"tenant": "tenant-A", "name": "t3"}, "default", 3)
        self.scheduler.enqueue({"tenant": "tenant-B", "name": "t4"}, "default", 4)

        task1 = await self.scheduler.dequeue()
        assert task1 is not None
        task2 = await self.scheduler.dequeue()
        assert task2 is not None
        task3 = await self.scheduler.dequeue()
        assert task3 is not None
        assert task3.get("tenant") == "tenant-B", "Should serve different tenant when tenant-A at limit"

    @pytest.mark.asyncio
    async def test_complete_frees_tenant_slot(self):
        """Completing a task should free a concurrency slot."""
        self.scheduler.enqueue({"tenant": "t1", "name": "a"}, "default", 1)
        self.scheduler.enqueue({"tenant": "t1", "name": "b"}, "default", 1)
        self.scheduler.enqueue({"tenant": "t1", "name": "c"}, "default", 1)
        self.scheduler.enqueue({"tenant": "t2", "name": "d"}, "default", 1)

        task_a = await self.scheduler.dequeue()
        task_b = await self.scheduler.dequeue()
        # t1 at capacity
        next1 = await self.scheduler.dequeue()
        assert next1 is not None and next1.get("tenant") == "t2"

        self.scheduler.complete(task_a["id"])
        next2 = await self.scheduler.dequeue()
        assert next2 is not None and next2.get("tenant") == "t1"

    @pytest.mark.asyncio
    async def test_different_tenants_independent(self):
        """Different tenants should not affect each other."""
        self.scheduler = TaskScheduler(max_per_tenant=1)
        self.scheduler.enqueue({"tenant": "alice", "name": "a1"}, "default", 1)
        self.scheduler.enqueue({"tenant": "bob", "name": "b1"}, "default", 1)
        self.scheduler.enqueue({"tenant": "alice", "name": "a2"}, "default", 1)

        t1 = await self.scheduler.dequeue()
        assert t1 is not None
        t2 = await self.scheduler.dequeue()
        assert t2 is not None and t2.get("tenant") == "bob"

    @pytest.mark.asyncio
    async def test_recovery_after_restart(self):
        """Re-enqueued tasks after restart should respect tenant limits."""
        self.scheduler = TaskScheduler(max_per_tenant=1)
        for i in range(3):
            self.scheduler.enqueue({"tenant": "x", "name": f"r-{i}"}, "recovery", 1)
        self.scheduler.enqueue({"tenant": "y", "name": "other"}, "recovery", 1)

        t1 = await self.scheduler.dequeue("recovery")
        assert t1 is not None and t1.get("tenant") == "x"
        t2 = await self.scheduler.dequeue("recovery")
        assert t2 is not None and t2.get("tenant") == "y"
