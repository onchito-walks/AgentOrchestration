"""Metrics collection and reporting."""

import time
from collections import defaultdict
from typing import Dict, List
from threading import Lock


class MetricsCollector:
    def __init__(self):
        self._lock = Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timers: Dict[str, float] = {}

    def increment(self, metric: str, value: int = 1) -> None:
        with self._lock:
            self._counters[metric] += value

    def gauge(self, metric: str, value: float) -> None:
        with self._lock:
            self._gauges[metric] = value

    def observe(self, metric: str, value: float) -> None:
        with self._lock:
            self._histograms[metric].append(value)

    def start_timer(self, metric: str) -> None:
        with self._lock:
            self._timers[metric] = time.time()

    def stop_timer(self, metric: str) -> float:
        with self._lock:
            if metric in self._timers:
                duration = time.time() - self._timers.pop(metric)
                self.observe(metric, duration)
                return duration
        return 0.0

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: {"count": len(v), "sum": sum(v), "avg": sum(v) / len(v) if v else 0}
                               for k, v in self._histograms.items()},
            }


metrics = MetricsCollector()

# 2019-01-01T14:07:11 update

# 2019-02-19T09:42:37 update

# 2019-02-20T11:46:45 update

# 2019-03-19T17:25:17 update

# 2019-05-16T12:48:17 update

# 2019-06-20T11:04:52 update
