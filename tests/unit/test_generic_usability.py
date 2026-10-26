import json
import os
from types import SimpleNamespace

import pytest

from chemotion_api.elements.abstract_element import Analyses
from chemotion_api.elements.attachments import Attachment
from chemotion_api import labImotion
from chemotion_api.element_manager import ElementManager
from chemotion_api.labImotion import GenericManager, GenericElementKlass, ontology
from chemotion_api.labImotion.items import genericproperties
from chemotion_api.labImotion.items.fields import FieldType
from chemotion_api.labImotion.items.genericproperties import GenericProperties
from chemotion_api.labImotion.items.options import ElementType
from chemotion_api.utils import clean_generic_object_json
from chemotion_api.utils.segment_fields import SegmentField


def _klass(id, name, label, version):
    return SimpleNamespace(id=id, name=name, label=label, version=version, is_active=True)


@pytest.fixture
def manager(monkeypatch):
    klasses = [_klass(1, 'wrk', 'Workflow', '1.0'), _klass(2, 'wrk', 'Workflow', '2.0'),
               _klass(3, 'plan', 'Plan', '1.0')]
    monkeypatch.setattr(GenericElementKlass, 'load_all', classmethod(lambda cls, con: klasses))
    return GenericManager(None)


def test_template_class_alias():
    assert labImotion.GenericElement is GenericElementKlass


def test_get_element_by_name_label_and_version(manager):
    assert manager.get_element('plan').id == 3
    assert manager.get_element('wrk', version='2.0').id == 2
    assert manager.get_element(label='Workflow', version='1.0').id == 1
    assert manager.get_element(id=3).name == 'plan'


def test_get_element_errors_list_candidates(manager):
    with pytest.raises(KeyError, match=r"Multiple results.*Workflow \(name=wrk, version=1.0, id=1\).*version=2.0"):
        manager.get_element('wrk')
    with pytest.raises(KeyError, match=r"No element found.*Available: .*Plan"):
        manager.get_element('xyz')


def test_analyses_attribute_access():
    ana = Analyses({'id': 7, 'name': 'QA check', 'description': '', 'extended_metadata': {'kind': 'NMR'},
                    'children': []}, None)
    assert ana.name == 'QA check' and ana.kind == 'NMR' and ana.id == 7 and ana.datasets == []
    ana.name = 'Renamed'
    assert ana['name'] == 'Renamed'
    with pytest.raises(AttributeError):
        ana.unknown


def test_attachment_attribute_access():
    att = Attachment(None, {'id': 3, 'filename': 'a.txt'})
    assert att.filename == 'a.txt' and att.id == 3
    att.filename = 'b.txt'
    assert att['filename'] == 'b.txt'
    with pytest.raises(AttributeError):
        att.unknown


def _klass_json(**changes) -> dict:
    with open(os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'GenericElement.json')) as f:
        json_data = json.load(f)
    return json_data | changes


def test_template_authoring_keeps_labels_and_generates_valid_keys():
    klass = GenericElementKlass(_klass_json(), None)
    layer = klass.properties.add_new_layer('Cultivation (°C)')
    assert layer.key == 'cultivation_c'
    assert klass.properties.add_new_layer('Cultivation (°C)').key == 'cultivation_c_a'
    with pytest.raises(ValueError, match='already exists'):
        klass.properties.add_new_layer('Other', key='con')

    temp = layer.add_field(FieldType.INTEGER, 'Incubation temperature (°C)')
    assert (temp.label, temp.field) == ('Incubation temperature (°C)', 'incubation_temperature_c')
    assert layer.add_field(FieldType.TEXT, 'Incubation temperature (°C)').field == 'incubation_temperature_c_a'
    assert layer.add_field(FieldType.TEXT, 'pH').field == 'ph_field'
    assert layer.add_field(FieldType.TEXT, 'Strain', field='strain').field == 'strain'
    with pytest.raises(ValueError, match='already exists'):
        layer.add_field(FieldType.TEXT, 'Strain 2', field='strain')
    klass.properties.validate(klass.to_dict()['properties_template'])


