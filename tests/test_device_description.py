"""Device descriptions on a live ELN (M4.3)."""
import zipfile

import pytest

pytestmark = pytest.mark.integration


def test_device_description_lifecycle(instance_with_collection, tmp_path):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    dev = col.new_device_description()
    dev.properties.update(name='NMR 400', vendor_company_name='Bruker', room='1.23', general_tags=['nmr'],
                          operators=[{'name': 'Ada', 'email': 'ada@example.org', 'type': 'technical'}])
    dev.save()
    assert dev.id and dev.short_label.startswith('API-Dev')

    loaded = instance.get_device_description(dev.id)
    assert loaded.properties['operators'][0]['email'] == 'ada@example.org'
    loaded.properties['serial_number'] = 'SN-1'
    log = tmp_path / 'calibration.txt'
    log.write_text('ok')
    loaded.analyses.add_analyses('calibration').add_dataset(str(log))
    loaded.save()

    again = instance.get_device_description(dev.id)
    assert again.properties['serial_number'] == 'SN-1'
    assert [a['name'] for a in again.analyses] == ['calibration']
    assert zipfile.is_zipfile(again.download_analyses(str(tmp_path / 'analyses.zip')))
    assert isinstance(instance.device_ontologies(), list)

    (sub,) = col.split_device_descriptions(again)
    assert sub.short_label == f'{dev.short_label}-1' and sub.ancestor_ids == [dev.id]
    assert {d.id for d in col.get_device_descriptions()} == {dev.id, sub.id}
    assert sub.delete()
    assert [d.id for d in col.get_device_descriptions()] == [dev.id]
