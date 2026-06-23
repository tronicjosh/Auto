"""The antenna workflow is now defined **entirely by config** in `workflow_configs/antenna/`.

There is no antenna-specific code here: vocab reading, row mapping, validation and the
workbook writer are all built by the loader from config specs (vocab_spec / mapping_spec /
rules_spec / output_spec), composed from the shared engine's named building blocks. Adding a
new workflow is a config folder + one registry line — no code.
"""

from .loader import CONFIG_ROOT, load_workflow


def build():
    """(Re)build the antenna workflow purely from its config files."""
    return load_workflow(CONFIG_ROOT / "antenna")


ANTENNA = build()
