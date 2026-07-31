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
