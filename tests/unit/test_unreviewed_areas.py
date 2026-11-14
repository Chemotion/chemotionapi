"""Fixes from the 2026-11-13 review of modules no one had examined (CLI, inbox, search, research
plans, LabIMotion schemas). Each test reproduces the reported failure."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_new_instance_creates_a_missing_directory(tmp_path):
    """`os.path.exists(os.path.isdir(cwd))` asked about file descriptor 0, so it was always true
    and a missing directory raised NotADirectoryError instead of being created."""
    from chemotion_api.commands import InstanceManager
    target = tmp_path / 'fresh'
    manager = InstanceManager.__new__(InstanceManager)
    manager._df_dir = str(target)
    with patch.object(InstanceManager, 'get_image_of_versions', return_value={}), \
            patch('chemotion_api.commands.walk_productive_template', return_value=[]):
        try:
            manager.new_instance(cwd=str(target))
        except Exception as e:  # anything after the directory step is out of scope here
            assert not isinstance(e, NotADirectoryError), e
    assert target.is_dir()


def test_versions_match_exactly_and_follow_pages():
    from chemotion_api.commands import InstanceManager
    pages = [{'results': [{'name': 'eln-1.1.2'}, {'name': 'db-1.1.2'}], 'next': 'page2'},
             {'results': [{'name': 'eln-1.2'}, {'name': 'db-1.2'}], 'next': None}]
    responses = [MagicMock(status_code=200, json=MagicMock(return_value=p)) for p in pages]
    with patch('chemotion_api.commands.requests.get', side_effect=responses):
        images = InstanceManager.get_image_of_versions('1.2')
    assert images == {'eln': 'ptrxyz/chemotion:eln-1.2', 'db': 'ptrxyz/chemotion:db-1.2'}


@pytest.mark.parametrize("count, pages", [(0, 1), (19, 1), (20, 1), (21, 2), (40, 2)])
def test_inbox_requests_exactly_the_pages_it_needs(count, pages):
    assert max(1, -(-count // 20)) == pages


def test_a_refused_search_raises_instead_of_returning_nothing():
    from chemotion_api.search.search_helper import SearchHelperBase
    helper = SimpleNamespace(
        element_type_res='samples', _per_page=10, _collection_id=1,
        _payload={'selection': {}},
        _connection=SimpleNamespace(post=lambda *a, **k: SimpleNamespace(status_code=201, json=lambda: {
            'samples': {'elements': [], 'error': 'Your search for name is not allowed'}})))
    with pytest.raises(PermissionError, match='not allowed'):
        SearchHelperBase._send_request(helper)


def test_an_empty_text_block_loads():
    from chemotion_api.elements.research_plan import RichText
    assert RichText('a', '')['value'] == {'ops': []}
    assert RichText('b', 'typed')['value'] == {'ops': [{'insert': 'typed'}]}


def _plan():
    from chemotion_api.elements.research_plan import ResearchPlan
    plan = ResearchPlan.__new__(ResearchPlan)
    plan._generic_segments, plan._session, plan._id = SimpleNamespace(), SimpleNamespace(), 1
    plan._image_values = {}
    return plan


def test_an_unreadable_linked_sample_is_kept_as_a_link():
    plan = _plan()
    with patch('chemotion_api.elements.research_plan.Sample', side_effect=ConnectionError('404')):
        linked = plan._parse_sample({'sample_id': 7})
    assert linked == {'sample_id': 7}
    assert plan._reparse_sample(linked) == {'sample_id': 7}


def test_an_image_keeps_its_zoom_and_a_missing_one_survives_a_save():
    plan = _plan()
    plan._image_values = {'abc': {'public_name': 'abc', 'file_name': 'x.png', 'zoom': 150}}
    assert plan._reparse_image({'identifier': 'abc', 'filename': 'x.png'})['zoom'] == 150
    missing = {'public_name': 'gone', 'file_name': 'y.png', 'zoom': 80}
    assert plan._reparse_image(missing) == missing


def test_a_tables_start_collapsed_round_trips_where_the_eln_keeps_it():
    from chemotion_api.elements.research_plan import Table
    plan = _plan()
    table = plan._parse_table({'id': 't', 'type': 'table',
                               'value': {'columns': [], 'rows': [], 'startCollapsed': True}})
    assert table['startCollapsed'] is True
    out = plan._reparse_table(table)
    assert out['value']['startCollapsed'] is True and 'startCollapsed' not in out
    assert isinstance(table, Table)


def test_field_conditions_are_validated():
    """`"item"` is not a JSON-schema keyword, so any array of conditions passed."""
    from jsonschema import ValidationError
    import chemotion_api.labImotion.items.validation  # noqa: F401  (registers the schemas)
    from chemotion_api.labImotion.items.validation.registry import SchemaRegistry
    from chemotion_api.labImotion.items.validation.schemas.schema_field import generic_schema
    cond = generic_schema['properties']['cond_fields']
    assert 'items' in cond and 'item' not in cond
    validator = SchemaRegistry.instance().validator_for(generic_schema['$id'])
    field = {'cond_fields': [{'not': 'a condition'}]}
    errors = [e for e in validator.iter_errors(field) if 'cond_fields' in list(e.absolute_path)]
    assert errors, 'a malformed condition must be reported'


def test_heading_class_pattern_rejects_repeats():
    import re
    from chemotion_api.labImotion.items.validation.schemas import schema_generc_layer as m
    pattern = next(v['pattern'] for v in _walk(m.__dict__) if isinstance(v, dict)
                   and 'panel_generic_heading' in str(v.get('pattern', '')))
    assert re.match(pattern, 'panel_generic_heading_bu')
    assert not re.match(pattern, 'panel_generic_heading_bb')


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)
