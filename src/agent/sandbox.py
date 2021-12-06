"""Agent Sandbox — Isolated execution environment for agents."""

import os
import tempfile
import resource
from typing import Dict, Optional
from pathlib import Path


class ResourceLimits:
    def __init__(self, cpu_time: int = 60, memory_mb: int = 512, disk_mb: int = 100):
        self.cpu_time = cpu_time
        self.memory_mb = memory_mb
        self.disk_mb = disk_mb


class AgentSandbox:
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or tempfile.mkdtemp(prefix="ao_sandbox_"))
        self._sandboxes: Dict[str, Path] = {}

    def create(self, agent_id: str, limits: Optional[ResourceLimits] = None) -> Path:
        sandbox_path = self.base_path / agent_id
        sandbox_path.mkdir(parents=True, exist_ok=True)
        self._sandboxes[agent_id] = sandbox_path
        return sandbox_path

    def destroy(self, agent_id: str) -> bool:
        sandbox = self._sandboxes.pop(agent_id, None)
        if sandbox and sandbox.exists():
            import shutil
            shutil.rmtree(sandbox, ignore_errors=True)
            return True
        return False

    def get_path(self, agent_id: str) -> Optional[Path]:
        return self._sandboxes.get(agent_id)

    def apply_limits(self, agent_id: str, limits: ResourceLimits) -> None:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_time, limits.cpu_time))
            mem_bytes = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, resource.error) as e:
            pass

    def cleanup_all(self) -> None:
        for agent_id in list(self._sandboxes.keys()):
            self.destroy(agent_id)

# 2019-01-10T19:56:24 update

# 2019-02-07T17:00:55 update

# 2019-05-15T17:22:36 update

# 2019-06-14T10:08:48 update

# 2019-06-21T11:59:12 update

# 2019-06-26T13:24:25 update

# 2019-07-05T09:17:12 update

# 2019-07-09T11:23:07 update

# 2019-07-10T16:17:07 update

# 2019-08-15T10:32:06 update

# 2019-08-18T17:28:35 update

# 2019-10-15T13:00:49 update

# 2019-10-25T10:56:15 update

# 2020-01-10T10:39:46 update

# 2020-01-27T13:05:12 update

# 2020-04-16T14:16:09 update

# 2020-05-20T14:43:03 update

# 2020-06-16T20:48:15 update

# 2020-07-03T20:44:23 update

# 2020-07-13T20:07:35 update

# 2020-07-16T14:18:50 update

# 2020-08-04T18:59:59 update

# 2020-08-31T11:47:49 update

# 2020-09-07T16:04:09 update

# 2020-10-27T16:57:05 update

# 2021-02-09T15:01:25 update

# 2021-03-25T08:24:03 update

# 2021-06-16T13:38:08 update

# 2021-06-29T08:07:27 update

# 2021-08-13T12:17:43 update

# 2021-09-01T17:41:43 update

# 2021-09-08T10:52:46 update

# 2021-10-19T13:52:01 update

# 2021-12-02T14:43:57 update

# 2021-12-05T11:58:00 update

# 2021-12-06T16:06:43 update