def test_select_field_with_own_options_and_without_option_layers():
    template = _klass_json()['properties_template'] | {'select_options': {}}
    klass = GenericElementKlass(_klass_json(properties_template=template | {'layers': {}}), None)
    layer = klass.properties.add_new_layer('General')
    unlinked = layer.add_field(FieldType.SELECT, 'Unlinked')
    assert unlinked.option_layers == ''

    medium = layer.add_field(FieldType.SELECT, 'Growth medium', options=['LB', 'TB'])
    assert medium.option_layers == 'growth_mediu'
    assert klass.properties.select_options['growth_mediu']['options'] == [{'key': 'LB', 'label': 'LB'},
                                                                          {'key': 'TB', 'label': 'TB'}]
    with pytest.raises(ValueError, match='only supported for SELECT'):
        layer.add_field(FieldType.TEXT, 'Text', options=['a'])
    with pytest.raises(ValueError, match='add_select_option'):
        unlinked.option_layers = 'unknown'


def test_field_default_and_required_are_stored():
    klass = GenericElementKlass(_klass_json(), None)
    field = klass.properties.add_new_layer('General').add_field(FieldType.CHECKBOX, 'Done')
    field.required = True
    field.default = 'x'
    assert field.to_dict()['required'] is True and field.to_dict()['default'] == 'x'
    with pytest.raises(TypeError):
        field.required = 'yes'


def test_klass_prefix_is_exposed():
    klass = GenericElementKlass(_klass_json(), None)
    assert klass.klass_prefix == 'ttt'
    klass.klass_prefix = 'MB'
    assert klass.to_dict()['klass_prefix'] == 'MB'


def test_zero_based_layer_positions_and_invalid_release_copy_can_be_loaded():
    json_data = _klass_json()
    json_data['properties_template']['layers']['con']['position'] = 0
    json_data['properties_release'] = {'layers': 'broken'}
    klass = GenericElementKlass(json_data, None)
    assert klass.properties.get_layer_by_key('con').position == 0
    with pytest.raises(TypeError):
        klass.release


def test_load_all_skips_invalid_templates():
    broken = _klass_json(id=11)
    del broken['properties_template']
    con = SimpleNamespace(get=lambda url: SimpleNamespace(status_code=200,
                                                          json=lambda: {'klass': [_klass_json(), broken]}))
    with pytest.warns(UserWarning, match=r"Skipped invalid GenericElementKlass 'zzz' \(id=11\)"):
        assert [k.id for k in GenericElementKlass.load_all(con)] == [10]
    with pytest.raises(KeyError):
        GenericElementKlass.load_all(con, strict=True)


def test_dataset_properties_are_not_validated_as_element_properties(monkeypatch):
    calls = []
    monkeypatch.setattr(genericproperties, 'validate_generic_dataset_properties', lambda d: calls.append('dataset'))
    monkeypatch.setattr(genericproperties, 'validate_generic_properties', lambda d: calls.append('element'))
    props = GenericProperties({}, ElementType.DATASET, None)
    props.validate()
    assert calls == ['dataset']


def test_unknown_property_names_raise_value_error():
    json_data = {'properties': {'layers': {'gen': {'fields': [{'field': 'strain', 'type': 'text'}]}}}}
    mapping = {'__id': 1, 'General': {'__key': 'gen', 'strain': 'strain'}}
    with pytest.raises(ValueError, match=r'Unknown field "Strain" in layer "General".*Available: strain'):
        clean_generic_object_json(json_data, {'General': {'Strain': 'E. coli'}}, mapping)
    with pytest.raises(ValueError, match=r'Unknown layer "Cultivation". Available: General'):
        clean_generic_object_json(json_data, {'Cultivation': {}}, mapping)


def test_element_manager_reload_clears_cache():
    manager = ElementManager(None)
    manager._all_classes, manager._all_types, manager.is_loaded = {'a': {}}, ['x'], True
    manager.reload()
    assert (manager._all_classes, manager._all_types, manager.is_loaded) == (None, None, False)


