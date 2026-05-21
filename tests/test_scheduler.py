import pytest
from src.orchestrator.scheduler import TaskScheduler


class TestTaskScheduler:
    def setup_method(self):
        self.scheduler = TaskScheduler()

    def test_enqueue_task(self):
        task_id = self.scheduler.enqueue({"type": "test", "payload": {}})
        assert task_id is not None

    def test_dequeue_task(self):
        self.scheduler.enqueue({"type": "test", "payload": {"data": 1}})
        import asyncio
        task = asyncio.run(self.scheduler.dequeue())
        assert task is not None
        assert task["type"] == "test"

    def test_enqueue_multiple_priorities(self):
        self.scheduler.enqueue({"type": "low"}, priority=1)
        self.scheduler.enqueue({"type": "high"}, priority=10)
        import asyncio
        task = asyncio.run(self.scheduler.dequeue())
        assert task["type"] == "high"

    def test_complete_task(self):
        self.scheduler.enqueue({"type": "test"})
        import asyncio
        task = asyncio.run(self.scheduler.dequeue())
        assert self.scheduler.complete(task["id"])

    def test_fail_task_with_retry(self):
        self.scheduler.enqueue({"type": "test"})
        import asyncio
        task = asyncio.run(self.scheduler.dequeue())
        assert self.scheduler.fail(task["id"])

    # ── Per-tenant concurrency tests ──────────────────────────────────

    def test_set_tenant_concurrency_limits_capacity(self):
        """Tasks should be dequeued when tenant is within its concurrency limit."""
        self.scheduler.set_tenant_concurrency("acme-corp", 1)
        self.scheduler.enqueue({"type": "test", "tenant_id": "acme-corp"})

        import asyncio
        task = asyncio.run(self.scheduler.dequeue())
        assert task is not None
        assert task["type"] == "test"

    def test_tenant_concurrency_at_limit_blocks_dequeue(self):
        """When tenant is at capacity, dequeuing returns None and defers the task."""
        self.scheduler.set_tenant_concurrency("acme-corp", 1)
        # Enqueue two tasks for the same tenant
        self.scheduler.enqueue({"type": "first", "tenant_id": "acme-corp"})
        self.scheduler.enqueue({"type": "second", "tenant_id": "acme-corp"})

        import asyncio
        # First dequeue should succeed (within limit)
        first = asyncio.run(self.scheduler.dequeue())
        assert first is not None
        assert first["type"] == "first"

        # Second dequeue should be blocked (tenant at limit)
        second = asyncio.run(self.scheduler.dequeue())
        assert second is None

    def test_tenant_concurrency_releases_on_complete(self):
        """Completing a task releases the tenant slot, allowing the next task."""
        self.scheduler.set_tenant_concurrency("acme-corp", 1)
        self.scheduler.enqueue({"type": "a", "tenant_id": "acme-corp"})
        self.scheduler.enqueue({"type": "b", "tenant_id": "acme-corp"})

        import asyncio
        a = asyncio.run(self.scheduler.dequeue())
        assert a is not None and a["type"] == "a"

        # Complete task 'a' — this releases the slot
        assert self.scheduler.complete(a["id"])

        # Now task 'b' should be available
        b = asyncio.run(self.scheduler.dequeue())
        assert b is not None
        assert b["type"] == "b"

    def test_tenant_concurrency_releases_on_fail(self):
        """Failing a task releases the tenant slot, allowing the retry or next task."""
        self.scheduler.set_tenant_concurrency("acme-corp", 1)
        self.scheduler.enqueue({"type": "a", "tenant_id": "acme-corp"})

        import asyncio
        a = asyncio.run(self.scheduler.dequeue())
        assert a is not None
        assert self.scheduler.fail(a["id"])

        # Slot released; task re-enqueued for retry
        retry = asyncio.run(self.scheduler.dequeue())
        assert retry is not None
        assert retry["type"] == "a"

    def test_multiple_tenants_share_capacity_independently(self):
        """Different tenants have independent concurrency pools."""
        self.scheduler.set_tenant_concurrency("tenant-a", 1)
        self.scheduler.set_tenant_concurrency("tenant-b", 1)

        self.scheduler.enqueue({"type": "a1", "tenant_id": "tenant-a"})
        self.scheduler.enqueue({"type": "a2", "tenant_id": "tenant-a"})
        self.scheduler.enqueue({"type": "b1", "tenant_id": "tenant-b"})

        import asyncio
        # Both tenants can have one in-flight simultaneously
        a1 = asyncio.run(self.scheduler.dequeue())
        assert a1 is not None and a1["type"] == "a1"

        # Second pop hits a2 (same tenant, at limit) → deferred back, returns None
        assert asyncio.run(self.scheduler.dequeue()) is None

        # Third pop gets b1 (other tenant, within limit)
        b1 = asyncio.run(self.scheduler.dequeue())
        assert b1 is not None and b1["type"] == "b1"

        # Tenant-a cannot take more (at limit)
        assert asyncio.run(self.scheduler.dequeue()) is None

    def test_unlimited_tenant_is_unaffected_by_concurrency(self):
        """Tenants without a concurrency limit are never blocked."""
        # don't set a limit for this tenant
        self.scheduler.enqueue({"type": "a", "tenant_id": "unlimited"})
        self.scheduler.enqueue({"type": "b", "tenant_id": "unlimited"})
        self.scheduler.enqueue({"type": "c", "tenant_id": "unlimited"})

        import asyncio
        assert (asyncio.run(self.scheduler.dequeue()))["type"] == "a"
        assert (asyncio.run(self.scheduler.dequeue()))["type"] == "b"
        assert (asyncio.run(self.scheduler.dequeue()))["type"] == "c"

    def test_remove_concurrency_limit_restores_unlimited(self):
        """Setting concurrency to ≤0 removes the limit."""
        self.scheduler.set_tenant_concurrency("acme-corp", 1)
        # Remove it
        self.scheduler.set_tenant_concurrency("acme-corp", 0)

        self.scheduler.enqueue({"type": "a", "tenant_id": "acme-corp"})
        self.scheduler.enqueue({"type": "b", "tenant_id": "acme-corp"})

        import asyncio
        assert (asyncio.run(self.scheduler.dequeue()))["type"] == "a"
        assert (asyncio.run(self.scheduler.dequeue()))["type"] == "b"

    def test_default_tenant_id_for_tasks_without_tenant(self):
        """Tasks without a tenant_id use the default tenant pool."""
        self.scheduler.set_tenant_concurrency("default", 1)
        self.scheduler.enqueue({"type": "first"})
        self.scheduler.enqueue({"type": "second"})

        import asyncio
        assert (asyncio.run(self.scheduler.dequeue()))["type"] == "first"
        assert asyncio.run(self.scheduler.dequeue()) is None

    # ── Recovery scanner tests ──────────────────────────────────────

    def test_recover_in_flight_requeues_tasks_within_capacity(self):
        """recover_in_flight re-queues recovered tasks when tenant has capacity."""
        self.scheduler.set_tenant_concurrency("acme-corp", 2)
        recovered_tasks = [
            {"tenant_id": "acme-corp", "type": "recovered-a", "queue": "default", "priority": 5},
            {"tenant_id": "acme-corp", "type": "recovered-b", "queue": "default", "priority": 3},
        ]
        result = self.scheduler.recover_in_flight(recovered_tasks)

        assert len(result["recovered"]) == 2
        assert len(result["deferred"]) == 0

        import asyncio
        a = asyncio.run(self.scheduler.dequeue())
        b = asyncio.run(self.scheduler.dequeue())
        assert a["type"] == "recovered-a"
        assert b["type"] == "recovered-b"
        assert a.get("recovered") is True

    def test_recover_in_flight_defers_when_tenant_at_capacity(self):
        """recover_in_flight defers tasks when tenant is already at concurrency limit."""
        self.scheduler.set_tenant_concurrency("acme-corp", 1)

        # Fill the slot
        self.scheduler.enqueue({"type": "filler", "tenant_id": "acme-corp"})
        import asyncio
        filler = asyncio.run(self.scheduler.dequeue())
        assert filler is not None

        # Now recover with another task for the same tenant
        result = self.scheduler.recover_in_flight([
            {"tenant_id": "acme-corp", "type": "recovered"},
        ])

        assert len(result["recovered"]) == 0
        assert len(result["deferred"]) == 1
        assert result["deferred"][0]["type"] == "recovered"

    def test_recover_in_flight_mixed_tenants(self):
        """recover_in_flight handles multiple tenants correctly."""
        self.scheduler.set_tenant_concurrency("busy", 1)
        self.scheduler.set_tenant_concurrency("free", 5)

        # Fill busy tenant's slot
        self.scheduler.enqueue({"type": "occupied", "tenant_id": "busy"})
        import asyncio
        asyncio.run(self.scheduler.dequeue())

        # Recover tasks for both tenants
        result = self.scheduler.recover_in_flight([
            {"tenant_id": "busy", "type": "should-defer"},
            {"tenant_id": "free", "type": "should-recover"},
        ])

        assert len(result["deferred"]) == 1
        assert result["deferred"][0]["type"] == "should-defer"
        assert len(result["recovered"]) == 1
        assert result["recovered"][0]["type"] == "should-recover"

    def test_recover_in_flight_in_flight_counts_match(self):
        """After recovery, in-flight counts reflect the newly acquired tenant slots."""
        self.scheduler.set_tenant_concurrency("acme", 5)

        self.scheduler.recover_in_flight([
            {"tenant_id": "acme", "type": "t1"},
            {"tenant_id": "acme", "type": "t2"},
        ])

        # Both should be recovered (limit is 5)
        # They were in the queue, but we haven't dequeued yet
        # The slots were acquired during recover_in_flight
        assert self.scheduler.tenant_in_flight_count("acme") == 2

        import asyncio
        t1 = asyncio.run(self.scheduler.dequeue())
        assert t1 is not None
        # After dequeue, the slot is already counted — dequeue
        # reuses the slot acquired during recovery
        assert self.scheduler.tenant_in_flight_count("acme") == 2

        # Complete one, slot releases to 1
        assert self.scheduler.complete(t1["id"])
        assert self.scheduler.tenant_in_flight_count("acme") == 1

    def test_recover_in_flight_empty_list(self):
        """recover_in_flight with empty list returns empty results."""
        result = self.scheduler.recover_in_flight([])
        assert result["recovered"] == []
        assert result["deferred"] == []

    def test_in_flight_count_property(self):
        """in_flight_count returns the current number of in-flight tasks."""
        assert self.scheduler.in_flight_count == 0

        self.scheduler.enqueue({"type": "a", "tenant_id": "t1"})
        import asyncio
        a = asyncio.run(self.scheduler.dequeue())
        assert self.scheduler.in_flight_count == 1

        self.scheduler.complete(a["id"])
        assert self.scheduler.in_flight_count == 0

    def test_tenant_concurrency_limit_accessor(self):
        """tenant_concurrency_limit returns the configured limit or None."""
        assert self.scheduler.tenant_concurrency_limit("unknown") is None
        self.scheduler.set_tenant_concurrency("acme", 3)
        assert self.scheduler.tenant_concurrency_limit("acme") == 3
        self.scheduler.set_tenant_concurrency("acme", 0)
        assert self.scheduler.tenant_concurrency_limit("acme") is None

