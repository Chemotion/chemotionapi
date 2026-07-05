"""Templates and factory helpers for empty Chemotion element building blocks.

Holds the bundled ``*.json`` templates (e.g. ``container.json``) and the helpers that load
and instantiate them with fresh identifiers when new elements are created.
"""

import json
import os
import uuid

from chemotion_api.utils import resource_path


def init_container():
    """Build a fresh element container (root holding a single empty analyses child).

    Loads the bundled ``container.json`` template and assigns new UUIDs to the root and the
    analyses container.

    :return: A new container dict with ``container_type`` ``'root'`` and one analyses child
    """
    json_path = os.path.join(resource_path(__file__), 'container.json')
    with open(json_path) as f:
        data = json.loads(f.read())
    root = data.copy()
    root['container_type'] = 'root'
    root['id'] = uuid.uuid4().__str__()
    analyses = data.copy()
    analyses['id'] = uuid.uuid4().__str__()
    analyses['container_type'] = 'analyses'
    root['children'] = [analyses]
    return root


