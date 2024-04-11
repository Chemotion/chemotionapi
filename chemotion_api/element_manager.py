import copy
import json
import uuid

from chemotion_api.connection import Connection
from chemotion_api.elements.sample import MoleculeManager
import os.path
from chemotion_api.user import User

from chemotion_api.elements.empty_elements import init_container

from requests.exceptions import RequestException

from chemotion_api.utils.solvent_manager import get_solvent_list


class ElementManager:

    def __init__(self, session: Connection):
        self._session = session
        self._all_classes = None
        self.is_loaded = False

    @property
    def all_classes(self) -> dict[str: dict]:
        if self._all_classes is None:
            self._all_classes = self.get_all_classes()
            self.is_loaded = True
        return self._all_classes

    def get_all_classes(self):
        get_url = "/api/v1/generic_elements/klasses.json"
        res = self._session.get(get_url)
        if res.status_code != 200:
            raise RequestException('Counld not get the genetic elements')
        all_classes = {}
        for x in res.json()['klass']:
            all_classes[x['name']] = x
        return all_classes

    def _init_container(self):
        return init_container()


    def _get_user(self):
        u = User.load_me(self._session)
        return u


    def _get_short_label(self, type_name):
        u = self._get_user()
        if type_name == 'sample':
            return '{}-{}'.format(u.initials, u.counters[type_name + 's'])
        if type_name == 'reaction':
            return '{}-R{}'.format(u.initials, u.counters[type_name + 's'])
        return f"{u.initials}-{type_name}{u.counters.get(type_name + 's', u.counters.get(type_name, 0))}"

    def build_new(self, type_name, collection_id):
        class_obj = self.all_classes[type_name]
        data = {}
        if not class_obj['is_generic']:
            json_path = os.path.join(os.path.dirname(__file__), 'elements/empty_elements', type_name + '.json')
            if os.path.exists(json_path):
                with open(json_path, 'r') as f:
                    data = json.loads(f.read())
            if type_name == 'wellplate':
                data['wells'] = []
                for y in range(1, 9):
                    for x in range(1, 13):
                        data['wells'].append({
                            "id": uuid.uuid4().__str__(),
                            "is_new": True,
                            "position": {
                                "x": x,
                                "y": y
                            }

                        })
        else:
            res = self._session.get('api/v1/generic_elements/klass.json', params={'name': type_name})
            klass_obj = res.json().get('klass')
            properties_release = copy.deepcopy(klass_obj['properties_release'])
            for key, layer in klass_obj['properties_release']['layers'].items():
                if not layer['wf']:
                    properties_release['layers'][key]['ai'] = []
                else:
                    del properties_release['layers'][key]
            data = {
                    "type": type_name,
                    "is_new": True,
                    "name": f"New {klass_obj['label']}",
                    "can_copy": True,
                    "klassType": "GenericEl",
                    "element_klass": klass_obj,
                    "element_klass_id": klass_obj['id'],
                    "properties": properties_release,
                    "properties_release": klass_obj['properties_release'],
                    "attachments": [],
                    "files": [],
            }





        data['container'] = self._init_container()
        data['collection_id'] = collection_id
        data['short_label'] = self._get_short_label(type_name)
        data['segments'] = []
        return data

    def build_solvent_sample(self, name, collection_id):
        solvent_info = self.get_solvent_list().get(name)
        if solvent_info is None:
            raise KeyError('Solver: "{}" is not available. Run instance.get_solvent_list() to see all valid solver names'.format(name))
        sample_data = self.build_new('sample', collection_id)

        mol = MoleculeManager(self._session).create_molecule_by_smiles(solvent_info['smiles'])

        sample_data['molecule'] = mol
        sample_data['density'] = solvent_info['density']
        sample_data['external_label'] = '{}'.format(name)
        sample_data['short_label'] = 'solvent'
        sample_data['is_split'] = True
        return sample_data

    @classmethod
    def get_solvent_list(cls):
        return get_solvent_list()
