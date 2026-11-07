"""Mixture components (M2.3), offline."""
import pytest

from chemotion_api.elements.components import Component, load_components, save_components
from chemotion_api.elements.sample import Molecule

ETHANOL = {'id': 7, 'iupac_name': 'ethanol', 'cano_smiles': 'CCO'}
STORED = {'id': 3, 'name': 'ethanol', 'position': 0, 'sample_id': 9,
          'component_properties': {'amount_mol': 0.01, 'material_group': 'liquid', 'molecule_id': 7,
                                   'molecule': ETHANOL}}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)
        self.url, self.reason = 'http://eln.test', 'x'

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res):
        self.res, self.calls = res, []

    def get(self, url, **kw):
        self.calls.append(('get', url, None))
        return self.res

    def put(self, url, data=None, **kw):
        self.calls.append(('put', url, data))
        return self.res


def test_a_stored_component_splits_off_its_molecule():
    c = Component(STORED)
    assert (c.id, c.name, c.position, c.molecule_id) == (3, 'ethanol', 0, 7)
    assert 'molecule' not in c.properties and c.molecule['cano_smiles'] == 'CCO'


def test_saving_numbers_new_components_and_keeps_existing_ids():
    existing = Component(STORED)
    new = Component.new(Molecule(dict(ETHANOL, id=8, iupac_name='oxidane')), amount_mol=0.02)
    session = _Session(_Res(200, [STORED]))
    save_components(session, 9, [existing, new])
    (_, url, body), = session.calls
    assert url == '/api/v1/components' and body['sample_id'] == 9
    first, second = body['components']
    assert first['id'] == 3 and first['component_properties']['molecule_id'] == 7
    assert 'molecule' not in first['component_properties']
    assert second == {'id': 'new_2', 'name': 'oxidane', 'position': 2,
                      'component_properties': {'amount_mol': 0.02, 'molecule_id': 8}}


def test_unknown_properties_are_refused():
    with pytest.raises(ValueError, match='amount_kg'):
        Component.new(Molecule(ETHANOL), amount_kg=1)


def test_a_component_without_a_molecule_sends_nothing():
    session = _Session(_Res(200, []))
    with pytest.raises(ValueError, match='no molecule'):
        save_components(session, 9, [Component({'id': None, 'name': 'x', 'component_properties': {}})])
    assert session.calls == []


def test_components_come_back_by_position():
    rows = [dict(STORED, id=4, position=1), dict(STORED, id=3, position=0)]
    assert [c.id for c in load_components(_Session(_Res(200, rows)), 9)] == [3, 4]
