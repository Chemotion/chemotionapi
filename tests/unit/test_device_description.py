"""Device descriptions (M4.3), offline, against a real ELN `main` payload."""
import json
import os

from chemotion_api.elements.device_description import FIELDS, DeviceDescription
from chemotion_api.elements.registry import element_type_info
from chemotion_api.schema_manager import SchemaManager

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'device_description_v4_main.json')


class _About:
    status_code, text = 200, '<h4>Version: v4.0.0</h4>'


class _Session:
    schema_manager = SchemaManager(_About())
    _host_url = 'http://eln.test'


class _Segments:
    all_classes = []


def _device():
    with open(FIXTURE) as f:
        payload = json.load(f)
    dev = DeviceDescription(_Segments(), _Session(), json_data=payload)
    dev._data_loaded = True
    return dev


def test_registered_on_the_standard_routes():
    info = element_type_info('device_description')
    assert (info.cls, info.url, info.response_key) == (DeviceDescription, '/api/v1/device_descriptions',
                                                        'device_description')


def test_properties_and_clean_data():
    dev = _device()
    p = dev.properties
    assert (p['name'], p['vendor_company_name'], p['serial_number']) == ('NMR 400', 'Bruker', 'SN-1')
    assert p['general_tags'] == ['nmr'] and p['operators'][0]['name'] == 'Ada'
    assert set(p) == set(FIELDS)
    p['room'] = '2.01'
    p['version_installation_start_date'] = ''
    out = dev._clean_properties_data()
    assert out['room'] == '2.01' and 'version_installation_start_date' not in out
    assert all(v is not None for v in out.values())
