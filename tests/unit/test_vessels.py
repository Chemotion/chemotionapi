"""Vessels and vessel templates (M4.2), offline."""
import pytest

from chemotion_api.vessels import Vessel, VesselTemplate, bulk_create_vessels, create_vessel, list_vessels

TEMPLATE = {'id': 't-1', 'name': 'Flask', 'vessel_type': 'round bottom flask', 'material_type': 'glass',
            'material_details': None, 'volume_amount': 250.0, 'volume_unit': 'ml', 'details': None, 'container': None}
VESSEL = {'id': 'v-1', 'name': 'Flask instance', 'short_label': 'API-V1', 'description': None, 'bar_code': 'B1',
          'qr_code': None, 'weight_amount': 120.5, 'weight_unit': 'g', 'vessel_template': TEMPLATE, 'tag': {}}


class _Res:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._payload, self.text, self.headers = status, payload, str(payload), headers or {}

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

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def test_template_create_update_and_name_clash():
    session = _Session(_Res(201, TEMPLATE), _Res(200, dict(TEMPLATE, details='NS 29')), _Res(409, {}))
    t = VesselTemplate(name='Flask', volume_amount=250.0, volume_unit='ml', _session=session).save()
    assert t.id == 't-1' and session.calls[0] == ('post', '/api/v1/vessels/templates/create',
                                                  {'name': 'Flask', 'volume_amount': 250.0, 'volume_unit': 'ml'})
    t.details = 'NS 29'
    assert t.save().details == 'NS 29' and session.calls[1][:2] == ('put', '/api/v1/vessels/templates/t-1')
    with pytest.raises(ValueError, match='already exists'):
        VesselTemplate(name='Flask', _session=session).save()


def test_template_delete_refused_while_used():
    with pytest.raises(ValueError, match='still has vessels'):
        VesselTemplate(id='t-1', name='Flask', _session=_Session(_Res(400, {}))).delete()


def test_vessels():
    session = _Session(_Res(201, VESSEL), _Res(200, dict(VESSEL, description='dried')), _Res(200, {}),
                       _Res(201, [dict(VESSEL, id=f'v-{n}', name=f'rack {n}') for n in (2, 3)]))
    v = create_vessel(session, 5, VesselTemplate.from_json(TEMPLATE), weight_amount=120.5)
    assert (v.short_label, v.template.name, v.weight_amount) == ('API-V1', 'Flask', 120.5)
    v.description = 'dried'
    assert v.save().description == 'dried'
    v.delete()
    made = bulk_create_vessels(session, 5, 't-1', 2, base_name='rack')
    assert [m.name for m in made] == ['rack 2', 'rack 3']
    assert session.calls[0][2] == {'vessel_template_id': 't-1', 'collection_id': 5, 'weight_amount': 120.5}
    assert session.calls[1][2] == {'name': 'Flask instance', 'description': 'dried', 'bar_code': 'B1',
                                   'weight_amount': 120.5, 'weight_unit': 'g'}
    assert session.calls[3][2] == {'vessel_template_id': 't-1', 'collection_id': 5, 'count': 2, 'base_name': 'rack'}


def test_rejects_and_paging():
    with pytest.raises(ValueError, match='1 to 100'):
        bulk_create_vessels(_Session(), 5, 't-1', 0)
    with pytest.raises(ValueError, match='Unknown vessel fields'):
        create_vessel(_Session(), 5, 't-1', colour='red')
    with pytest.raises(ValueError, match='Save the vessel template'):
        create_vessel(_Session(), 5, VesselTemplate(name='x'))
    page = [VESSEL] * 2
    session = _Session(_Res(200, {'vessels': page}, {'X-Total-Pages': '2'}), _Res(200, {'vessels': [VESSEL]}))
    assert len(list_vessels(session, 5, per_page=2)) == 3
    assert isinstance(Vessel.from_json(VESSEL), Vessel)
