"""Tests for jitter retry in scheduler (bounty #1546)."""
import asyncio
import time
from src.orchestrator.scheduler import TaskScheduler


def test_default_max_retries():
    sched = TaskScheduler()
    assert sched._max_retries == 3


def test_retry_increments_count():
    sched = TaskScheduler(max_retries=3)
    tid = sched.enqueue({"name": "test"}, "default")
    # dequeue moves to in_flight
    task = asyncio.run(sched.dequeue("default"))
    assert task is not None
    assert sched.fail(task["id"]) is True  # re-enqueued with jitter


def test_retry_limited():
    sched = TaskScheduler(max_retries=2)
    sched.enqueue({"name": "test"}, "default")
    # First attempt: dequeue, fail (retries=1, 1<2 → re-enqueue)
    task = asyncio.run(sched.dequeue("default"))
    assert task is not None
    assert sched.fail(task["id"]) is True
    # Second attempt: dequeue, fail (retries=2, 2 not < 2 → exhausted)
    task = asyncio.run(sched.dequeue("default"))
    assert task is not None
    assert sched.fail(task["id"]) is False


def test_backoff_increases():
    sched = TaskScheduler(base_delay=1.0, max_delay=60.0)
    b1 = sched._compute_backoff(1)
    b2 = sched._compute_backoff(2)
    b3 = sched._compute_backoff(3)
    assert b2 > b1
    assert b3 > b2


def test_backoff_bounded():
    sched = TaskScheduler(base_delay=1.0, max_delay=5.0)
    b = sched._compute_backoff(10)
    assert b >= 1.0
    assert b <= 10.0


def test_jitter_randomness():
    sched = TaskScheduler(base_delay=10.0, max_delay=60.0)
    results = set()
    for _ in range(20):
        results.add(round(sched._compute_backoff(1), 1))
    assert len(results) > 1


def test_fail_with_jitter_delegates():
    sched = TaskScheduler(max_retries=3)
    tid = sched.enqueue({"name": "test"}, "default")
    task = asyncio.run(sched.dequeue("default"))
    assert task is not None
    assert sched.fail_with_jitter(task["id"]) is True


def test_custom_max_retries():
    sched = TaskScheduler(max_retries=5)
    sched.enqueue({"name": "test"}, "default")
    # 4 fails with max_retries=5 → 4 < 5 → all re-enqueued
    for i in range(4):
        task = asyncio.run(sched.dequeue("default"))
        assert task is not None, f"dequeue failed at iteration {i}"
        assert sched.fail(task["id"]) is True, f"fail failed at iteration {i}"
    # 5th fail: retries=5, 5 not < 5 → exhausted
    task = asyncio.run(sched.dequeue("default"))
    assert task is not None
    assert sched.fail(task["id"]) is False


def test_next_retry_at_set():
    sched = TaskScheduler(base_delay=1.0)
    sched.enqueue({"name": "test"}, "default")
    task = asyncio.run(sched.dequeue("default"))
    assert task is not None
    sched.fail(task["id"])
    task2 = asyncio.run(sched.dequeue("default"))
    assert task2 is not None
    assert "next_retry_at" in task2
    assert task2["next_retry_at"] > time.time()
