import difflib
import json
import os

from chemotion_api.utils import resource_path

_SOLVER_LIST = None


def get_solvent_list() -> dict[str, dict[str, str | float]]:
    global _SOLVER_LIST
    if _SOLVER_LIST is None:
        json_path = os.path.join(resource_path(__file__), '../elements/empty_elements/solvents.json')
        if os.path.exists(json_path):
            with open(json_path) as f:
                _SOLVER_LIST = json.loads(f.read())
        else:
            return {}
    return _SOLVER_LIST


def get_solvent_info(name: str) -> dict[str, str | float]:
    """
    :param name: Solvent name (see :func:`get_solvent_list`)
    :return: the entry of the solvent list (``smiles``, ``density``, ...)

    :raises KeyError: if the name is not in the solvent list. The message names similar solvents.
    """
    solvents = get_solvent_list()
    solvent_info = solvents.get(name)
    if solvent_info is not None:
        return solvent_info
    lower_name = name.lower()
    suggestions = [n for n in solvents if lower_name in n.lower()]
    suggestions += [n for n in difflib.get_close_matches(name, solvents.keys(), n=3, cutoff=0.6)
                    if n not in suggestions]
    message = f'Solvent "{name}" is not available. Run instance.get_solvent_list() to see all valid solvent names.'
    if suggestions:
        message += ' Did you mean: {}?'.format(', '.join(f'"{n}"' for n in suggestions[:5]))
    raise KeyError(message)
