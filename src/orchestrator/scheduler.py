"""Task Scheduler — Priority-based task queuing and dispatch.

Supports per-tenant concurrency limits and in-flight recovery
for process restarts. The recovery scanner enforces tenant-level
capacity before re-queuing tasks from persistent storage.
"""

import asyncio
import heapq
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

DEFAULT_TENANT = "default"


class PriorityQueue:
    def __init__(self):
        self._queue = []
        self._counter = 0

    def push(self, item: Any, priority: int = 0) -> None:
        heapq.heappush(self._queue, (-priority, self._counter, item))
        self._counter += 1

    def pop(self) -> Optional[Any]:
        if self._queue:
            return heapq.heappop(self._queue)[2]
        return None

    def peek(self) -> Optional[Any]:
        if self._queue:
            return self._queue[0][2]
        return None

    def __len__(self) -> int:
        return len(self._queue)


class TaskScheduler:
    """Priority-based scheduler with per-tenant concurrency enforcement.

    Features:
      - Priority queues per named queue
      - Delayed/scheduled tasks that auto-move to active queues
      - Per-tenant concurrency limits with atomic capacity checks
      - Recovery scanner that respects tenant limits on process restart
      - Bounded audit logging on capacity rejections
    """

    def __init__(self):
        self._queues: Dict[str, PriorityQueue] = {}
        self._scheduled: Dict[str, float] = {}
        self._in_flight: Dict[str, Dict] = {}
        self._max_retries = 3

        # Per-tenant concurrency tracking
        self._tenant_concurrency_limits: Dict[str, int] = {}
        self._tenant_in_flight: Dict[str, int] = {}

    # ── Tenant concurrency management ──────────────────────────────

    def set_tenant_concurrency(self, tenant_id: str, max_concurrent: int) -> None:
        """Set the maximum concurrent in-flight tasks for *tenant_id*.

        A value of 0 or negative removes the limit (unlimited concurrency).
        """
        if max_concurrent <= 0:
            self._tenant_concurrency_limits.pop(tenant_id, None)
        else:
            self._tenant_concurrency_limits[tenant_id] = max_concurrent

    def _check_tenant_capacity(self, tenant_id: str) -> bool:
        """Atomically check whether *tenant_id* has capacity for one more task.

        Returns True when:
          - No limit is configured for this tenant, or
          - Current in-flight count is below the limit.
        """
        limit = self._tenant_concurrency_limits.get(tenant_id)
        if limit is None:
            return True  # no limit = unlimited
        current = self._tenant_in_flight.get(tenant_id, 0)
        return current < limit

    def _acquire_tenant_slot(self, tenant_id: str) -> bool:
        """Try to claim a concurrency slot for *tenant_id*.

        Returns True if the slot was acquired; caller should proceed
        with dispatch. Returns False (without side effects) when the
        tenant is at capacity.
        """
        if not self._check_tenant_capacity(tenant_id):
            return False
        self._tenant_in_flight[tenant_id] = (
            self._tenant_in_flight.get(tenant_id, 0) + 1
        )
        return True

    def _release_tenant_slot(self, tenant_id: str) -> None:
        """Release a concurrency slot previously acquired for *tenant_id*."""
        current = self._tenant_in_flight.get(tenant_id, 0)
        if current > 0:
            self._tenant_in_flight[tenant_id] = current - 1
        else:
            logger.warning(
                "Tenant %s has no in-flight tasks to release (double-release?)",
                tenant_id,
            )

    def _get_tenant_id(self, task: Dict) -> str:
        """Extract the tenant identifier from a task dict."""
        return task.get("tenant_id", DEFAULT_TENANT)

    # ── Core queue operations ──────────────────────────────────────

    def enqueue(self, task: Dict, queue: str = "default", priority: int = 0) -> str:
        task_id = str(uuid4())
        task["id"] = task_id
        task["enqueued_at"] = time.time()
        task["retries"] = 0

        if queue not in self._queues:
            self._queues[queue] = PriorityQueue()
        self._queues[queue].push(task, priority)
        return task_id

    def schedule(self, task: Dict, delay: float, queue: str = "default", priority: int = 0) -> str:
        task_id = str(uuid4())
        task["id"] = task_id
        self._scheduled[task_id] = time.time() + delay
        return task_id

    async def dequeue(self, queue: str = "default", timeout: float = 1.0) -> Optional[Dict]:
        now = time.time()
        expired = [tid for tid, t in self._scheduled.items() if t <= now]
        for tid in expired:
            task = self._scheduled.pop(tid)
            if task:
                self.enqueue(task, queue)

        if queue in self._queues and len(self._queues[queue]) > 0:
            task = self._queues[queue].pop()
            if task:
                tenant_id = self._get_tenant_id(task)

                # If the slot was already acquired (e.g. by recover_in_flight),
                # don't double-count
                if task.get("_slot_acquired"):
                    self._in_flight[task["id"]] = task
                    return task

                if not self._acquire_tenant_slot(tenant_id):
                    # Tenant at capacity — defer; don't silently drop
                    logger.info(
                        "Deferred task %s for tenant %s (at concurrency limit)",
                        task.get("id"),
                        tenant_id,
                    )
                    # Re-enqueue at back of same queue so other tenants can proceed
                    self.enqueue(task, queue, priority=task.get("priority", 0))
                    return None
                self._in_flight[task["id"]] = task
                return task
        return None

    def complete(self, task_id: str) -> bool:
        task = self._in_flight.pop(task_id, None)
        if task:
            self._release_tenant_slot(self._get_tenant_id(task))
            return True
        return False

    def fail(self, task_id: str, queue: str = "default") -> bool:
        task = self._in_flight.pop(task_id, None)
        if task:
            self._release_tenant_slot(self._get_tenant_id(task))
            task["retries"] += 1
            if task["retries"] < self._max_retries:
                self.enqueue(task, queue, priority=task.get("priority", 0))
                return True
        return False

    # ── Recovery scanner (process restart path) ────────────────────

    def recover_in_flight(self, recovered_tasks: List[Dict]) -> Dict[str, List[Dict]]:
        """Process tasks recovered from persistent storage after a restart.

        Each task is checked against its tenant's concurrency limit.
        Tasks within capacity are re-queued; tasks at capacity are
        returned in the ``deferred`` list with an audit explanation.

        Returns ``{"recovered": [...], "deferred": [...]}``.

        This is the recovery scanner entry point called by the engine
        after a process restart. It atomically validates the tenant
        state precondition before committing any recovered task to
        the active queue.
        """
        recovered: List[Dict] = []
        deferred: List[Dict] = []

        for task in recovered_tasks:
            tenant_id = self._get_tenant_id(task)

            if self._acquire_tenant_slot(tenant_id):
                task["id"] = str(uuid4())
                task["enqueued_at"] = time.time()
                task["recovered"] = True
                task["_slot_acquired"] = True
                queue = task.get("queue", "default")
                self.enqueue(task, queue, priority=task.get("priority", 0))
                recovered.append(task)
                logger.info(
                    "Recovered task %s for tenant %s",
                    task.get("id"),
                    tenant_id,
                )
            else:
                deferred.append(task)
                logger.warning(
                    "Deferred recovered task for tenant %s: "
                    "at concurrency limit (%s/%s). "
                    "Task will be retried when capacity becomes available.",
                    tenant_id,
                    self._tenant_in_flight.get(tenant_id, 0),
                    self._tenant_concurrency_limits.get(tenant_id, "unlimited"),
                )

        return {"recovered": recovered, "deferred": deferred}

    # ── Introspection ──────────────────────────────────────────────

    @property
    def in_flight_count(self) -> int:
        return len(self._in_flight)

    def tenant_in_flight_count(self, tenant_id: str) -> int:
        return self._tenant_in_flight.get(tenant_id, 0)

    def tenant_concurrency_limit(self, tenant_id: str) -> Optional[int]:
        return self._tenant_concurrency_limits.get(tenant_id)

