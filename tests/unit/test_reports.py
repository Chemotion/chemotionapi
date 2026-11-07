"""Reports, archives and table exports (M3.2), offline."""
import pytest

import chemotion_api.reports as reports
from chemotion_api.reports import Archive, ReportTemplate, create_report, export_elements, \
    export_reaction_smiles, report_payload


class _El:
    def __init__(self, element_type, eid):
        self.element_type, self.id, self.is_new = element_type, eid, eid is None


class _Res:
    def __init__(self, status, payload=None, content=b''):
        self.status_code, self._payload, self.content, self.text = status, payload, content, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def _next(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params'))))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._next('get', url, kw)

    def post(self, url, **kw):
        return self._next('post', url, kw)

    def delete(self, url, **kw):
        return self._next('delete', url, kw)


REPORT = {'id': 4, 'file_name': 'weekly', 'template': 'standard', 'downloadable': False,
          'objects': [{'id': 1, 'type': 'sample'}]}


def test_payload_defaults_match_the_ui():
    body = report_payload([_El('sample', 1), _El('reaction', 2)], file_name='weekly')
    assert body['objTags'] == [{'id': 1, 'type': 'sample'}, {'id': 2, 'type': 'reaction'}]
    assert all(s['checked'] for key in ('splSettings', 'rxnSettings', 'siRxnSettings') for s in body[key])
    assert {s['text'] for s in body['rxnSettings']} >= {'dangerous_products', 'variations'}
    assert body['configs'] == [{'text': 'page_break', 'checked': True}, {'text': 'whole_diagram', 'checked': True}]
    assert (body['templateId'], body['templateType'], body['imgFormat']) == ('standard', 'standard', 'png')
    assert body['molSerials'] == [] and body['prdAtts'] == [] and 'fileDescription' not in body


def test_payload_options():
    body = report_payload([_El('reaction', 2)], ReportTemplate(3, 'SI', 'supporting_information_std_rxn'),
                          reaction_settings={'variations': False}, all_chemicals_in_schemes=False,
                          page_break=False, molecule_serials={7: '1a'}, description='d', image_format='emf')
    assert {s['text']: s['checked'] for s in body['rxnSettings']}['variations'] is False
    assert body['configs'] == [{'text': 'page_break', 'checked': False}, {'text': 'product_diagram', 'checked': True}]
    assert (body['templateId'], body['templateType']) == ('3', 'supporting_information_std_rxn')
    assert body['molSerials'] == [{'mol': {'id': 7}, 'value': '1a'}]
    assert (body['fileDescription'], body['imgFormat']) == ('d', 'emf')
    assert report_payload([_El('sample', 1)], 5)['templateId'] == '5'


@pytest.mark.parametrize('elements, kwargs, match', [
    ([], {}, 'at least one'),
    ([_El('wellplate', 1)], {}, 'samples and reactions only'),
    ([_El('sample', None)], {}, 'Save'),
    ([_El('sample', 1)], {'template': 'nope'}, 'Unknown report type'),
    ([_El('sample', 1)], {'sample_settings': {'colour': True}}, 'Unknown report settings'),
    ([_El('sample', 1)], {'image_format': 'jpg'}, 'png, eps or emf'),
])
def test_payload_rejects(elements, kwargs, match):
    with pytest.raises(ValueError, match=match):
        report_payload(elements, **kwargs)


def test_create_report_polls_until_downloadable(monkeypatch):
    monkeypatch.setattr(reports.time, 'sleep', lambda s: None)
    session = _Session([_Res(201, {'report': REPORT}), _Res(201, {'archives': []}),
                        _Res(201, {'archives': [dict(REPORT, downloadable=True)]})])
    archive = create_report(session, [_El('sample', 1)], file_name='weekly')
    assert archive.downloadable and archive.id == 4
    assert [c[1] for c in session.calls] == ['/api/v1/reports'] + ['/api/v1/archives/downloadable'] * 2
    assert session.calls[1][2] == {'ids': [4]}


def test_create_report_refused_and_timeout(monkeypatch):
    with pytest.raises(PermissionError):
        create_report(_Session([_Res(401, {})]), [_El('sample', 1)])
    clock = iter(range(0, 1000, 100))
    monkeypatch.setattr(reports.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(reports.time, 'sleep', lambda s: None)
    session = _Session([_Res(201, {'report': REPORT})] + [_Res(201, {'archives': []})] * 5)
    with pytest.raises(TimeoutError, match='still be queued'):
        create_report(session, [_El('sample', 1)], timeout=250)


def test_archive_download_uses_the_templates_extension(tmp_path):
    session = _Session([_Res(200, content=b'csv'), _Res(200, {})])
    archive = Archive.from_json(dict(REPORT, template='rxn_list_csv', downloadable=True), session)
    path = archive.download(str(tmp_path / 'r.csv'))
    assert open(path, 'rb').read() == b'csv'
    archive.delete()
    assert session.calls == [('get', '/api/v1/download_report/file', {'id': 4, 'ext': 'csv'}),
                             ('delete', '/api/v1/archives/4', None)]
    with pytest.raises(ValueError, match='not generated yet'):
        Archive.from_json(REPORT, session).download(str(tmp_path / 'x'))


def test_export_elements_selects_exactly_the_given_elements(tmp_path):
    session = _Session([_Res(200, content=b'xlsx')])
    path = export_elements(session, 9, [_El('sample', 1), _El('reaction', 2), _El('sample', 3)],
                           str(tmp_path / 'e.xlsx'))
    assert open(path, 'rb').read() == b'xlsx'
    (_, url, body), = session.calls
    assert url == '/api/v1/reports/export_samples_from_selections' and body['exportType'] == 1
    assert body['uiState'] == {
        'sample': {'checkedIds': [1, 3], 'uncheckedIds': [], 'checkedAll': False},
        'reaction': {'checkedIds': [2], 'uncheckedIds': [], 'checkedAll': False},
        'wellplate': {'checkedIds': [], 'uncheckedIds': [], 'checkedAll': False},
        'currentCollection': 9}
    assert body['columns'] == reports.DEFAULT_EXPORT_COLUMNS


def test_export_elements_nothing_found_and_rejects(tmp_path):
    assert export_elements(_Session([_Res(204)]), 9, [_El('sample', 1)], str(tmp_path / 'e'), 'sdf') is None
    with pytest.raises(ValueError, match='xlsx, sdf'):
        export_elements(_Session([]), 9, [_El('sample', 1)], str(tmp_path / 'e'), 'csv')
    with pytest.raises(ValueError, match='Unknown export tables'):
        export_elements(_Session([]), 9, [_El('sample', 1)], str(tmp_path / 'e'), columns={'samples': []})
    with pytest.raises(ValueError, match='not screen'):
        export_elements(_Session([]), 9, [_El('screen', 1)], str(tmp_path / 'e'))


def test_reaction_smiles_notation(tmp_path):
    session = _Session([_Res(200, content=b'CCO>>CC=O')])
    export_reaction_smiles(session, 9, [_El('reaction', 2)], str(tmp_path / 'r.csv'), 'SM.R.S>>P')
    assert session.calls[0][2]['exportType'] == 2 and session.calls[0][2]['columns'] == {}
    with pytest.raises(ValueError, match='Only reactions'):
        export_reaction_smiles(session, 9, [_El('sample', 1)], str(tmp_path / 'r.csv'))
    with pytest.raises(ValueError, match='notation'):
        export_reaction_smiles(session, 9, [_El('reaction', 2)], str(tmp_path / 'r.csv'), 'A>B')
