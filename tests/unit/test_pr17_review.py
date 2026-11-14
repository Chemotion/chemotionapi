"""Fixes from the review of PR #17 (2026-11-14). Each test reproduces the reported failure."""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_save_analyses import _answer, _analysis, _Element as _AnalysesElement, _Session as _PutSession  # noqa: E402
from test_split_samples import _collection, _Sample, _Session as _SplitSession, loaded  # noqa: E402,F401

from chemotion_api.collection import Collection  # noqa: E402
from chemotion_api.elements.attachments import Attachment  # noqa: E402
from chemotion_api.elements.reaction import _duration_text  # noqa: E402
from chemotion_api.search.structure import StructureSearcher  # noqa: E402


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError('no body')     # what requests does for a 204
        return self._payload


# --- 1. the scheme's duration is sent as text ---------------------------------------------------

@pytest.mark.parametrize('duration, text', [
    ({'unit': 'Hour(s)', 'value': 2.0}, '2 Hour(s)'),
    ({'unit': 'Minute(s)', 'value': 1.5}, '1.5 Minute(s)'),
    ({'unit': None, 'value': None}, ''),          # a new reaction's default: 400 before
    (SimpleNamespace(unit='Day(s)', value=3), '3 Day(s)'),
    ('2 h', '2 h'), (None, ''),
])
def test_the_duration_is_text(duration, text):
    assert _duration_text(duration) == text


# --- 2. new subsamples are found although an older sample was updated in between ---------------

def test_an_older_sample_updated_meanwhile_does_not_hide_the_new_subsamples(loaded):
    before = [{'id': 50, 'short_label': 'API-5'}]
    # Ordered by update time: sample 7 was edited after the split, so it comes first.
    after = [{'id': 7, 'short_label': 'API-7'}, {'id': 51, 'short_label': 'API-5-1'}]
    session = _SplitSession(before, after)
    assert _collection(session).split_samples(_Sample(5, 'API-5')) == [('loaded', 51)]


# --- 3. deleting one analysis keeps the others' unsaved edits -----------------------------------

def test_deleting_an_analysis_keeps_unsaved_edits_and_new_analyses():
    session = _PutSession(_answer(_analysis(11, 'IR')))
    element = _AnalysesElement(session)
    element.analyses.by_name('IR')['name'] = 'IR (edited)'
    element.analyses.add_analyses('draft')
    element.delete_analysis(element.analyses.by_name('NMR'))
    assert [a['name'] for a in element.analyses] == ['IR (edited)', 'draft']


# --- 6. a 204 to an unlink is a success ------------------------------------------------------

def test_an_unlink_answered_with_204_does_not_raise():
    calls = []
    session = SimpleNamespace(delete=lambda url, **kw: calls.append(url) or _Res(204))
    attachment = Attachment(session, {'id': 5, 'filename': 'a.txt', 'attachable_id': 9})
    attachment.unlink()
    assert calls == ['/api/v1/attachments/link/5']


# --- 7. a collection without an id refuses a split before any request -----------------------

def test_a_split_in_a_collection_without_an_id_is_a_value_error():
    session = _SplitSession([], [])
    collection = _collection(session, col_id=None)
    sbmm = SimpleNamespace(element_type='sequence_based_macromolecule_sample', id=3, is_new=False,
                           short_label='SBMM-3')
    with pytest.raises(ValueError, match='cannot hold'):
        Collection.split_sbmm_samples(collection, sbmm)
    assert session.calls == []


# --- 8. a type without matches is an empty set, not a KeyError ----------------------------------

def test_a_type_the_answer_has_no_block_for_is_empty():
    connection = SimpleNamespace(post=lambda url, data=None, **kw: _Res(200, {
        'samples': {'elements': [], 'totalElements': 0}}))
    manager = SimpleNamespace(all_classes={
        'sample': {'name': 'sample', 'is_generic': False, 'label': 'Sample'},
        'reaction': {'name': 'reaction', 'is_generic': False, 'label': 'Reaction'}})
    searcher = StructureSearcher(connection, manager, 1).substructure('C\nM  END')
    result = searcher.request()
    assert result.total('reaction') == 0
    assert list(result.reactions) == []
    assert json.dumps(result.types) == '[]'


# --- 5. importing a spreadsheet uploads the file without saving the wellplate --------------------

def test_import_spreadsheet_does_not_save_the_wellplate(tmp_path, monkeypatch):
    from chemotion_api.elements.attachments import Attachments
    from chemotion_api.elements.wellplate import Wellplate
    sheet = tmp_path / 'plate.xlsx'
    sheet.write_bytes(b'xlsx')
    uploads, puts = [], []
    monkeypatch.setattr(Attachments, 'save', lambda self, id, element_type: uploads.append((id, element_type)))
    session = SimpleNamespace(
        host_url='http://eln', put=lambda url, data=None, **kw: puts.append(url) or _Res(200, {'wellplate': {'id': 4}}))
    plate = Wellplate.__new__(Wellplate)
    plate._session, plate._attachments = session, Attachments(session, [{'id': 1, 'filename': 'old.txt'}])
    plate._saved_id_for = lambda what: 4
    plate._is_partial = False
    plate.save = plate.load = lambda *a, **k: pytest.fail('the wellplate itself must not be saved or reloaded')
    plate._load_data_from_server = lambda: ([{'id': 1}, {'id': 2, 'filename': 'plate.xlsx'}], {'id': 4})
    plate._set_json_data = lambda data: None
    assert plate.import_spreadsheet(str(sheet)) is plate
    assert uploads == [(4, 'Wellplate')]
    assert puts == ['/api/v1/wellplates/import_spreadsheet/4']
    assert [a['id'] for a in plate.attachments] == [1, 2]
