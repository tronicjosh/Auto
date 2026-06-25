"""The antenna tool's behaviour is defined **entirely by config**, in the `config/` folder.

There is no antenna-specific code here: vocab reading, row mapping, validation and the workbook
writer are all built by the loader from the config specs (vocab_spec / mapping_spec / rules_spec /
output_spec). Engineers tune the tool by editing the config files, not this code.
"""

from .loader import CONFIG_ROOT, load_workflow


def build():
    """(Re)build the antenna workflow from its config files."""
    return load_workflow(CONFIG_ROOT)


ANTENNA = build()
