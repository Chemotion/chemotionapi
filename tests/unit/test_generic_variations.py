"""Generic element variations (M6.4), offline."""
import pytest

from chemotion_api.elements.generic_element import GenericElement, variation_key


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append(('get', url, None))
        return self.responses.pop(0)

    def put(self, url, data=None, **kw):
        self.calls.append(('put', url, data))
        return self.responses.pop(0)

    def post(self, url, files=None, **kw):
        self.calls.append(('post', url, sorted(files)))
        return self.responses.pop(0)


def _element(session):
    el = GenericElement.__new__(GenericElement)
    el._session, el._id, el.is_new, el._element_type = session, 13, False, 'wrk'
    return el


RECORD = {'element_variation': {'id': 1, 'elementId': 13, 'variations': {'r1': {'metadata': {}}}, 'layout': {'x': 1}}}


def test_variations_round_trip(tmp_path):
    workbook = tmp_path / 'v.xlsx'
    workbook.write_bytes(b'PK')
    session = _Session(_Res(200, RECORD), _Res(200, RECORD), _Res(201, {'warnings': ['skipped B2']}), _Res(422, 'bad'))
    el = _element(session)
    assert el.variations() == {'variations': {'r1': {'metadata': {}}}, 'layout': {'x': 1}}
    el.save_variations({'r1': {'metadata': {}}})
    assert session.calls[1] == ('put', '/api/v1/element_variations/13', {'variations': {'r1': {'metadata': {}}}})
    assert el.import_variations(str(workbook)) == ['skipped B2']
    with pytest.raises(ValueError, match='Cannot import'):
        el.import_variations(str(workbook))


def test_property_keys_follow_the_server():
    assert variation_key('general', 'temp') == 'layergeneralfieldtemp'
