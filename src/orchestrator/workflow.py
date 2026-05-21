"""Workflow Manager — Defines and executes multi-step agent workflows.

Supports dependency chaining between workflows and blocks downstream
execution when an upstream workflow is in PARTIAL_ROLLBACK state.
"""

from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from src.common.errors import DuplicateNodeError
from src.orchestrator.yaml_loader import load_workflow_from_yaml, load_workflow_from_yaml_string


def _make_noop_handler(name: str) -> Callable:
    """Create a no-op callable that logs the handler name when invoked."""
    import logging
    logger = logging.getLogger(__name__)

    def handler() -> str:
        logger.info("Executing stub handler: %s", name)
        return f"stub:{name}"
    return handler


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RollbackState(Enum):
    """Tracks rollback status of a completed or failed workflow.

    NO_ROLLBACK     — workflow ran cleanly or hasn't started
    PARTIAL_ROLLBACK — workflow failed mid-execution; some steps committed
                      state before the failure. Downstream workflows
                      that depend on this one are blocked.
    FULL_ROLLBACK   — workflow was fully rolled back (manual recovery).
                      Downstream is still blocked until NO_ROLLBACK.
    """
    NO_ROLLBACK = auto()
    PARTIAL_ROLLBACK = auto()
    FULL_ROLLBACK = auto()


class WorkflowStep:
    def __init__(self, name: str, handler: Callable, retries: int = 0, timeout: int = 300):
        self.id = str(uuid4())
        self.name = name
        self.handler = handler
        self.retries = retries
        self.timeout = timeout
        self.status = StepStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None


class Workflow:
    def __init__(self, name: str, description: str = ""):
        self.id = str(uuid4())
        self.name = name
        self.description = description
        self.steps: List[WorkflowStep] = []
        self._step_map: Dict[str, WorkflowStep] = {}
        self._step_names: Set[str] = set()
        self.status = StepStatus.PENDING
        self.depends_on: List[str] = []  # IDs of upstream workflows

    def add_step(self, step: WorkflowStep) -> "Workflow":
        if step.name in self._step_names:
            raise DuplicateNodeError(
                step.name,
                f"step already registered in workflow '{self.name}'",
            )
        self.steps.append(step)
        self._step_map[step.id] = step
        self._step_names.add(step.name)
        return self

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        return self._step_map.get(step_id)

    def add_dependency(self, workflow_id: str) -> "Workflow":
        """Declare that this workflow depends on *workflow_id* completing first.

        When the upstream workflow fails and enters PARTIAL_ROLLBACK,
        this workflow cannot execute until it is resolved.
        """
        if workflow_id not in self.depends_on:
            self.depends_on.append(workflow_id)
        return self


