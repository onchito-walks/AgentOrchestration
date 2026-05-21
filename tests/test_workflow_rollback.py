"""Tests for WorkflowManager with RollbackState and downstream blocking."""

import pytest
from src.orchestrator.workflow import (
    RollbackState,
    StepStatus,
    Workflow,
    WorkflowManager,
    WorkflowStep,
)
from src.common.errors import WorkflowExecutionError


# ── Helpers ──────────────────────────────────────────────────────────

def _ok_handler():
    """Handler that always succeeds."""
    return "ok"


def _fail_handler():
    """Handler that always raises."""
    raise RuntimeError("step failed")


# ── RollbackState enum ───────────────────────────────────────────────

class TestRollbackState:
    def test_has_three_members(self):
        assert len(RollbackState) == 3

    def test_no_rollback_is_default(self):
        assert RollbackState.NO_ROLLBACK.value == 1
        assert RollbackState.PARTIAL_ROLLBACK.value == 2
        assert RollbackState.FULL_ROLLBACK.value == 3


# ── Workflow dependencies ────────────────────────────────────────────

class TestWorkflowDependencies:
    def test_add_dependency(self):
        wf = Workflow("child")
        wf.add_dependency("upstream-123")
        assert wf.depends_on == ["upstream-123"]

    def test_add_dependency_idempotent(self):
        wf = Workflow("child")
        wf.add_dependency("upstream-123")
        wf.add_dependency("upstream-123")
        assert wf.depends_on == ["upstream-123"]

    def test_add_dependency_multiple(self):
        wf = Workflow("child")
        wf.add_dependency("a").add_dependency("b").add_dependency("c")
        assert wf.depends_on == ["a", "b", "c"]

    def test_add_dependency_fluent(self):
        wf = Workflow("child")
        returned = wf.add_dependency("upstream-123")
        assert returned is wf


# ── Rollback state management ───────────────────────────────────────

class TestRollbackStateManagement:
    def setup_method(self):
        self.mgr = WorkflowManager()

    def test_default_is_no_rollback(self):
        wf = self.mgr.create_workflow("test")
        assert self.mgr.get_rollback_state(wf.id) == RollbackState.NO_ROLLBACK

    def test_default_for_unknown_workflow(self):
        assert self.mgr.get_rollback_state("nonexistent") == RollbackState.NO_ROLLBACK

    def test_set_rollback_state(self):
        wf = self.mgr.create_workflow("test")
        self.mgr.set_rollback_state(wf.id, RollbackState.FULL_ROLLBACK)
        assert self.mgr.get_rollback_state(wf.id) == RollbackState.FULL_ROLLBACK

    def test_set_rollback_unknown_workflow_is_noop(self):
        self.mgr.set_rollback_state("nonexistent", RollbackState.PARTIAL_ROLLBACK)
        # Should not raise; no state written
        assert self.mgr.get_rollback_state("nonexistent") == RollbackState.NO_ROLLBACK

    def test_delete_workflow_clears_rollback_state(self):
        wf = self.mgr.create_workflow("test")
        self.mgr.set_rollback_state(wf.id, RollbackState.PARTIAL_ROLLBACK)
        self.mgr.delete_workflow(wf.id)
        assert self.mgr.get_rollback_state(wf.id) == RollbackState.NO_ROLLBACK


# ── Successful execution ─────────────────────────────────────────────

class TestSuccessfulExecution:
    def setup_method(self):
        self.mgr = WorkflowManager()

    def test_execute_simple_workflow(self):
        wf = self.mgr.create_workflow("simple")
        wf.add_step(WorkflowStep("step1", _ok_handler))
        assert self.mgr.execute_workflow(wf.id) is True
        assert wf.status == StepStatus.COMPLETED
        assert self.mgr.get_rollback_state(wf.id) == RollbackState.NO_ROLLBACK

    def test_execute_multi_step_workflow(self):
        wf = self.mgr.create_workflow("multi")
        wf.add_step(WorkflowStep("step1", _ok_handler))
        wf.add_step(WorkflowStep("step2", _ok_handler))
        wf.add_step(WorkflowStep("step3", _ok_handler))
        assert self.mgr.execute_workflow(wf.id) is True
        assert all(s.status == StepStatus.COMPLETED for s in wf.steps)
        assert self.mgr.get_rollback_state(wf.id) == RollbackState.NO_ROLLBACK

    def test_execute_unknown_workflow_returns_false(self):
        assert self.mgr.execute_workflow("nonexistent") is False


