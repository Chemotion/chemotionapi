import pytest

from chemotion_api import Instance
def test_new_generics(logged_in_instance):
    instance: Instance = logged_in_instance
    col = instance.get_root_collection().find('TEST')[0]
    all_element_classes = instance.all_element_classes
    assert 'dev' in all_element_classes

    a = col.new_generic('dev')
    a.properties['General']['General'][1] = 'Name'
    a.properties['General']['General'][3] = 'Internel Name'
    a.properties['General']['General'][5] = 4
    a.properties['General']['General'][7] = 'DOI---1'
    a.save()
    a1 = instance.get_generic_by_name('dev', a.id)
    a1_copy = instance.get_generic_by_label('Device', a.id)
    assert a1.id == a1_copy.id

    with pytest.raises(ValueError) as e:
        instance.get_generic_by_name('NO VALID NAME', 1)

    with pytest.raises(ValueError) as e:
        instance.get_generic_by_label('NO VALID LABEL', 1)

def test_table_generics(logged_in_instance):
    instance: Instance = logged_in_instance
    all_element_classes = instance.all_element_classes
    assert 'devcl' in all_element_classes

    a = instance.get_generic_by_name('devcl', 9)

    a.properties['General']['Subclass'].append({'Name': 'Test', 'Link': 'Nowhere'})
    a.save()
    pass
#
# def test_all_generics(instance_with_test_samples):
#     instance: Instance = instance_with_test_samples['instance']
#     all_element_classes = instance.all_element_classes
#     assert 'imtl' in all_element_classes
#
#     a = instance.get_root_collection().get_generics_by_name('imtl', 2)
#
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