class WorkflowManager:
    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}
        self._rollback_states: Dict[str, RollbackState] = {}

    # ── CRUD ────────────────────────────────────────────────────────

    def create_workflow(self, name: str, description: str = "") -> Workflow:
        workflow = Workflow(name, description)
        self._workflows[workflow.id] = workflow
        return workflow

    def create_workflow_from_yaml(
        self,
        path: str,
        search_paths: Optional[List[str]] = None,
    ) -> Workflow:
        """Load a workflow definition from a YAML file with import
        expansion and duplicate node ID rejection.

        Returns a fully-constructed ``Workflow`` with all steps added.
        Raises ``DuplicateNodeError`` if duplicate node IDs are found.
        """
        data = load_workflow_from_yaml(path, search_paths)
        return self._build_from_dict(data)

    def create_workflow_from_yaml_string(
        self,
        yaml_text: str,
        source_name: str = "<inline>",
        search_paths: Optional[List[str]] = None,
    ) -> Workflow:
        """Same as ``create_workflow_from_yaml`` but from a raw YAML string."""
        data = load_workflow_from_yaml_string(yaml_text, source_name, search_paths)
        return self._build_from_dict(data)

    def _build_from_dict(self, data: Dict[str, Any]) -> Workflow:
        """Internal: construct a ``Workflow`` from a validated dict with
        ``name``, ``description``, ``steps``, and ``nodes`` keys,
        and register it with the manager.
        """
        name = data.get("name", "unnamed")
        description = data.get("description", "")
        workflow = Workflow(name, description)

        steps = data.get("steps", [])
        for s in steps:
            handler_name = s.get("handler", "noop")
            step = WorkflowStep(
                name=s.get("name", s.get("id", "unnamed")),
                handler=_make_noop_handler(handler_name),
                retries=s.get("retries", 0),
                timeout=s.get("timeout", 300),
            )
            workflow.add_step(step)

        # Register the workflow so it is discoverable via get_workflow()
        self._workflows[workflow.id] = workflow

        # Node entries (decision nodes, etc.) are validated for
        # duplicates but don't become WorkflowStep objects here — they
        # are preserved for future routing logic.
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[Workflow]:
        return list(self._workflows.values())

    def delete_workflow(self, workflow_id: str) -> bool:
        self._rollback_states.pop(workflow_id, None)
        return self._workflows.pop(workflow_id, None) is not None

    # ── Rollback state management ───────────────────────────────────

    def get_rollback_state(self, workflow_id: str) -> RollbackState:
        """Return the current rollback state for a workflow.

        Defaults to NO_ROLLBACK for workflows that have never failed or
        that have not been registered in the rollback tracker.
        """
        return self._rollback_states.get(workflow_id, RollbackState.NO_ROLLBACK)

    def set_rollback_state(self, workflow_id: str, state: RollbackState) -> None:
        """Manually set rollback state (e.g. for recovery after manual fix)."""
        if workflow_id in self._workflows:
            self._rollback_states[workflow_id] = state

    def list_blocked_workflows(self) -> Dict[str, str]:
        """Return {workflow_name: blocking_workflow_name} for every workflow
        currently blocked by an upstream partial rollback.
        """
        blocked: Dict[str, str] = {}
        for wf_id, wf in self._workflows.items():
            blocker = self._has_blocking_rollback_in_chain(wf_id)
            if blocker:
                blocker_wf = self._workflows.get(blocker)
                blocked[wf.name] = blocker_wf.name if blocker_wf else blocker
        return blocked

    # ── Dependency chain inspection ─────────────────────────────────

    def _has_blocking_rollback_in_chain(
        self, workflow_id: str, visited: Optional[Set[str]] = None
    ) -> Optional[str]:
        """Walk the dependency chain upward from *workflow_id*.

        Returns the *first* upstream workflow ID whose rollback state is
        PARTIAL_ROLLBACK (or FULL_ROLLBACK), or None if the chain is clean.

        Cycle-safe: if a dependency is re-visited the walk stops for that
        branch (returns None, same as 'clean').
        """
        if visited is None:
            visited = set()

        # Check self
        if workflow_id in visited:
            return None  # cycle guard
        visited.add(workflow_id)

        state = self._rollback_states.get(workflow_id, RollbackState.NO_ROLLBACK)
        if state in (RollbackState.PARTIAL_ROLLBACK, RollbackState.FULL_ROLLBACK):
            return workflow_id

        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return None

        for dep_id in workflow.depends_on:
            blocker = self._has_blocking_rollback_in_chain(dep_id, visited.copy())
            if blocker:
                return blocker

        return None

    # ── Workflow execution ──────────────────────────────────────────

    def execute_workflow(self, workflow_id: str) -> bool:
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        # ── Gate: reject if an upstream dependency is in rollback ──
        blocker_id = self._has_blocking_rollback_in_chain(workflow_id)
        if blocker_id:
            blocker_wf = self._workflows.get(blocker_id)
            blocker_name = blocker_wf.name if blocker_wf else blocker_id
            from src.common.errors import WorkflowExecutionError
            raise WorkflowExecutionError(
                workflow.name,
                f"upstream workflow '{blocker_name}' is in "
                f"{self._rollback_states.get(blocker_id, RollbackState.PARTIAL_ROLLBACK).name} "
                f"state — cannot execute until resolved",
            )

        # ── Execute steps sequentially ─────────────────────────────
        workflow.status = StepStatus.RUNNING
        for step in workflow.steps:
            step.status = StepStatus.RUNNING
            try:
                result = step.handler()
                step.result = result
                step.status = StepStatus.COMPLETED
            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
                workflow.status = StepStatus.FAILED
                self._rollback_states[workflow_id] = RollbackState.PARTIAL_ROLLBACK
                return False

        workflow.status = StepStatus.COMPLETED
        self._rollback_states[workflow_id] = RollbackState.NO_ROLLBACK
        return True
