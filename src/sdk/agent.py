"""Base agent class for the Orchestrator SDK."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, agent_id: str, name: str, config: Optional[Dict] = None):
        self.agent_id = agent_id
        self.name = name
        self.config = config or {}
        self._running = False
        self._metadata: Dict[str, Any] = {}

    @abstractmethod
    async def setup(self) -> None:
        pass

    @abstractmethod
    async def handle_task(self, task: Dict[str, Any]) -> Any:
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        pass

    async def run(self) -> None:
        self._running = True
        await self.setup()
        logger.info(f"Agent {self.name} ({self.agent_id}) started")
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.cleanup()
            logger.info(f"Agent {self.name} stopped")

    def stop(self) -> None:
        self._running = False

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

# 2019-04-19T17:53:22 update

# 2019-05-21T12:12:13 update

# 2019-06-05T14:31:06 update

# 2019-08-19T14:06:12 update

# 2019-09-03T17:18:33 update

# 2019-09-25T19:10:47 update

# 2019-10-04T18:47:05 update
