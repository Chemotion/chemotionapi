import copy

import pytest

from chemotion_api.elements.reaction import VariationSegments
from chemotion_api.utils import clean_generic_object_json
from chemotion_api.utils.segment_fields import iter_fields

KLASS = {
    'label': 'Electrochemistry',
    'properties_release': {
        'select_options': {
            'electrode': {'options': [{'key': 'traditional', 'label': 'disk'},
                                      {'key': 'mesh', 'label': 'mesh'}]},
        },
        'layers': {
            'cell': {
                'key': 'cell', 'label': 'Cell', 'position': 1,
                'fields': [
                    {'field': 'electrode', 'label': 'Electrode type', 'type': 'select',
                     'option_layers': 'electrode', 'position': 1},
                    {'field': 'current', 'label': 'Current [A]', 'type': 'system-defined',
                     'option_layers': 'current', 'value_system': '', 'position': 2},
                    {'field': 'temp', 'label': 'Temperature', 'type': 'system-defined',
                     'option_layers': 'temperature', 'value_system': 'C', 'position': 3},
                    {'field': 'cycles', 'label': 'Cycles', 'type': 'integer', 'position': 4},
                    {'field': 'note', 'label': 'Note', 'type': 'text', 'position': 5},
                    {'field': 'file', 'label': 'File', 'type': 'upload', 'position': 6},
                ],
            },
        },
    },
}


def _fields():
    return {name: field for _, name, field in iter_fields(KLASS['properties_release'])}


def _segments(raw=None):
    return VariationSegments(raw or {}, lambda: {KLASS['label']: KLASS})


def test_field_helpers():
    fields = _fields()
    assert fields['Electrode type'].type == 'select'
    assert fields['Electrode type'].options() == [{'key': 'traditional', 'label': 'disk'},
                                                  {'key': 'mesh', 'label': 'mesh'}]
    assert fields['Electrode type'].option_key('disk') == 'traditional'
    assert fields['Electrode type'].option_label('traditional') == 'disk'
    assert fields['Temperature'].units() == ['C', 'F', 'K']
    with pytest.raises(TypeError):
        fields['Note'].options()


def test_clean_value():
    fields = _fields()
    assert fields['Electrode type'].clean_value('disk') == 'traditional'
    assert fields['Temperature'].clean_value(25) == {'value': 25, 'unit': 'C'}
    with pytest.raises(ValueError):
        fields['Electrode type'].clean_value('ring')
    with pytest.raises(ValueError):
        fields['Temperature'].clean_value({'value': 25, 'unit': 'mA'})
    with pytest.raises(ValueError):
        fields['Cycles'].clean_value(1.5)


def test_segment_save_validates_changed_values_only():
    segment = {'properties': copy.deepcopy(KLASS['properties_release'])}
    segment['properties']['layers']['cell']['fields'][0]['value'] = 'stale-key'
    mapping = {'Cell': {'__key': 'cell', 'Electrode type': 'electrode', 'Temperature': 'temp'}}

    # Unchanged values loaded from the server are saved as they are
    clean_generic_object_json(segment, {'Cell': {'Electrode type': 'stale-key'}}, mapping)

    clean_generic_object_json(segment, {'Cell': {'Electrode type': 'disk', 'Temperature': 30}}, mapping)
    fields = segment['properties']['layers']['cell']['fields']
    assert fields[0]['value'] == 'traditional'
    assert (fields[2]['value'], fields[2]['value_system']) == (30, 'C')

    with pytest.raises(ValueError, match='Electrode type'):
        clean_generic_object_json(segment, {'Cell': {'Electrode type': 'ring'}}, mapping)


def test_variation_segment_has_every_field():
    segments = _segments()
    segments['Electrochemistry']['Cell']['Electrode type'] = 'traditional'
    segments['Electrochemistry']['Cell']['Temperature'] = 40
    entries = segments.clean()['Electrochemistry']

    assert set(entries) == {'layer<cell>field<electrode>', 'layer<cell>field<current>',
                            'layer<cell>field<temp>', 'layer<cell>field<cycles>', 'layer<cell>field<note>'}
    assert entries['layer<cell>field<electrode>'] == {
        'type': 'select', 'label': 'Electrode type', 'options': ['disk', 'mesh'], 'value': 'disk',
        'unit': None, 'quantity': 'electrode'}
    assert entries['layer<cell>field<temp>'] == {
        'type': 'system-defined', 'label': 'Temperature', 'value': 40.0, 'unit': 'C', 'quantity': 'temperature'}
    assert entries['layer<cell>field<current>']['value'] is None


def test_variation_segment_round_trip():
    segments = _segments()
    segments['Electrochemistry']['Cell']['Note'] = 'run 1'
    loaded = _segments(segments.clean())
    assert loaded['Electrochemistry']['Cell']['Note'] == 'run 1'
    assert loaded['Electrochemistry']['Cell']['Electrode type'] == 'disk'


def test_variation_field_without_default_unit():
    segments = _segments()
    segments['Electrochemistry']['Cell']['Current [A]'] = {'value': 10, 'unit': 'mA'}
    with pytest.raises(ValueError, match='no default unit'):
        segments.clean()


def test_variation_unknown_segment_and_field():
    segments = _segments()
    with pytest.raises(KeyError):
        segments['Unknown']
    segments['Electrochemistry']['Cell']['File'] = 'x.txt'
    with pytest.raises(KeyError):
        segments.clean()
