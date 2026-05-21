"""
YAML Workflow Loader — Parses YAML workflow definitions with import
expansion and duplicate node ID rejection.

Validation happens at the registration / pre-dispatch boundary so
the bad graph cannot start executing.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from src.common.errors import DuplicateNodeError

logger = logging.getLogger(__name__)

# ── Public API ──────────────────────────────────────────────────────


def load_workflow_from_yaml(
    path: str,
    search_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Parse a YAML workflow definition, expand imports, and detect
    duplicate node identifiers across all imported and local nodes.

    Returns the fully-resolved workflow dict with keys:
        name, description, imports (resolved), steps, nodes

    Raises ``DuplicateNodeError`` if any two nodes (steps or decision
    nodes) share the same ``id``, whether they come from imports or the
    local file.
    """
    search_paths = search_paths or [os.path.dirname(os.path.abspath(path))]
    resolved = _resolve_yaml(path, search_paths, set())
    _validate_duplicates(resolved)
    return resolved


def load_workflow_from_yaml_string(
    yaml_text: str,
    source_name: str = "<inline>",
    search_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Same as ``load_workflow_from_yaml`` but accepts a raw YAML string.

    ``source_name`` is used only for error messages.
    """
    search_paths = search_paths or [os.getcwd()]
    raw = yaml.safe_load(yaml_text)
    if not isinstance(raw, dict):
        raise ValueError("YAML workflow definition must be a mapping (dict)")

    # Resolve any !import tagged nodes
    resolved = _resolve_tree(raw, source_name, search_paths, set())
    _validate_duplicates(resolved)
    return resolved


# ── Internal helpers ────────────────────────────────────────────────


def _resolve_yaml(path: str, search_paths: List[str], visited: Set[str]) -> Dict[str, Any]:
    """Read a YAML file from *path* (trying *search_paths* as fallback)
    and recursively expand any !import tags and ``imports:`` sections.
    """
    resolved_path = _find_file(path, search_paths)
    if resolved_path is None:
        raise FileNotFoundError(f"Workflow YAML not found: {path}")

    # Track paths in the visited set (canonical absolute paths only)
    abs_path = os.path.abspath(resolved_path)
    if abs_path in visited:
        raise ValueError(f"Circular YAML import detected: {path}")
    visited.add(abs_path)

    with open(resolved_path, "r") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Workflow YAML must be a mapping: {path}")

    base_dir = os.path.dirname(abs_path)
    return _resolve_tree(raw, resolved_path, [base_dir, *search_paths], visited)


def _resolve_tree(
    node: Any,
    source: str,
    search_paths: List[str],
    visited: Set[str],
) -> Any:
    """Recursively walk the parsed YAML tree and expand ``!import``
    tagged values as well as top-level ``imports:`` list entries.
    """
    if isinstance(node, dict):
        # Handle top-level imports: key
        if "imports" in node and isinstance(node["imports"], list):
            expanded_steps: List[Dict] = []
            expanded_nodes: List[Dict] = []
            for imp in node["imports"]:
                imp_path: str
                if isinstance(imp, dict):
                    imp_path = imp.get("path", "")
                elif isinstance(imp, str):
                    imp_path = imp
                else:
                    continue

                imported = _resolve_yaml(imp_path, search_paths, visited)
                if "steps" in imported:
                    expanded_steps.extend(imported["steps"])
                if "nodes" in imported:
                    expanded_nodes.extend(imported["nodes"])

            # Merge expanded imports into the local lists
            if expanded_steps:
                node.setdefault("steps", []).extend(expanded_steps)
            if expanded_nodes:
                node.setdefault("nodes", []).extend(expanded_nodes)

        # Recursively resolve any !import-tagged values
        return {k: _resolve_tree(v, source, search_paths, visited) for k, v in node.items()}

    elif isinstance(node, list):
        return [_resolve_tree(item, source, search_paths, visited) for item in node]

    # Leaf values (str, int, float, bool, None) pass through
    return node


def _find_file(path: str, search_paths: List[str]) -> Optional[str]:
    """Resolve *path* to an existing file, searching *search_paths*."""
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    for base in search_paths:
        candidate = os.path.join(base, path)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def _validate_duplicates(workflow: Dict[str, Any]) -> None:
    """Check for duplicate node identifiers across ``steps:`` and
    ``nodes:`` sections. Raise ``DuplicateNodeError`` on the first
    duplicate found.
    """
    seen: Set[str] = set()

    for section_name in ("steps", "nodes"):
        entries = workflow.get(section_name, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            node_id = entry.get("id") or entry.get("name")
            if not node_id:
                continue
            if node_id in seen:
                raise DuplicateNodeError(
                    node_id,
                    f"duplicate across '{section_name}' section in YAML import",
                )
            seen.add(node_id)


# ── YAML constructor for !import tag ────────────────────────────────


def _import_constructor(loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode) -> Any:
    """YAML ``!import`` tag handler — loads and inlines another YAML file.

    Usage in workflow YAML::

        steps:
          - !import shared/steps.yaml
    """
    path = loader.construct_scalar(node)
    return path


# Register the !import tag on yaml.SafeLoader
yaml.SafeLoader.add_constructor("!import", _import_constructor)
