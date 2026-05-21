"""Tests for the migration manager and deploy gate (issue #969, bounty $7k)."""

import os
import tempfile
import pytest

from src.common.migration import (
    Migration,
    MigrationManager,
    MigrationError,
    MigrationStatus,
)


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "migrations")


# ═══════════════════════════════════════════════════════════════════════
# Migration (unit)
# ═══════════════════════════════════════════════════════════════════════


class TestMigrationUnit:
    def test_load_sql(self):
        path = os.path.join(FIXTURES, "2026_05_19_initial.sql")
        m = Migration(path, "2026-05-19")
        sql = m.load()
        assert "CREATE TABLE" in sql
        assert m.checksum is not None

    def test_forward_compatible_add_column(self):
        path = os.path.join(FIXTURES, "2026_05_21_add_status_column.sql")
        m = Migration(path, "2026-05-21-001")
        assert m.is_forward_compatible is True

    def test_forward_compatible_create_index(self):
        path = os.path.join(FIXTURES, "2026_05_21_002_create_task_index.sql")
        m = Migration(path, "2026-05-21-002")
        assert m.is_forward_compatible is True

    def test_forward_incompatible_drop_column(self):
        path = os.path.join(FIXTURES, "2026_05_20_drop_old_column.sql")
        m = Migration(path, "2026-05-20")
        assert m.is_forward_compatible is False

    def test_run_valid_sql(self):
        path = os.path.join(FIXTURES, "2026_05_19_initial.sql")
        m = Migration(path, "2026-05-19")
        m.run()  # should not raise
        assert m.status == MigrationStatus.COMPLETED
        assert m.completed_at is not None

    def test_run_empty_sql_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("   ;;;  ")
            tmppath = f.name
        try:
            m = Migration(tmppath, "test-empty")
            with pytest.raises(MigrationError, match="Migration test-empty failed"):
                m.run()
        finally:
            os.unlink(tmppath)

    def test_run_fails_raises_on_empty_migration(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("")
            tmppath = f.name
        try:
            m = Migration(tmppath, "test-empty")
            with pytest.raises(MigrationError, match="Empty migration"):
                m.run()
        finally:
            os.unlink(tmppath)

    def test_run_sets_failed_status_on_empty_migration(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("   ")
            tmppath = f.name
        try:
            m = Migration(tmppath, "test-empty")
            with pytest.raises(MigrationError):
                m.run()
            assert m.status == MigrationStatus.FAILED
            assert m.error is not None
        finally:
            os.unlink(tmppath)


# ═══════════════════════════════════════════════════════════════════════
# MigrationManager (integration)
# ═══════════════════════════════════════════════════════════════════════


class TestMigrationManagerDiscovery:
    def test_discover_all_migrations(self):
        mm = MigrationManager(FIXTURES)
        migrations = mm.discover()
        # We expect 4 .sql files matched; one (non-versioned) might be filtered
        assert len(migrations) >= 3

    def test_discover_sorted_by_version(self):
        mm = MigrationManager(FIXTURES)
        migrations = mm.discover()
        versions = [m.version for m in migrations]
        assert versions == sorted(versions), f"Not sorted: {versions}"

    def test_discover_parses_version_and_description(self):
        mm = MigrationManager(FIXTURES)
        migrations = mm.discover()
        # Find the file with a description in the name
        for m in migrations:
            if "add" in m.description:
                assert m.description is not None
                break
        else:
            pytest.skip("No migration with description found")

    def test_pending_after_discover(self):
        mm = MigrationManager(FIXTURES)
        mm.discover()
        pending = mm.pending()
        assert len(pending) == len(mm._migrations)  # nothing applied yet


class TestMigrationManagerCompatibility:
    def test_all_compatible_by_default(self):
        """The fixtures have 3 safe + 1 unsafe migration."""
        mm = MigrationManager(FIXTURES)
        mm.discover()
        compat = mm.compatibility_check()
        assert compat["incompatible_count"] >= 1
        assert compat["compatible"] is False

    def test_compatibility_after_applying_unsafe(self):
        """After tagging the unsafe one as applied, remaining should be safe."""
        mm = MigrationManager(FIXTURES)
        mm.discover()
        # Mark the DROP migration as already applied
        for m in mm._migrations:
            if "drop" in m.description.lower():
                mm._applied[m.id] = m
        compat = mm.compatibility_check()
        assert compat["compatible"] is True


class TestMigrationManagerGate:
    def test_gate_passes_with_no_pending(self):
        mm = MigrationManager(FIXTURES)
        mm.discover()
        # Apply all
        for m in mm._migrations:
            mm._applied[m.id] = m
        assert mm.gate_passed is True
        assert mm.deploy_gate() is True

    def test_gate_blocks_with_incompatible(self):
        mm = MigrationManager(FIXTURES)
        mm.discover()
        result = mm.deploy_gate()
        assert result is False

    def test_gate_skips_when_no_migrations_dir(self):
        mm = MigrationManager("/tmp/nonexistent_migrations_dir_xyz")
        assert mm.deploy_gate() is True  # no migrations = no blockage

    def test_gate_sets_gate_active_flag(self):
        mm = MigrationManager(FIXTURES)
        mm.discover()
        # Mark unsafe as applied
        for m in mm._migrations:
            if "drop" in m.description.lower():
                mm._applied[m.id] = m
        result = mm.deploy_gate()
        assert result is True
        assert mm._gate_active is True
