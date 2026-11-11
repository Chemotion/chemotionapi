import pytest

from chemotion_api import Instance

def test_new_generics(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    col = instance_with_collection['main_collection']
    all_element_classes = instance.all_element_classes
    assert 'try' in all_element_classes

    a = col.new_generic('try')
    a.properties['Nr. 1']['Group'][0] = 'Name'
    a.properties['Nr. 1']['Group'][1] = 1
    a.properties['Nr. 1']['Group'][2] = 'DOI---1'
    a.save()
    a1 = instance.get_generic_by_name('try', a.id)
    a1_copy = instance.get_generic_by_label('Tryout', a.id)
    assert a1.id == a1_copy.id

    with pytest.raises(ValueError) as e:
        instance.get_generic_by_name('NO VALID NAME', 1)

    with pytest.raises(ValueError) as e:
        instance.get_generic_by_label('NO VALID LABEL', 1)

    test = instance.get_json_ld_id(a1.json_ld['@id'])
    assert test.json_ld == a1.json_ld


def test_generic_by_name_refuses_an_element_of_another_type(instance_with_collection):
    """Issue #14: the id decides what you get, not the type in the request.

    The server resolves a generic element by id alone, so asking for one type and passing the id
    of another used to return the wrong element silently — a `try` request yielding a `wrk`
    object, with nothing to indicate it. Reported against 312.0; confirmed still present on ELN
    v4.0.1 before this fix.
    """
    instance: Instance = instance_with_collection['instance']
    col = instance_with_collection['main_collection']

    created = col.new_generic('try')
    created.save()

    # the same id, requested as a different generic type that also exists on this server
    other = next(name for name in instance.all_element_classes
                 if name != 'try' and instance.all_element_classes[name].get('is_generic'))
    with pytest.raises(ValueError, match='not a'):
        instance.get_generic_by_name(other, created.id)

    # and by label, which delegates to the same path
    other_label = instance.all_element_classes[other]['label']
    with pytest.raises(ValueError, match='not a'):
        instance.get_generic_by_label(other_label, created.id)

    # the correct type is unaffected
    assert instance.get_generic_by_name('try', created.id).id == created.id

def test_generic_field_template(instance_with_collection):
    col = instance_with_collection['main_collection']
    a = col.new_generic('try')
    field = a.field('Nr. 1', 'Group')
    assert field.type == 'input-group' and field.ontology is None
    with pytest.raises(KeyError, match='Unknown field'):
        a.field('Nr. 1', 'No field')


def test_table_generics(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    col = instance_with_collection['main_collection']
    all_element_classes = instance.all_element_classes
    assert 'try' in all_element_classes

    a = col.new_generic('try')
    a.properties['Nr. 1']['Group'][1] = 2
    a.properties['Nr. 1']['Group'][2] = 'DOI---2'
    a.properties['Nr. 1']['Table'].append({'Col 1': 'Hallo A', 'Col 2': 'Hallo B'})
    a.save()
    pass
#
# def test_all_generics(instance_with_test_samples):
#     instance: Instance = instance_with_test_samples['instance']
#     all_element_classes = instance.all_element_classes
#     assert 'imtl' in all_element_classes
#
#     a = instance.get_root_collection().get_generics_by_name('imtl', 2)
#generic_manager
#     a1 = instance.get_generic_by_name('imtl', a[0].id)
#     a1_copy = instance.get_generic_by_label('IMTLaufkarte', a[0].id)
#     assert a1.id == a1_copy.id
#
#     with pytest.raises(ValueError) as e:
#         instance.get_generic_by_name('NO VALID NAME', 1)
#
#     with pytest.raises(ValueError) as e:
#         instance.get_generic_by_label('NO VALID LABEL', 1)
# def test_edit_generics(instance_with_test_samples):
#     instance: Instance = instance_with_test_samples['instance']
#     all_element_classes = instance.all_element_classes
#     assert 'imtl' in all_element_classes
#
#     a = instance.get_root_collection().get_generics_by_name('imtl', 2)
#     a[0].properties['General data']['Auftraggeber'] = "Martin Test"
#     a[0].save()
#     a1 = instance.get_generic_by_name('imtl', a[0].id)
#     assert a1.properties['General data']['Auftraggeber'] == "Martin Test"