NMR_TERM = {'id': 'chmo:class:http://purl.obolibrary.org/obo/CHMO_0000593',
            'iri': 'http://purl.obolibrary.org/obo/CHMO_0000593', 'label': '1H nuclear magnetic resonance spectroscopy',
            'short_form': 'CHMO_0000593', 'obo_id': 'CHMO:0000593', 'ontology_name': 'chmo', 'ontology_prefix': 'CHMO',
            'description': ['Spectroscopy where ...'], 'type': 'class'}


@pytest.fixture
def terminology_service(monkeypatch):
    docs = [NMR_TERM | {'id': 'msio:class:...', 'ontology_name': 'msio', 'ontology_prefix': 'MSIO'}, NMR_TERM,
            {'iri': 'http://purl.obolibrary.org/obo/BAO_0000593', 'label': 'protein-RNA interaction assay',
             'obo_id': 'BAO:0000593', 'short_form': 'BAO_0000593', 'ontology_prefix': 'BAO'}]
    requests_made = []

    def get(url, params, timeout):
        requests_made.append((url, params))
        return SimpleNamespace(status_code=200, json=lambda: {'response': {'docs': docs}})

    monkeypatch.setattr(ontology.requests, 'get', get)
    return requests_made


def test_ontology_term_lookup_prefers_the_terms_own_ontology(terminology_service):
    assert ontology.get_term('CHMO:0000593') == NMR_TERM
    assert ontology.get_term('chmo_0000593')['ontology_name'] == 'chmo'
    assert ontology.get_term('http://purl.obolibrary.org/obo/BAO_0000593')['label'] == 'protein-RNA interaction assay'
    assert terminology_service[-1][0] == 'https://api.terminology.tib.eu/api/select'
    assert ('q', 'BAO_0000593') in terminology_service[-1][1] and ('caller', 'NFDI4CHEM') in terminology_service[-1][1]
    with pytest.raises(KeyError, match='No ontology term'):
        ontology.get_term('CHMO:9999999')
    with pytest.raises(ValueError):
        ontology.search_terms('x')


def test_field_ontology_is_set_validated_and_saved(terminology_service):
    klass = GenericElementKlass(_klass_json(), None)
    layer = klass.properties.add_new_layer('Measurement')
    by_id = layer.add_field(FieldType.TEXT, 'NMR method', ontology='CHMO:0000593')
    assert by_id.ontology == NMR_TERM
    by_dict = layer.add_field(FieldType.TEXT, 'Other')
    by_dict.ontology = NMR_TERM | {'extra': 'dropped'}
    assert by_dict.ontology == NMR_TERM and by_dict.to_dict()['ontology'] == NMR_TERM
    with pytest.raises(TypeError, match='iri'):
        by_dict.ontology = {'label': 'no iri'}
    by_dict.ontology = None
    assert 'ontology' not in by_dict.to_dict()
    template = klass.to_dict()['properties_template']
    klass.properties.validate(template)

    # Terms set in the Chemotion UI (or trimmed to the IRI by an export) are loaded and kept
    reloaded = GenericElementKlass(_klass_json(properties_template=template), None)
    fields = reloaded.properties.get_layer_by_key('measurement').fields
    assert fields[0].ontology == NMR_TERM and fields[1].ontology is None
    template['layers']['measurement']['fields'][1]['ontology'] = {'iri': NMR_TERM['iri']}
    reloaded = GenericElementKlass(_klass_json(properties_template=template), None)
    assert reloaded.properties.get_layer_by_key('measurement').fields[1].ontology == {'iri': NMR_TERM['iri']}


def test_segment_field_exposes_ontology():
    assert SegmentField({'field': 'f', 'type': 'text', 'ontology': NMR_TERM}, 'l').ontology == NMR_TERM
    assert SegmentField({'field': 'f', 'type': 'text'}, 'l').ontology is None
