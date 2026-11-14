"""Safety data sheets and inventory labels (M4.5), offline. The record itself: test_sample_inventory."""
import json

import pytest

from chemotion_api.chemicals import attach_safety_sheet, find_safety_sheets, inventory_label
from chemotion_api.elements.sample import Chemical

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


class _Sample:
    element_type, id, is_new = 'sample', 3, False

    def __init__(self, session):
        self._session = session

    def get_chemical(self):
        return Chemical(self._session, 3, RECORD)


def test_safety_sheets_lists_the_stored_paths():
    assert Chemical(None, 3, RECORD).safety_sheets == ['/safety_sheets/Merck/E7023.pdf']
    assert Chemical(None, 3, {}).safety_sheets == []


def test_manual_upload_sends_the_form_and_rereads_the_record(tmp_path):
    pdf = tmp_path / 'sds.pdf'
    pdf.write_bytes(b'%PDF-1.4')
    session = _Session(_Res(201, RECORD))
    chem = attach_safety_sheet(session, _Sample(session), str(pdf), 'Merck', 'merckProductInfo',
                               {'productNumber': 'E7023'}, cas='64-17-5')
    assert chem.safety_sheets == ['/safety_sheets/Merck/E7023.pdf']
    assert session.calls[0][:2] == ('post', '/api/v1/chemicals/save_manual_sds')
    assert session.calls[0][2]['sample_id'] == 3 and session.calls[0][2]['cas'] == '64-17-5'


def test_rejects():
    with pytest.raises(ValueError, match='vendor'):
        find_safety_sheets(_Session(), 'x', vendor='Acme')
    reaction = type('_R', (), {'element_type': 'reaction', 'id': 1})()
    with pytest.raises(ValueError, match='samples only'):
        attach_safety_sheet(_Session(), reaction, 'x.pdf', 'Merck', 'merckProductInfo')


def test_vendor_search_params_and_inventory_label():
    session = _Session(_Res(200, {'merck_link': {}}), _Res(200, None), _Res(200, {'id': 1, 'prefix': 'CHI',
                                                                                  'name': 'n', 'counter': 4}))
    find_safety_sheets(session, '64-17-5', vendor='Merck')
    assert session.calls[0] == ('get', '/api/v1/chemicals/fetch_safetysheet/null', {
        'data[vendor]': 'Merck', 'data[language]': 'en', 'data[option]': 'CAS', 'data[searchStr]': '64-17-5'})
    assert inventory_label(session, 5) is None
    assert inventory_label(session, 5).counter == 4
