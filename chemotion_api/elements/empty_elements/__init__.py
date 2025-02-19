import json
import os
import uuid

from chemotion_api.utils import resource_path


def init_container():
    json_path = os.path.join(resource_path(__file__), 'container.json')
    f = open(json_path, 'r')
    data = json.loads(f.read())
    root = data.copy()
    root['container_type'] = 'root'
    root['id'] = uuid.uuid4().__str__()
    analyses = data.copy()
    analyses['id'] = uuid.uuid4().__str__()
    analyses['container_type'] = 'analyses'
    root['children'] = [analyses]
    f.close()
    return root


