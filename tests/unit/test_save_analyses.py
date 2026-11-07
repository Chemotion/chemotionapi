"""Saving and deleting analyses through the containers route (M3.5), offline."""
import json

import pytest

from chemotion_api.elements.abstract_element import AbstractElement, AnalysesList


def _analysis(aid, name):
    return {'id': aid, 'name': name, 'description': '', 'container_type': 'analysis',
            'extended_metadata': {'kind': '', 'status': ''}, 'children': []}


CONTAINER = {'id': 1, 'container_type': 'root', 'children': [
    {'id': 2, 'container_type': 'analyses', 'children': [_analysis(10, 'NMR'), _analysis(11, 'IR')]}]}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.puts = list(responses), []

    def put(self, url, data=None, **kw):
        self.puts.append((url, json.loads(data)))
        return self.responses.pop(0)


class _Element:
    save_analyses = AbstractElement.save_analyses
    delete_analysis = AbstractElement.delete_analysis
    _put_container = AbstractElement._put_container
    _parse_analyses = AbstractElement._parse_analyses
    _clean_analyses_data = AbstractElement._clean_analyses_data
    _saved_id_for = AbstractElement._saved_id_for

    def __init__(self, session):
        self._session, self.is_new, self.id, self.element_type = session, False, 5, 'sample'
        self.json_data = {'id': 5, 'container': json.loads(json.dumps(CONTAINER))}
        self._analyses = self._parse_analyses()

    analyses = property(lambda self: self._analyses)


def _answer(*analyses):
    return _Res(200, {'container': dict(CONTAINER, children=[dict(CONTAINER['children'][0], children=list(analyses))])})


def test_save_analyses_sends_the_whole_root_container_and_reparses():
    saved = _analysis(12, 'UV')
    session = _Session(_answer(_analysis(10, 'NMR*'), _analysis(11, 'IR'), saved))
    el = _Element(session)
    el.analyses.by_name('NMR')['name'] = 'NMR*'
    el.analyses.add_analyses('UV')
    el.save_analyses()
    (url, body), = session.puts
    assert url == '/api/v1/containers/container'
    sent = body['container']['children'][0]['children']
    assert body['container']['id'] == 1 and [a['name'] for a in sent] == ['NMR*', 'IR', 'UV']
    assert sent[2]['is_new'] is True
    assert [(a.id, a['name']) for a in el.analyses] == [(10, 'NMR*'), (11, 'IR'), (12, 'UV')]


def test_delete_analysis_marks_it_deleted():
    session = _Session(_answer(_analysis(11, 'IR')))
    el = _Element(session)
    el.delete_analysis(el.analyses.by_name('NMR'))
    sent = session.puts[0][1]['container']['children'][0]['children']
    assert [(a['id'], a.get('is_deleted')) for a in sent] == [(10, True), (11, None)]
    assert [a['name'] for a in el.analyses] == ['IR']


def test_delete_an_unsaved_analysis_sends_nothing_and_foreign_ones_are_refused():
    session = _Session()
    el = _Element(session)
    new = el.analyses.add_analyses('draft')
    el.delete_analysis(new)
    assert session.puts == [] and [a['name'] for a in el.analyses] == ['NMR', 'IR']
    with pytest.raises(ValueError, match='not one of'):
        el.delete_analysis(AnalysesList(session).add_analyses('NMR'))


def test_refusals():
    el = _Element(_Session(_Res(401, {})))
    with pytest.raises(PermissionError):
        el.save_analyses()
    el.is_new = True
    with pytest.raises(ValueError, match='Save the sample'):
        el.save_analyses()
