import pytest
from src.common.metrics import MetricsCollector


class TestMetricsCollector:
    def setup_method(self):
        self.metrics = MetricsCollector()

    def test_increment(self):
        self.metrics.increment("requests.total")
        self.metrics.increment("requests.total")
        snapshot = self.metrics.snapshot()
        assert snapshot["counters"]["requests.total"] == 2

    def test_gauge(self):
        self.metrics.gauge("memory.usage", 85.5)
        snapshot = self.metrics.snapshot()
        assert snapshot["gauges"]["memory.usage"] == 85.5

    def test_observe(self):
        self.metrics.observe("response.time", 0.5)
        self.metrics.observe("response.time", 1.5)
        snapshot = self.metrics.snapshot()
        assert snapshot["histograms"]["response.time"]["count"] == 2
        assert snapshot["histograms"]["response.time"]["avg"] == 1.0

    def test_timer(self):
        self.metrics.start_timer("operation")
        import time
        time.sleep(0.01)
        duration = self.metrics.stop_timer("operation")
        assert duration > 0.005

# 2019-07-16T09:29:21 update

# 2019-09-09T13:35:42 update

# 2019-09-27T12:32:57 update

# 2019-10-31T18:15:44 update

# 2019-12-03T08:48:09 update

# 2019-12-12T14:59:28 update

# 2019-12-17T08:03:25 update

# 2020-03-13T11:30:29 update

# 2020-03-18T08:01:30 update

# 2020-04-15T20:08:39 update

# 2020-04-15T17:28:05 update

# 2020-10-05T20:20:34 update

# 2020-10-20T13:35:37 update

# 2020-11-13T10:55:30 update

# 2021-05-30T18:22:53 update

# 2021-06-10T12:21:04 update

# 2021-07-30T14:21:13 update