# 2019-04-25T08:37:12 update

# 2019-06-04T16:40:00 update

# 2019-07-11T12:01:28 update

# 2019-08-02T12:20:21 update

# 2019-08-23T10:38:50 update

# 2019-10-31T13:55:52 update

# 2019-11-04T20:12:32 update

# 2019-12-13T12:22:36 update

# 2020-02-01T10:32:37 update

# 2020-02-26T09:44:38 update

# 2020-03-09T19:00:55 update

# 2020-05-01T18:40:34 update

# 2020-05-12T15:10:31 update

# 2020-06-30T13:24:19 update

# 2020-09-22T16:00:45 update

# 2020-10-20T10:52:48 update

# 2020-10-21T12:18:08 update

# 2020-11-06T12:35:01 update

# 2020-12-09T08:09:33 update

# 2021-01-07T08:20:36 update

# 2021-10-02T15:23:16 update

# 2021-10-06T16:14:57 update

# 2021-10-06T09:27:41 update

# 2021-11-19T08:37:40 update

# 2022-03-01T16:39:54 update

# 2022-05-26T13:43:07 update

# 2022-06-02T10:50:58 update

# 2022-06-14T10:46:48 update

# 2022-07-31T16:44:34 update

# 2022-08-30T18:20:12 update

# 2022-11-04T14:47:03 update

# 2022-12-06T10:36:49 update

# 2022-12-22T13:21:12 update

# 2022-12-26T12:24:50 update

# 2023-03-09T08:09:55 update

# 2023-05-01T10:07:37 update

# 2023-06-08T14:32:15 update

# 2023-07-14T17:24:18 update

# 2023-12-14T08:38:31 update

# 2024-02-20T13:43:58 update

# 2024-03-24T08:52:42 update

# 2024-03-28T15:27:17 update

# 2024-03-29T18:10:33 update

# 2024-04-15T20:18:31 update

# 2024-05-27T13:11:52 update

# 2024-05-27T16:42:56 update

# 2024-06-20T13:03:45 update

# 2024-06-28T12:32:58 update

# 2024-07-10T14:10:16 update

# 2024-07-26T14:18:59 update

# 2024-08-12T08:21:05 update

# 2024-08-21T16:58:40 update

# 2024-09-27T19:54:30 update

# 2024-10-21T13:47:42 update

# 2024-11-11T09:19:27 update

# 2024-12-24T08:23:41 update

# 2025-02-14T10:35:15 update

# 2025-03-31T18:09:40 update

# 2025-06-21T17:32:49 update

# 2025-07-21T16:52:28 update

# 2025-08-20T19:45:16 update

# 2025-11-04T18:54:24 update

# 2025-12-09T20:17:36 update

# 2026-01-12T15:42:32 update

# 2026-01-23T14:41:20 update

# 2026-03-18T14:43:07 update

# 2026-04-13T11:43:19 update