# ── Failed execution → PARTIAL_ROLLBACK ─────────────────────────────

class TestFailedExecution:
    def setup_method(self):
        self.mgr = WorkflowManager()

    def test_failed_step_triggers_partial_rollback(self):
        wf = self.mgr.create_workflow("failing")
        wf.add_step(WorkflowStep("step1", _ok_handler))
        wf.add_step(WorkflowStep("step2", _fail_handler))
        assert self.mgr.execute_workflow(wf.id) is False
        assert wf.status == StepStatus.FAILED
        assert self.mgr.get_rollback_state(wf.id) == RollbackState.PARTIAL_ROLLBACK
        # First step completed, second failed
        assert wf.steps[0].status == StepStatus.COMPLETED
        assert wf.steps[1].status == StepStatus.FAILED

    def test_subsequent_steps_skipped_on_failure(self):
        wf = self.mgr.create_workflow("skip-after-fail")
        wf.add_step(WorkflowStep("step1", _fail_handler))
        wf.add_step(WorkflowStep("step2", _ok_handler))
        self.mgr.execute_workflow(wf.id)
        # step2 should never have run
        assert wf.steps[1].status == StepStatus.PENDING


# ── Downstream blocking ──────────────────────────────────────────────

class TestDownstreamBlocking:
    def setup_method(self):
        self.mgr = WorkflowManager()

    def test_downstream_blocked_by_partial_rollback(self):
        upstream = self.mgr.create_workflow("upstream")
        downstream = self.mgr.create_workflow("downstream")
        downstream.add_dependency(upstream.id)

        # Upstream fails → PARTIAL_ROLLBACK
        upstream.add_step(WorkflowStep("fail", _fail_handler))
        self.mgr.execute_workflow(upstream.id)
        assert self.mgr.get_rollback_state(upstream.id) == RollbackState.PARTIAL_ROLLBACK

        # Downstream should be blocked
        downstream.add_step(WorkflowStep("step", _ok_handler))
        with pytest.raises(WorkflowExecutionError) as exc:
            self.mgr.execute_workflow(downstream.id)
        assert "upstream" in str(exc.value)
        assert "PARTIAL_ROLLBACK" in str(exc.value)

    def test_downstream_not_blocked_when_upstream_succeeds(self):
        upstream = self.mgr.create_workflow("upstream")
        downstream = self.mgr.create_workflow("downstream")
        downstream.add_dependency(upstream.id)

        # Upstream succeeds
        upstream.add_step(WorkflowStep("ok", _ok_handler))
        assert self.mgr.execute_workflow(upstream.id) is True

        # Downstream should run fine
        downstream.add_step(WorkflowStep("ok", _ok_handler))
        assert self.mgr.execute_workflow(downstream.id) is True
        assert downstream.status == StepStatus.COMPLETED

    def test_independent_workflow_not_blocked(self):
        failed = self.mgr.create_workflow("failed")
        independent = self.mgr.create_workflow("independent")

        failed.add_step(WorkflowStep("fail", _fail_handler))
        self.mgr.execute_workflow(failed.id)
        assert self.mgr.get_rollback_state(failed.id) == RollbackState.PARTIAL_ROLLBACK

        # independent has no dependency — should run fine
        independent.add_step(WorkflowStep("ok", _ok_handler))
        assert self.mgr.execute_workflow(independent.id) is True

    def test_chain_blocked_by_upstream_via_intermediate(self):
        root = self.mgr.create_workflow("root")
        mid = self.mgr.create_workflow("mid")
        leaf = self.mgr.create_workflow("leaf")
        mid.add_dependency(root.id)
        leaf.add_dependency(mid.id)

        root.add_step(WorkflowStep("fail", _fail_handler))
        self.mgr.execute_workflow(root.id)

        leaf.add_step(WorkflowStep("ok", _ok_handler))
        with pytest.raises(WorkflowExecutionError) as exc:
            self.mgr.execute_workflow(leaf.id)
        assert "PARTIAL_ROLLBACK" in str(exc.value)

    def test_blocked_chain_after_upstream_recovery(self):
        upstream = self.mgr.create_workflow("upstream")
        downstream = self.mgr.create_workflow("downstream")
        downstream.add_dependency(upstream.id)

        # Fail upstream
        upstream.add_step(WorkflowStep("fail", _fail_handler))
        self.mgr.execute_workflow(upstream.id)

        # Manually recover: clear rollback state
        self.mgr.set_rollback_state(upstream.id, RollbackState.NO_ROLLBACK)

        # Now downstream should work
        downstream.add_step(WorkflowStep("ok", _ok_handler))
        assert self.mgr.execute_workflow(downstream.id) is True

    def test_self_reference_not_blocked(self):
        """A workflow should not block itself (no self-dependency by default)."""
        wf = self.mgr.create_workflow("self")
        wf.add_step(WorkflowStep("ok", _ok_handler))
        assert self.mgr.execute_workflow(wf.id) is True

    def test_cycle_in_dependency_graph_does_not_hang(self):
        a = self.mgr.create_workflow("a")
        b = self.mgr.create_workflow("b")
        a.add_dependency(b.id)
        b.add_dependency(a.id)  # cycle!

        a.add_step(WorkflowStep("ok", _ok_handler))
        b.add_step(WorkflowStep("ok", _ok_handler))

        # Should not deadlock — cycle is handled gracefully
        assert self.mgr.execute_workflow(a.id) is True
        assert self.mgr.execute_workflow(b.id) is True


