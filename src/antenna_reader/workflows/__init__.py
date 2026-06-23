"""Workflow registry. Adding a workflow = a config folder + a builder line here.

Workflows are built from their config files; `reload_workflow` re-reads the files so
edits saved from the UI take effect immediately, without a restart.
"""

from .antenna import build as _build_antenna
from .base import Workflow
from .diff import diff_versions

# id -> builder (reads that workflow's config folder and returns a Workflow)
_BUILDERS = {"antenna": _build_antenna}
_REGISTRY = {wid: build() for wid, build in _BUILDERS.items()}


def list_workflows() -> list[Workflow]:
    """Enabled workflows, for the landing page."""
    return [w for w in _REGISTRY.values() if w.enabled]


def get_workflow(workflow_id: str) -> Workflow | None:
    return _REGISTRY.get(workflow_id)


def reload_workflow(workflow_id: str) -> Workflow | None:
    """Rebuild one workflow from its (just-edited) config files."""
    if workflow_id in _BUILDERS:
        _REGISTRY[workflow_id] = _BUILDERS[workflow_id]()
        return _REGISTRY[workflow_id]
    return None


__all__ = ["Workflow", "diff_versions", "list_workflows", "get_workflow", "reload_workflow"]
