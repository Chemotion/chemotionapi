import json
import os

_SOLVER_LIST = None


def get_solvent_list() -> dict[str, dict[str, str | float]]:
    global _SOLVER_LIST
    if _SOLVER_LIST is None:
        json_path = os.path.join(os.path.dirname(__file__), '../elements/empty_elements/solvents.json')
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                _SOLVER_LIST = json.loads(f.read())
        else:
            return {}
    return _SOLVER_LIST