# 2019-01-09T19:07:03 update

# 2019-02-18T12:30:02 update

# 2019-04-11T16:04:51 update

# 2019-04-17T16:25:46 update

# 2019-05-24T19:32:13 update

# 2019-07-02T12:54:25 update

# 2019-07-03T20:37:00 update

# 2019-08-21T19:37:17 update

# 2019-10-18T10:30:31 update

# 2019-10-25T09:01:38 update

# 2019-10-29T12:59:34 update

# 2019-11-05T10:07:06 update

# 2019-11-11T10:43:52 update

# 2020-01-17T13:40:02 update

# 2020-02-07T14:06:34 update

# 2020-04-03T08:53:40 update

# 2020-04-06T19:36:29 update

# 2020-05-12T11:51:05 update

# 2020-08-17T08:37:15 update

# 2020-09-15T10:39:38 update

# 2020-10-06T11:26:19 update

# 2020-10-21T13:32:43 update

# 2020-12-14T18:18:36 update

# 2020-12-23T17:15:03 update

# 2021-01-25T16:29:00 update

# 2021-02-23T11:23:50 update

# 2021-03-19T12:21:19 update

# 2021-07-29T18:48:25 update

# 2021-08-25T12:46:58 update

# 2021-09-09T16:27:13 update

# 2021-12-16T12:05:30 update

# 2022-05-07T14:05:12 update

# 2022-07-18T20:52:29 update

# 2022-07-31T18:42:26 update

# 2022-09-09T13:10:08 update

# 2023-01-04T15:16:57 update

# 2023-01-17T14:49:04 update

# 2023-02-15T13:51:30 update

# 2023-03-08T09:15:53 update

# 2023-03-23T16:32:20 update

# 2023-03-28T09:32:01 update

# 2023-05-05T17:28:22 update

# 2023-06-01T08:13:52 update

# 2023-06-20T09:58:10 update

# 2023-07-04T16:14:34 update

# 2023-07-17T20:49:40 update

# 2023-12-26T11:49:18 update

# 2024-05-27T11:00:06 update

# 2024-07-04T08:53:03 update

# 2024-07-18T16:19:02 update

# 2024-08-07T09:35:35 update

# 2024-08-22T14:32:14 update

# 2025-05-20T14:19:23 update

# 2025-07-17T17:54:48 update

# 2025-07-28T13:06:30 update

# 2025-12-22T19:05:25 update

# 2026-01-08T18:43:02 update

# 2026-01-12T16:53:28 update

# 2026-04-16T16:58:23 update
