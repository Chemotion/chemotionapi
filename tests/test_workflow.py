import pytest
import json
from chemotion_api import Instance


def test_current_workflow(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    b = instance.get_generic_by_name('wrk',4)
    current_workflow = b.wf_current_workflow()
    assert current_workflow == [['Nr 1', 'Nr 3'], ['Nr 3', 'Nr 2']]

def test_wf_tree(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    b = instance.get_generic_by_name('wrk',4)
    wf_tree = b.wf_tree()
    assert wf_tree == {'Nr 1': [{'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}, {'Nr 2': []}], 'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}

def test_new_wf(instance_with_collection):
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')
    a.save()
    wf_tree = a.wf_tree()
    current_workflow = a.wf_current_workflow()
    assert current_workflow == [['Nr 1'], ['Nr 3']]
    assert wf_tree == {'Nr 1': [{'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}, {'Nr 2': []}], 'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}

def test_next_wf(instance_with_collection):
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')
    a.save()
    wf_next_options = a.wf_next_options(flat=False)
    a.wf_next(**wf_next_options[1]['options'][0])
    wf_tree = a.wf_tree()
    current_workflow = a.wf_current_workflow()
    assert current_workflow == [['Nr 1'], ['Nr 3', 'Nr 2']]
    assert wf_tree == {'Nr 1': [{'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}, {'Nr 2': []}], 'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}

def test_next_wf_flat(instance_with_collection):
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')
    a.save()
    wf_next_options = a.wf_next_options()
    a.wf_next(**wf_next_options[0])
    wf_tree = a.wf_tree()
    current_workflow = a.wf_current_workflow()
    assert current_workflow == [['Nr 1', 'Nr 3'], ['Nr 3']]
    assert wf_tree == {'Nr 1': [{'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}, {'Nr 2': []}], 'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}

def test_next_blank_wf(instance_with_collection):
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')
    a.save()

    a.wf_next()
    wf_tree = a.wf_tree()
    current_workflow = a.wf_current_workflow()
    assert current_workflow == [['Nr 1', 'Nr 3'], ['Nr 3']]
    assert wf_tree == {'Nr 1': [{'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}, {'Nr 2': []}], 'Nr 3': [{'Nr 2': []}, {'Nr 4': []}]}
    a.wf_next()
    current_workflow = a.wf_current_workflow()
    assert current_workflow == [['Nr 1', 'Nr 3', 'Nr 2'], ['Nr 3']]
    try:
        a.wf_next()
        assert False
    except ValueError:
        assert True
    current_workflow = a.wf_current_workflow()
    assert current_workflow == [['Nr 1', 'Nr 3', 'Nr 2'], ['Nr 3']]

def test_add_layer_wf(instance_with_collection):
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')
    a.save()

    a.wf_add_layer('Nr 2')
    a.wf_add_layer('Nr 4', 15)
    a.save()
    a.load()
    assert list(a.properties.keys()) == ['Fixed', 'Nr 4', 'Nr 1', 'Nr 3', 'Nr 2']
    try:
        a.wf_add_layer('Fixed', 5)
        assert False
    except ValueError:
        assert True


def test_wf_reload(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')

    def option(wf_idx, label):
        return next(x for x in a.wf_next_options() if x['wf_idx'] == wf_idx and x['layer_label'] == label)

    key = a.wf_next(**option(0, 'Nr 3'))
    assert key == 'Nr 3.1'
    a.properties[key]['name_three'] = 'A3'
    a.properties[a.wf_next(**option(1, 'Nr 4'))]['name_four'] = 'B4'
    a.properties[a.wf_next(**option(0, 'Nr 2'))]['name_two'] = 'A2'
    a.properties['Nr 3']['name_three'] = 'B3'
    a.save()

    b = instance.get_generic_by_name('wrk', a.id)
    assert b.wf_current_workflow() == [['Nr 1', 'Nr 3', 'Nr 2'], ['Nr 3', 'Nr 4']]
    assert b.properties['Nr 3.1']['name_three'] == 'A3'
    assert b.properties['Nr 3']['name_three'] == 'B3'
    assert b.properties['Nr 2']['name_two'] == 'A2'
    assert b.properties['Nr 4']['name_four'] == 'B4'
    assert b.wf_next_options() == []


def test_wf_layer_access(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')
    assert (a.label, a.klass_name, a.klass_version) == ('Workflow', 'wrk', '2.0')
    a.wf_next(**next(x for x in a.wf_next_options() if x['wf_idx'] == 0 and x['layer_key'] == 'three'))
    a.wf_layer(0, 'Nr 3')['name_three'] = 'A3'
    a.wf_layer(1, 'three')['name_three'] = 'B3'
    a.save()

    b = instance.get_generic_by_name('wrk', a.id)
    assert [[(x['key'], x['properties_key']) for x in wf['layers']] for wf in b.wf_workflows()] == [
        [('one', 'Nr 1'), ('three.1', 'Nr 3.1')], [('three', 'Nr 3')]]
    assert b.wf_layer(0, 'three.1')['name_three'] == 'A3'
    assert b.wf_layer(b.wf_workflows()[1]['wf_id'], 'Nr 3')['name_three'] == 'B3'
    with pytest.raises(ValueError, match='does not exist'):
        b.wf_layer(1, 'Nr 4')
    with pytest.raises(ValueError, match='No workflow'):
        b.wf_layer(5, 'Nr 3')


def test_generic_element_info(instance_with_collection):
    col = instance_with_collection['main_collection']

    a = col.new_generic('wrk')
    assert a.klass_prefix == 'WRK'
    assert a.layers_without_fields() == ['Fixed']
    assert a.segments.available() == [k for k in a.segments if k not in ('Properties', 'Analyses')]
    a.save()
    assert a.short_label.split('-')[1].startswith('WRK')
