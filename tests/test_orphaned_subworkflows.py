"""Tests for orphaned subworkflow prevention (#1040)."""
import pytest
from src.orchestrator.engine import OrchestrationEngine


class TestOrphanedSubworkflows:
    def setup_method(self):
        self.engine = OrchestrationEngine()

    def test_spawn_subworkflow_tracks_parent_child(self):
        """Spawning a subworkflow must register the parent-child link."""
        parent_id = "parent-1"
        child_id = self.engine.spawn_subworkflow(parent_id, {"target_agent": "agent-a", "name": "child"})
        assert child_id is not None
        assert parent_id in self.engine._parent_map
        assert child_id in self.engine._parent_map[parent_id]
        assert self.engine._child_parent[child_id] == parent_id

    def test_cancel_orphaned_cleans_children(self):
        """Cancelling orphaned subworkflows must clean up all tracking."""
        parent_id = "parent-2"
        c1 = self.engine.spawn_subworkflow(parent_id, {"target_agent": "a", "name": "c1"})
        c2 = self.engine.spawn_subworkflow(parent_id, {"target_agent": "b", "name": "c2"})
        assert len(self.engine._parent_map[parent_id]) == 2

        self.engine._cancel_orphaned_children(parent_id)
        assert parent_id not in self.engine._parent_map
        assert c1 not in self.engine._child_parent
        assert c2 not in self.engine._child_parent

    def test_multiple_parents_independent(self):
        """Cancelling one parent's children must not affect another parent's."""
        p1 = "parent-a"
        p2 = "parent-b"
        c1 = self.engine.spawn_subworkflow(p1, {"target_agent": "a", "name": "c1"})
        c2 = self.engine.spawn_subworkflow(p2, {"target_agent": "b", "name": "c2"})

        self.engine._cancel_orphaned_children(p1)
        assert p2 in self.engine._parent_map
        assert c2 in self.engine._child_parent
