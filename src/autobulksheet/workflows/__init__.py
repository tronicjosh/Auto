"""Workflow registry. The antenna workflow is built from its `config/` files at import;
`reload_workflow` re-reads them so config edits take effect without a process restart.

(The registry indirection is kept deliberately small — it's where a second workflow would
slot in later — but for now there is exactly one: antenna.)
"""

from .antenna import build as _build_antenna
from .base import Workflow

# id -> builder (reads that workflow's config folder and returns a Workflow)
_BUILDERS = {"antenna": _build_antenna}
_REGISTRY = {wid: build() for wid, build in _BUILDERS.items()}


def list_workflows() -> list[Workflow]:
    """Enabled workflows (currently just antenna)."""
    return [w for w in _REGISTRY.values() if w.enabled]


def get_workflow(workflow_id: str) -> Workflow | None:
    return _REGISTRY.get(workflow_id)


def reload_workflow(workflow_id: str) -> Workflow | None:
    """Rebuild one workflow from its (just-edited) config files."""
    if workflow_id in _BUILDERS:
        _REGISTRY[workflow_id] = _BUILDERS[workflow_id]()
        return _REGISTRY[workflow_id]
    return None


__all__ = ["Workflow", "list_workflows", "get_workflow", "reload_workflow"]
