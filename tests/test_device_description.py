"""Device descriptions against a live ELN v4.0.1: create, fetch, list, edit, save, reload."""
import uuid

from chemotion_api.collection import Collection
from chemotion_api.elements import DeviceDescription


def test_device_description_round_trip(instance_with_collection: dict):
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    name = f'API test device {uuid.uuid4().hex[:8]}'

    device = col.new_device_description()
    assert isinstance(device, DeviceDescription)
    device.properties['name'] = name
    device.properties['serial_number'] = 'SN-1'
    device.properties['general_tags'] = ['nmr']
    device.save()
    assert isinstance(device.id, int), 'the create response should give the element its server id'

    fetched = instance.get_device_description(device.id)
    assert isinstance(fetched, DeviceDescription)
    assert fetched.properties['name'] == name
    assert fetched.properties['serial_number'] == 'SN-1'
    assert fetched.properties['general_tags'] == ['nmr']

    listed = next(d for d in col.get_device_descriptions() if d.id == device.id)
    listed.properties['serial_number'] = 'SN-2'
    listed.properties['vendor_company_name'] = 'Acme'
    listed.save()

    reloaded = instance.get_device_description(device.id)
    assert reloaded.properties['serial_number'] == 'SN-2'
    assert reloaded.properties['vendor_company_name'] == 'Acme'
    assert reloaded.properties['name'] == name
    assert reloaded.ontology_terms() == []
