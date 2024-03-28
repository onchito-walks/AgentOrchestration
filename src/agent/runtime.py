"""Agent Runtime — Manages agent process lifecycle."""

import os
import signal
import subprocess
import logging
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RuntimeState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"


class AgentRuntime:
    def __init__(self):
        self._processes: Dict[str, subprocess.Popen] = {}
        self._states: Dict[str, RuntimeState] = {}

    def start(self, agent_id: str, command: list, env: Optional[Dict] = None) -> bool:
        if agent_id in self._processes and self._processes[agent_id].poll() is None:
            logger.warning(f"Agent {agent_id} is already running")
            return False

        self._states[agent_id] = RuntimeState.STARTING
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process_env["AO_AGENT_ID"] = agent_id

        try:
            proc = subprocess.Popen(
                command,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._processes[agent_id] = proc
            self._states[agent_id] = RuntimeState.RUNNING
            logger.info(f"Agent {agent_id} started (PID: {proc.pid})")
            return True
        except Exception as e:
            self._states[agent_id] = RuntimeState.CRASHED
            logger.error(f"Failed to start agent {agent_id}: {e}")
            return False

    def stop(self, agent_id: str, timeout: int = 10) -> bool:
        proc = self._processes.get(agent_id)
        if not proc or proc.poll() is not None:
            return False

        self._states[agent_id] = RuntimeState.STOPPING
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        self._states[agent_id] = RuntimeState.STOPPED
        logger.info(f"Agent {agent_id} stopped")
        return True

    def get_state(self, agent_id: str) -> RuntimeState:
        proc = self._processes.get(agent_id)
        if proc and proc.poll() is not None:
            self._states[agent_id] = RuntimeState.CRASHED
        return self._states.get(agent_id, RuntimeState.STOPPED)

    def is_running(self, agent_id: str) -> bool:
        proc = self._processes.get(agent_id)
        return proc is not None and proc.poll() is None

# 2019-01-11T10:56:26 update

# 2019-01-22T16:22:30 update

# 2019-03-06T18:13:59 update

# 2019-03-15T11:30:26 update

# 2019-03-18T11:22:04 update

# 2019-03-29T09:30:22 update

# 2019-05-06T17:17:42 update

# 2019-07-08T10:46:12 update

# 2019-10-30T15:01:34 update

# 2019-11-21T11:46:57 update

# 2019-12-09T13:23:07 update

# 2020-02-18T14:01:01 update

# 2020-02-19T11:51:07 update

# 2020-02-27T18:21:42 update

# 2020-03-11T12:29:19 update

# 2020-04-13T09:40:09 update

# 2020-06-16T14:21:27 update

# 2020-08-12T12:56:50 update

# 2020-08-13T09:41:21 update

# 2020-09-10T08:08:18 update

# 2020-10-02T12:22:16 update

# 2020-10-14T13:05:00 update

# 2020-10-19T14:32:13 update

# 2021-02-11T08:23:22 update

# 2021-02-19T19:20:29 update

# 2021-03-24T19:22:02 update

# 2021-09-03T16:39:23 update

# 2021-10-11T10:52:21 update

# 2021-12-13T09:33:23 update

# 2022-01-04T11:11:07 update

# 2022-07-31T15:24:35 update

# 2022-08-05T19:33:09 update

# 2022-10-07T20:08:25 update

# 2022-10-20T09:57:32 update

# 2023-01-06T17:26:45 update

# 2023-01-12T18:21:36 update

# 2023-03-30T19:52:43 update

# 2023-06-06T16:53:33 update

# 2023-09-21T18:21:37 update

# 2024-01-02T10:34:11 update

# 2024-01-04T10:43:54 update

# 2024-03-28T11:14:49 update