# ── list_blocked_workflows ───────────────────────────────────────────

class TestListBlocked:
    def setup_method(self):
        self.mgr = WorkflowManager()

    def test_list_blocked_returns_empty_when_clean(self):
        a = self.mgr.create_workflow("a")
        b = self.mgr.create_workflow("b")
        b.add_dependency(a.id)
        a.add_step(WorkflowStep("ok", _ok_handler))
        self.mgr.execute_workflow(a.id)
        assert self.mgr.list_blocked_workflows() == {}

    def test_list_blocked_returns_blocked_workflows(self):
        up = self.mgr.create_workflow("upstream")
        down = self.mgr.create_workflow("downstream")
        down.add_dependency(up.id)

        up.add_step(WorkflowStep("fail", _fail_handler))
        self.mgr.execute_workflow(up.id)

        blocked = self.mgr.list_blocked_workflows()
        assert "downstream" in blocked
        assert "upstream" in blocked["downstream"]

    def test_list_blocked_excludes_independent(self):
        up = self.mgr.create_workflow("upstream")
        down = self.mgr.create_workflow("downstream")
        indep = self.mgr.create_workflow("independent")
        down.add_dependency(up.id)

        up.add_step(WorkflowStep("fail", _fail_handler))
        self.mgr.execute_workflow(up.id)
        indep.add_step(WorkflowStep("ok", _ok_handler))
        self.mgr.execute_workflow(indep.id)

        blocked = self.mgr.list_blocked_workflows()
        assert "downstream" in blocked
        assert "independent" not in blocked


# ── Verifying error class ────────────────────────────────────────────

class TestWorkflowExecutionError:
    def test_error_attributes(self):
        err = WorkflowExecutionError("my-wf", "something broke")
        assert err.workflow_name == "my-wf"
        assert err.reason == "something broke"
        assert "my-wf" in str(err)
        assert "something broke" in str(err)

    def test_is_agent_orchestrator_error(self):
        from src.common.errors import AgentOrchestratorError
        assert issubclass(WorkflowExecutionError, AgentOrchestratorError)
