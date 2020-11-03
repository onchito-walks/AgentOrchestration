"""SDK decorators for agent definitions."""

import functools
import asyncio
from typing import Any, Callable, Dict, Optional


def task(name: Optional[str] = None, retries: int = 0, timeout: int = 300):
    """Decorator for marking a method as an agent task handler."""
    def decorator(func: Callable) -> Callable:
        func.__task_config__ = {
            "name": name or func.__name__,
            "retries": retries,
            "timeout": timeout,
        }

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout,
                )
                return result
            except asyncio.TimeoutError:
                raise TimeoutError(f"Task {name or func.__name__} timed out after {timeout}s")

        return wrapper
    return decorator


def agent(name: str, version: str = "1.0.0", description: str = ""):
    """Decorator for marking a class as an agent definition."""
    def decorator(cls: type) -> type:
        cls.__agent_config__ = {
            "name": name,
            "version": version,
            "description": description,
        }
        return cls
    return decorator


def on_event(event_type: str):
    """Decorator for marking a method as an event handler."""
    def decorator(func: Callable) -> Callable:
        func.__event_handler__ = event_type

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper
    return decorator

# 2019-02-22T08:31:24 update

# 2019-03-27T17:49:45 update

# 2019-04-26T20:56:33 update

# 2019-11-05T08:00:55 update

# 2019-12-13T17:07:09 update

# 2020-02-06T20:25:27 update

# 2020-03-10T18:13:51 update

# 2020-04-17T08:18:59 update

# 2020-05-05T16:39:20 update

# 2020-05-20T09:01:41 update

# 2020-08-03T20:45:44 update

# 2020-08-11T10:42:34 update

# 2020-10-16T11:04:50 update

# 2020-10-29T16:52:19 update

# 2020-11-03T17:26:30 update
