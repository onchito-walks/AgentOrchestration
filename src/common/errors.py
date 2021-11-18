"""Custom exception definitions."""


class AgentOrchestratorError(Exception):
    """Base exception for all platform errors."""
    pass


class AgentNotFoundError(AgentOrchestratorError):
    def __init__(self, agent_id: str):
        super().__init__(f"Agent not found: {agent_id}")


class AgentTimeoutError(AgentOrchestratorError):
    def __init__(self, agent_id: str, timeout: int):
        super().__init__(f"Agent {agent_id} timed out after {timeout}s")


class TaskExecutionError(AgentOrchestratorError):
    def __init__(self, task_id: str, reason: str):
        super().__init__(f"Task {task_id} failed: {reason}")


class ConfigurationError(AgentOrchestratorError):
    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}")


class AuthenticationError(AgentOrchestratorError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class RateLimitError(AgentOrchestratorError):
    def __init__(self, retry_after: int = 60):
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")
        self.retry_after = retry_after


class ResourceExhaustedError(AgentOrchestratorError):
    def __init__(self, resource: str):
        super().__init__(f"Resource exhausted: {resource}")

# 2019-01-25T13:21:06 update

# 2019-02-15T19:31:32 update

# 2019-03-18T12:12:35 update

# 2019-04-29T20:33:13 update

# 2019-05-13T10:17:52 update

# 2019-08-08T11:13:54 update

# 2019-10-03T13:18:53 update

# 2019-12-25T12:36:57 update

# 2020-01-08T20:51:36 update

# 2020-02-04T16:32:04 update

# 2020-02-14T20:25:19 update

# 2020-05-13T17:33:02 update

# 2020-05-21T08:58:23 update

# 2020-06-17T19:16:10 update

# 2020-06-29T08:36:22 update

# 2020-09-15T17:03:38 update

# 2021-07-29T17:26:45 update

# 2021-09-09T14:13:15 update

# 2021-09-29T15:38:28 update

# 2021-10-26T11:39:45 update

# 2021-10-29T15:26:37 update

# 2021-11-11T16:23:02 update

# 2021-11-18T10:30:52 update
