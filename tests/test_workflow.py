"""Tests for duplicate node ID rejection in workflow registration (bounty #943 - $6K).

Covers:
- Workflow.add_step() duplicate name guard
- YAML inline duplicate detection
- YAML file-based import with duplicate detection
- WorkflowManager.create_workflow_from_yaml end-to-end
- Sanitised audit log messages (no runtime payload)
"""

import json
import logging
import os
import tempfile
from io import StringIO

import pytest
import yaml

from src.common.errors import DuplicateNodeError
from src.orchestrator.workflow import (
    Workflow,
    WorkflowManager,
    WorkflowStep,
)
from src.orchestrator.yaml_loader import (
    load_workflow_from_yaml,
    load_workflow_from_yaml_string,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def manager():
    return WorkflowManager()


# ── Workflow.add_step() duplicate name guard ───────────────────────


class TestAddStepDuplicateGuard:
    def test_duplicate_step_name_raises(self):
        wf = Workflow("test", "desc")
        step1 = WorkflowStep("step_one", lambda: None)
        wf.add_step(step1)

        step2 = WorkflowStep("step_one", lambda: "different")
        with pytest.raises(DuplicateNodeError) as exc:
            wf.add_step(step2)
        assert "step_one" in str(exc.value)
        assert "test" in str(exc.value)

    def test_unique_step_names_ok(self):
        wf = Workflow("test", "desc")
        wf.add_step(WorkflowStep("a", lambda: None))
        wf.add_step(WorkflowStep("b", lambda: None))
        wf.add_step(WorkflowStep("c", lambda: None))
        assert len(wf.steps) == 3

    def test_error_contains_node_id(self):
        wf = Workflow("err_test", "")
        wf.add_step(WorkflowStep("dup_me", lambda: None))
        with pytest.raises(DuplicateNodeError) as exc:
            wf.add_step(WorkflowStep("dup_me", lambda: None))
        assert exc.value.node_id == "dup_me"
        assert "err_test" in exc.value.context


# ── YAML inline duplicate detection ────────────────────────────────


class TestYamlInlineDedup:
    def test_duplicate_step_ids_in_single_yaml(self):
        yaml_text = """
        name: dup_test
        steps:
          - id: step_1
            name: First Step
          - id: step_2
            name: Second Step
          - id: step_1
            name: Duplicate!
        """
        with pytest.raises(DuplicateNodeError) as exc:
            load_workflow_from_yaml_string(yaml_text)
        assert "step_1" in str(exc.value)

    def test_duplicate_node_ids_in_single_yaml(self):
        yaml_text = """
        name: node_dup
        nodes:
          - id: decision_alpha
            type: switch
          - id: decision_beta
            type: action
          - id: decision_alpha
            type: another
        """
        with pytest.raises(DuplicateNodeError) as exc:
            load_workflow_from_yaml_string(yaml_text)
        assert "decision_alpha" in str(exc.value)

    def test_duplicate_across_steps_and_nodes_sections(self):
        yaml_text = """
        name: cross_section_dup
        steps:
          - id: shared_node
            name: Shared
        nodes:
          - id: shared_node
            type: decision
        """
        with pytest.raises(DuplicateNodeError) as exc:
            load_workflow_from_yaml_string(yaml_text)
        assert "shared_node" in str(exc.value)

    def test_no_duplicates(self):
        yaml_text = """
        name: clean
        steps:
          - id: step_a
            name: A
          - id: step_b
            name: B
        nodes:
          - id: node_x
            type: switch
        """
        result = load_workflow_from_yaml_string(yaml_text)
        assert len(result["steps"]) == 2
        assert len(result["nodes"]) == 1


# ── YAML file-based import with duplicate detection ────────────────


class TestYamlFileImports:
    def test_imported_and_local_duplicate(self):
        """Steps from an imported file that collide with local steps
        should be detected before registration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            imported = {
                "steps": [
                    {"id": "validate_input", "name": "Validate"},
                    {"id": "process_data", "name": "Process"},
                ]
            }
            imported_path = os.path.join(tmpdir, "shared.yaml")
            with open(imported_path, "w") as f:
                yaml.dump(imported, f)

            main = {
                "name": "main_wf",
                "imports": [{"path": os.path.join(tmpdir, "shared.yaml")}],
                "steps": [
                    {"id": "validate_input", "name": "Validate"},
                ],
            }
            main_path = os.path.join(tmpdir, "main.yaml")
            with open(main_path, "w") as f:
                yaml.dump(main, f)

            with pytest.raises(DuplicateNodeError) as exc:
                load_workflow_from_yaml(main_path)
            assert "validate_input" in str(exc.value)

    def test_no_duplicate_across_imports(self):
        """Distinct node IDs across import boundaries should succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            imported = {
                "steps": [
                    {"id": "imported_step", "name": "Imported"},
                ]
            }
            imp_path = os.path.join(tmpdir, "other.yaml")
            with open(imp_path, "w") as f:
                yaml.dump(imported, f)

            main = {
                "name": "multi_source",
                "imports": [{"path": os.path.join(tmpdir, "other.yaml")}],
                "steps": [
                    {"id": "local_step", "name": "Local"},
                ],
            }
            main_path = os.path.join(tmpdir, "multi.yaml")
            with open(main_path, "w") as f:
                yaml.dump(main, f)

            result = load_workflow_from_yaml(main_path)
            assert len(result["steps"]) == 2

    def test_circular_import_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            a_path = os.path.join(tmpdir, "a.yaml")
            b_path = os.path.join(tmpdir, "b.yaml")

            a_def = {
                "name": "a",
                "imports": [{"path": os.path.join(tmpdir, "b.yaml")}],
                "steps": [],
            }
            b_def = {
                "name": "b",
                "imports": [{"path": os.path.join(tmpdir, "a.yaml")}],
                "steps": [],
            }
            with open(a_path, "w") as f:
                yaml.dump(a_def, f)
            with open(b_path, "w") as f:
                yaml.dump(b_def, f)

            with pytest.raises(ValueError, match="Circular"):
                load_workflow_from_yaml(a_path)


# ── WorkflowManager end-to-end integration ─────────────────────────


class TestWorkflowManagerYaml:
    def test_create_from_yaml_string(self, manager):
        yaml_text = """
        name: test_wf
        steps:
          - id: step_1
            name: First
            retries: 2
            timeout: 60
          - id: step_2
            name: Second
        """
        wf = manager.create_workflow_from_yaml_string(yaml_text)
        assert wf.name == "test_wf"
        assert len(wf.steps) == 2
        assert wf.steps[0].name == "First"
        assert wf.steps[0].retries == 2
        assert wf.steps[0].timeout == 60
        assert wf.steps[1].name == "Second"

    def test_create_from_yaml_duplicate_rejected(self, manager):
        yaml_text = """
        name: dup_wf
        steps:
          - id: step_x
            name: X
          - id: step_y
            name: Y
          - id: step_x
            name: X_again
        """
        with pytest.raises(DuplicateNodeError):
            manager.create_workflow_from_yaml_string(yaml_text)

    def test_create_from_yaml_workflow_registered(self, manager):
        yaml_text = """
        name: registered_wf
        steps:
          - id: step_a
            name: StepA
        """
        wf = manager.create_workflow_from_yaml_string(yaml_text)
        # Verify the workflow was actually registered
        assert manager.get_workflow(wf.id) is not None
        assert manager.get_workflow(wf.id).name == "registered_wf"

    def test_duplicate_step_name_via_manager_add(self, manager):
        """Direct add_step (not via YAML) should also be guarded."""
        wf = manager.create_workflow("direct_wf")
        wf.add_step(WorkflowStep("unique_name", lambda: None))
        with pytest.raises(DuplicateNodeError):
            wf.add_step(WorkflowStep("unique_name", lambda: None))


# ── Audit log: no runtime payload in error messages ────────────────


class TestAuditLogSanitised:
    def test_error_message_does_not_leak_payload(self):
        """The error message should name the node ID and context but
        NOT include runtime payload data, tokens, or private data."""
        wf = Workflow("safe_wf")
        wf.add_step(WorkflowStep("my_step", lambda: None))
        try:
            wf.add_step(WorkflowStep("my_step", lambda: None))
        except DuplicateNodeError as e:
            msg = str(e)
            # Should contain node ID
            assert "my_step" in msg
            # Should NOT contain the handler lambda repr or similar
            assert "lambda" not in msg
            assert "function" not in msg
            assert "0x" not in msg  # no hex addresses

    def test_yaml_duplicate_audit_no_payload(self):
        """YAML duplicate error should reference the section but not
        the full YAML structure."""
        yaml_text = """
        name: audit_wf
        steps:
          - id: dup_target
            name: Target
          - id: dup_target
            name: Duplicate
        """
        try:
            load_workflow_from_yaml_string(yaml_text)
            pytest.fail("Expected DuplicateNodeError")
        except DuplicateNodeError as e:
            msg = str(e)
            assert "dup_target" in msg
            # Should reference the section without dumping YAML
            assert "steps" in msg or "nodes" in msg or "duplicate" in msg
