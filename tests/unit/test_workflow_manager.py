import copy
import json
import os

import pytest

from chemotion_api.elements.workflow_manager import Workflow
from chemotion_api.utils import parse_generic_object_json, parse_generic_object_layer_json

# Template "wrk" v2.0 with an element made in the ELN (id 4) and one saved by an earlier API version (id 14)
with open(os.path.join(os.path.dirname(__file__), 'data', 'workflow_wrk.json')) as f:
    DATA = json.load(f)


def _element(name=None):
    json_data = {'properties_release': copy.deepcopy(DATA['properties_release'])}
    if name is None:
        layers = {k: v for k, v in copy.deepcopy(DATA['properties_release']['layers']).items() if not v['wf']}
        json_data['properties'] = {'layers': layers}
    else:
        json_data['properties'] = copy.deepcopy(DATA[name])
    return json_data


def _load(json_data):
    wf = Workflow(json_data['properties_release'])
    wf.init_wf(json_data)
    return wf


def _labels(wf):
    return [[x['label'] for x in w['layers']] for w in wf.workflows]


def _keys(wf):
    return [[x['key'] for x in w['layers']] for w in wf.workflows]


def _option(wf, wf_idx, label):
    return next(x for x in wf.next_options() if x['wf_idx'] == wf_idx and x['layer_label'] == label)


def test_read_ui_element():
    wf = _load(_element('ui_element'))
    assert _labels(wf) == [['Nr 1', 'Nr 3'], ['Nr 3', 'Nr 2']]
    assert _keys(wf) == [['one', 'three.1'], ['three', 'two']]


def test_repair_legacy_api_element():
    json_data = _element('legacy_api_element')
    wf = _load(json_data)
    assert _labels(wf) == [['Nr 1', 'Nr 3', 'Nr 2'], ['Nr 3', 'Nr 4']]
    layers = json_data['properties']['layers']
    assert layers['three.1']['key'] == 'three.1'
    assert layers['two']['wf_info']['source_layer'] == 'three.1'
    assert layers['four']['wf_info']['source_layer'] == 'three'
    assert all('source_layer' not in x for x in layers.values())


def test_next_writes_eln_format_and_survives_reload():
    json_data = _element()
    wf = _load(json_data)
    assert _labels(wf) == [['Nr 1'], ['Nr 3']]
    wf.next(json_data, **_option(wf, 0, 'Nr 3'))
    wf.next(json_data, **_option(wf, 1, 'Nr 4'))
    key, layer = wf.next(json_data, **_option(wf, 0, 'Nr 2'))
    expected = [['Nr 1', 'Nr 3', 'Nr 2'], ['Nr 3', 'Nr 4']]
    assert _labels(wf) == expected

    layers = json_data['properties']['layers']
    duplicate = next(k for k, x in layers.items() if k != 'three' and x['label'] == 'Nr 3')
    assert duplicate == 'three.1' and layers[duplicate]['key'] == 'three.1'
    assert layer['wf_info'] == {'node_id': layer['wf_info']['node_id'], 'source_layer': 'three.1'}
    assert all('source_layer' not in x for x in layers.values())

    reloaded = _load(json.loads(json.dumps(json_data)))
    assert _labels(reloaded) == expected


def test_property_names_do_not_change_on_reload():
    json_data = _element()
    wf = _load(json_data)
    values = parse_generic_object_json(json_data)['values']
    mapping = {}
    key, layer = wf.next(json_data, **_option(wf, 0, 'Nr 3'))
    assert parse_generic_object_layer_json(key, layer, values, mapping) == 'Nr 3.1'
    assert mapping['Nr 3.1']['__key'] == 'three.1'

    reloaded = parse_generic_object_json(json.loads(json.dumps(json_data)))
    assert reloaded['obj_mapping']['Nr 3']['__key'] == 'three'
    assert reloaded['obj_mapping']['Nr 3.1']['__key'] == 'three.1'


def test_layers_are_ordered_by_workflow_position():
    values = parse_generic_object_json(_element('legacy_api_element'))['values']
    assert list(values) == ['Fixed', 'Nr 1', 'Nr 3.1', 'Nr 2', 'Nr 3', 'Nr 4']


def test_next_options_describe_workflow_and_layer():
    json_data = _element()
    wf = _load(json_data)
    wf.next(json_data, **_option(wf, 0, 'Nr 3'))
    option = _option(wf, 0, 'Nr 2')
    assert option['wf_id'] == wf.workflows[0]['id']
    assert option['layer_key'] == 'two'
    assert option['source_key'] == 'three.1'
    assert option['source_layer'] == 'Nr 1 -> Nr 3'
    assert [x['wf_idx'] for x in wf.next_options(flat=False)] == [0, 1]
    # A finished workflow has no options
    wf_ui = _load(_element('ui_element'))
    assert {x['wf_idx'] for x in wf_ui.next_options()} == {0}


def test_next_with_wrong_arguments():
    json_data = _element()
    wf = _load(json_data)
    with pytest.raises(ValueError, match='No workflow with id'):
        wf.next(json_data, wf_id='unknown')
    with pytest.raises(ValueError, match='No workflow with index'):
        wf.next(json_data, wf_idx=5)
    # Nr 4 follows Nr 3 only, not Nr 1 (workflow 0)
    with pytest.raises(ValueError, match='is not a next step'):
        wf.next(json_data, layer_id=_option(wf, 1, 'Nr 4')['layer_id'], wf_idx=0)


def test_layer_without_label_is_named_by_its_key():
    values, mapping = {}, {}
    assert parse_generic_object_layer_json('three.1', {'key': 'three.1', 'label': '', 'fields': []},
                                           values, mapping) == 'three.1'
