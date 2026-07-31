"""Lookup of the built-in Chemotion solvent list (name → SMILES and related properties)."""
import json
import os

from chemotion_api.utils import resource_path

_SOLVER_LIST = None


def get_solvent_list() -> dict[str, dict[str, str | float]]:
    """Load and cache the built-in Chemotion solvent list.

    The list is read once from the bundled ``solvents.json`` file and cached for subsequent calls.

    :return: A mapping of solvent name to its properties (e.g. SMILES and numeric values), or an
        empty dict if the bundled solvent file cannot be found
    """
    global _SOLVER_LIST
    if _SOLVER_LIST is None:
        json_path = os.path.join(resource_path(__file__), '../elements/empty_elements/solvents.json')
        if os.path.exists(json_path):
            with open(json_path) as f:
                _SOLVER_LIST = json.loads(f.read())
        else:
            return {}
    return _SOLVER_LIST
