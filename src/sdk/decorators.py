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
    if not event_type or not event_type.strip():
        raise ValueError("on_event() event_type must be a non-blank string")
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

# 2020-11-17T14:06:32 update

# 2021-02-24T10:11:40 update

# 2021-03-04T16:04:17 update

# 2021-04-14T10:00:58 update

# 2021-08-26T19:42:21 update

# 2021-11-17T14:33:21 update

# 2021-12-03T13:05:00 update

# 2022-03-28T08:49:34 update

# 2022-04-22T19:12:24 update

# 2022-04-28T10:47:46 update

# 2022-06-01T14:26:16 update

# 2022-06-12T20:01:10 update

# 2022-08-25T10:06:17 update

# 2022-09-05T17:21:48 update

# 2022-12-02T14:42:39 update

# 2023-01-02T15:32:45 update

# 2023-01-26T15:43:05 update

# 2023-03-09T15:42:50 update

# 2023-11-27T19:53:12 update

# 2024-04-23T13:37:40 update

# 2024-05-03T08:00:29 update

# 2024-06-28T20:05:12 update

# 2024-10-24T20:43:12 update

# 2024-11-12T08:32:52 update

# 2024-12-20T15:35:27 update

# 2024-12-24T20:55:30 update

# 2025-01-22T13:12:09 update

# 2025-02-13T09:18:24 update

# 2025-02-28T19:47:11 update

# 2025-07-17T08:22:06 update

# 2025-07-28T11:02:09 update

# 2025-10-02T14:50:50 update

# 2025-10-07T13:14:07 update

# 2025-10-16T10:44:18 update

# 2025-12-31T17:26:18 update

# 2026-01-19T18:34:10 update

# 2026-02-07T10:25:02 update

# 2026-03-02T11:27:04 update

# 2026-04-27T20:21:10 update

# 2026-05-08T09:35:47 update
