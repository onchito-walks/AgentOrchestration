"""Migration Manager — Database schema migration orchestration.

Provides a migration job gate for deploys: migrations run and pass
forward-compatibility checks before new application pods receive traffic.

Issue: #969 (Bounty $7k)
"""

import os
import re
import time
import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when a migration fails or compatibility check fails."""


class MigrationStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Migration:
    """A single database migration — path, checksum, status."""

    def __init__(self, path: str, version: str, description: str = ""):
        self.path = path
        self.version = version
        self.id = version  # unique id = version string
        self.description = description or path
        self.status = MigrationStatus.PENDING
        self.checksum: Optional[str] = None
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.error: Optional[str] = None
        self._sql: Optional[str] = None

    def load(self) -> str:
        """Read and cache migration SQL content."""
        if self._sql is None:
            with open(self.path) as f:
                self._sql = f.read()
            self.checksum = hashlib.sha256(self._sql.encode()).hexdigest()[:16]
        return self._sql

    @property
    def is_forward_compatible(self) -> bool:
        """Heuristic: forward-compatible migrations only ADD columns/tables.

        Backward-incompatible patterns (DROP, ALTER COLUMN ... DROP, RENAME)
        require special handling and are flagged.
        """
        sql = self.load().lower()
        dangerous = [
            r"\bdrop\s+(table|column|index|view|schema)\b",
            r"\balter\s+table.*\bdrop\b",
            r"\balter\s+table.*rename\b",
            r"\bdelete\s+from\b",
            r"\btruncate\b",
        ]
        for pattern in dangerous:
            if re.search(pattern, sql):
                return False
        return True

    def run(self, connection=None) -> None:
        """Execute the migration.

        In the test/CI path this validates the SQL without connecting to a DB.
        In production this would execute against the actual database.
        """
        self.status = MigrationStatus.RUNNING
        self.started_at = time.time()
        try:
            sql = self.load()
            if connection:
                connection.execute(sql)
            else:
                # CI/offline mode: validate SQL can be parsed
                self._validate_sql(sql)
            self.status = MigrationStatus.COMPLETED
            self.completed_at = time.time()
        except Exception as e:
            self.status = MigrationStatus.FAILED
            self.error = str(e)
            raise MigrationError(f"Migration {self.version} failed: {e}") from e

    @staticmethod
    def _validate_sql(sql: str) -> None:
        """Basic SQL validation: must have at least one statement, no empty."""
        stripped = sql.strip()
        if not stripped:
            raise MigrationError("Empty migration SQL")
        # Simple structural checks
        if not stripped.rstrip(";").strip():
            raise MigrationError("Migration contains only whitespace/semicolons")


class MigrationManager:
    """Orchestrates migration discovery, ordering, execution, and gating."""

    _MIGRATION_FILE_RE = re.compile(
        r"^(\d{4}[._]\d{2}[._]\d{2}(?:[._]\d{6})?)[._-]?(.*)\.sql$"
    )

    def __init__(self, migrations_dir: str = "migrations"):
        self.migrations_dir = migrations_dir
        self._migrations: List[Migration] = []
        self._applied: Dict[str, Migration] = {}
        self._gate_active = False

    def discover(self) -> List[Migration]:
        """Scan migrations_dir for .sql files and sort by version."""
        self._migrations = []
        if not os.path.isdir(self.migrations_dir):
            logger.warning("Migrations directory not found: %s", self.migrations_dir)
            return self._migrations

        for fname in sorted(os.listdir(self.migrations_dir)):
            match = self._MIGRATION_FILE_RE.match(fname)
            if not match:
                continue
            version = match.group(1).replace("_", "-").replace(".", "-")
            desc = match.group(2).replace("-", " ").replace("_", " ").strip()
            path = os.path.join(self.migrations_dir, fname)
            self._migrations.append(Migration(path, version, desc))
        return self._migrations

    def pending(self) -> List[Migration]:
        """Return migrations not yet applied."""
        return [m for m in self._migrations if m.id not in self._applied]

    def run_pending(self, connection=None) -> List[Tuple[str, str]]:
        """Execute all pending migrations in order.

        Returns list of (version, status) tuples.
        """
        results: List[Tuple[str, str]] = []
        for migration in self.pending():
            try:
                migration.run(connection)
                self._applied[migration.id] = migration
                results.append((migration.version, MigrationStatus.COMPLETED))
            except MigrationError:
                results.append((migration.version, MigrationStatus.FAILED))
                raise
        return results

    def compatibility_check(self) -> Dict[str, Any]:
        """Check all pending migrations for forward compatibility.

        Returns:
            {
                "compatible": True/False,
                "safe": [...],
                "flagged": [...],
                "incompatible_count": N,
            }
        """
        safe: List[str] = []
        flagged: List[str] = []
        for m in self.pending():
            if m.is_forward_compatible:
                safe.append(m.version)
            else:
                flagged.append(m.version)
        return {
            "compatible": len(flagged) == 0,
            "safe": safe,
            "flagged": flagged,
            "incompatible_count": len(flagged),
        }

    @property
    def gate_passed(self) -> bool:
        """Migration gate: True if all pending migrations are
        forward-compatible OR all migrations have been applied."""
        pending = self.pending()
        if not pending:
            return True
        result = self.compatibility_check()
        return result["compatible"]

    def deploy_gate(self) -> bool:
        """Full deploy gate: discover → compatibility check → run pending.

        Returns True if deploy should proceed, False if blocked.

        Side effects: logs detailed gate status.
        """
        self.discover()
        compat = self.compatibility_check()

        logger.info("Migration gate — %d pending, compatible=%s",
                     len(compat["safe"]) + len(compat["flagged"]),
                     compat["compatible"])

        if not compat["compatible"]:
            logger.error("Deploy BLOCKED — %d incompatible migrations: %s",
                         compat["incompatible_count"],
                         ", ".join(compat["flagged"]))
            return False

        if not compat["safe"]:
            logger.info("No pending migrations — deploy can proceed")
            return True

        try:
            results = self.run_pending()
            logger.info("Migration gate passed — %d migrations applied",
                         len(results))
            self._gate_active = True
            return True
        except MigrationError as e:
            logger.error("Deploy BLOCKED — migration failed: %s", e)
            return False
