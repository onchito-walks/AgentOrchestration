"""Tests for artifact retention policy validation (bounty #1463)."""
import pytest
from src.orchestrator.workflow import Workflow, validate_retention_policy, MAX_RETENTION_DAYS


class TestValidateRetentionPolicy:
    def test_valid_retention(self):
        validate_retention_policy(30)
        validate_retention_policy(0)
        validate_retention_policy(MAX_RETENTION_DAYS)

    def test_negative_retention(self):
        with pytest.raises(ValueError, match=">= 0"):
            validate_retention_policy(-1)

    def test_excessive_retention(self):
        with pytest.raises(ValueError, match=f"<= {MAX_RETENTION_DAYS}"):
            validate_retention_policy(MAX_RETENTION_DAYS + 1)

    def test_non_integer_retention(self):
        with pytest.raises(ValueError, match="integer"):
            validate_retention_policy("30")
        with pytest.raises(ValueError, match="integer"):
            validate_retention_policy(30.5)

    def test_none_retention(self):
        with pytest.raises(ValueError, match="integer"):
            validate_retention_policy(None)

    def test_workflow_default_retention(self):
        wf = Workflow("test")
        assert wf.retention_days == 30

    def test_workflow_custom_retention(self):
        wf = Workflow("test", retention_days=90)
        assert wf.retention_days == 90

    def test_workflow_invalid_retention(self):
        with pytest.raises(ValueError, match=">= 0"):
            Workflow("test", retention_days=-5)
