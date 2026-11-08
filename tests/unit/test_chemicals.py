"""Chemical records and inventory labels (M4.5), offline."""
import json

import pytest

from chemotion_api.chemicals import Chemical, find_safety_sheets, inventory_label, load_chemical, save_chemical

RECORD = {'id': 7, 'sample_id': 3, 'cas': '64-17-5', 'chemical_data': [
    {'status': 'Available', 'safetySheetPath': [{'E7023_link': '/safety_sheets/Merck/E7023.pdf'}]}],
    'sequence_based_macromolecule_sample_id': None}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params'))))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def put(self, url, **kw):
        return self._call('put', url, kw)


class _El:
    def __init__(self, kind, eid):
        self.element_type, self.id = kind, eid


def test_load_maps_the_empty_record_to_none():
    empty = dict.fromkeys(RECORD)
    session = _Session(_Res(200, empty), _Res(200, RECORD))
    assert load_chemical(session, _El('sample', 3)) is None
    chem = load_chemical(session, _El('sample', 3))
    assert (chem.id, chem.cas, chem.safety_sheets) == (7, '64-17-5', ['/safety_sheets/Merck/E7023.pdf'])
    assert session.calls[0][2] == {'sample_id': 3}


def test_create_then_update_and_sbmm_owner():
    session = _Session(_Res(201, RECORD), _Res(200, RECORD), _Res(200, True), _Res(200, RECORD))
    save_chemical(session, _El('sample', 3), Chemical(cas='64-17-5', data={'status': 'Available'}))
    save_chemical(session, _El('sequence_based_macromolecule_sample', 4), Chemical(id=7, data={'status': 'x'}))
    assert session.calls[0] == ('post', '/api/v1/chemicals/create',
                                {'sample_id': 3, 'chemical_data': [{'status': 'Available'}], 'cas': '64-17-5'})
    assert session.calls[2] == ('put', '/api/v1/chemicals',
                                {'sequence_based_macromolecule_sample_id': 4, 'chemical_data': [{'status': 'x'}]})


def test_rejects():
    with pytest.raises(ValueError, match='Only samples'):
        load_chemical(_Session(), _El('reaction', 1))
    with pytest.raises(ValueError, match='CAS'):
        save_chemical(_Session(), _El('sample', 1), Chemical())
    with pytest.raises(ValueError, match='vendor'):
        find_safety_sheets(_Session(), 'x', vendor='Acme')


def test_vendor_search_params_and_inventory_label():
    session = _Session(_Res(200, {'merck_link': {}}), _Res(200, None), _Res(200, {'id': 1, 'prefix': 'CHI',
                                                                                  'name': 'n', 'counter': 4}))
    find_safety_sheets(session, '64-17-5', vendor='Merck')
    assert session.calls[0] == ('get', '/api/v1/chemicals/fetch_safetysheet/null', {
        'data[vendor]': 'Merck', 'data[language]': 'en', 'data[option]': 'CAS', 'data[searchStr]': '64-17-5'})
    assert inventory_label(session, 5) is None
    assert inventory_label(session, 5).counter == 4
