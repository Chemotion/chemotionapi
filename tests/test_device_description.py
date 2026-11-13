"""Device descriptions against a live ELN v4.0.1: list, load, edit, save, reload.

The seed has none, so the test creates one through the server's own create route (this client
has no constructor for the type) and then exercises only the client's paths.
"""
import uuid

from chemotion_api.collection import Collection
from chemotion_api.elements import DeviceDescription


def test_device_description_round_trip(instance_with_collection: dict):
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    name = f'API test device {uuid.uuid4().hex[:8]}'
    res = instance._con.post('/api/v1/device_descriptions',
                             data={'collection_id': col.id, 'name': name, 'serial_number': 'SN-1'})
    assert res.status_code in (200, 201), res.text
    created_id = res.json()['device_description']['id']

    listed = list(col.get_device_descriptions())
    device = next(d for d in listed if d.id == created_id)
    assert isinstance(device, DeviceDescription)
    assert device.properties['name'] == name
    assert device.properties['serial_number'] == 'SN-1'

    device.properties['serial_number'] = 'SN-2'
    device.properties['vendor_company_name'] = 'Acme'
    device.save()

    reloaded = next(d for d in col.get_device_descriptions() if d.id == created_id)
    assert reloaded.properties['serial_number'] == 'SN-2'
    assert reloaded.properties['vendor_company_name'] == 'Acme'
    assert reloaded.properties['name'] == name
    assert reloaded.ontology_terms() == []
