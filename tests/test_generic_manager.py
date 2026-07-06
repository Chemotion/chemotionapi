import copy
import json
import os

import pytest
from jsonschema import ValidationError
from jsonschema.validators import validate

from chemotion_api import GenericManager
from chemotion_api.labImotion.items.options import SaveActionType, FieldType, SubFieldType, SubTableFieldType, FieldUnit
from chemotion_api.labImotion.items.validation import validate_generic_element, validate_generic_dataset, validate_generic_segment
from chemotion_api.labImotion.items.validation.schemas.schema_select_options import generic_schema

HERE = os.path.dirname(os.path.abspath(__file__))  # resolve fixtures relative to this file, not the CWD

def test_write_all_schemas(instance_with_collection):
    instance_with_collection['instance'].generic_manager().write_all_validation_schemas()
    assert True

def test_no_schema_drift_on_seeded_instance(logged_in_instance):
    """The bundled schemas (LabIMotion 2.1.1 / ELN v3.1.2) must accept every klass the
    seeded test instance serves — the live counterpart of the offline drift unit tests."""
    report = logged_in_instance.generic_manager().check_schema_drift()
    assert all(issues == [] for issues in report.values()), report

@pytest.mark.parametrize(
"json_file", ['fixtures/GenericElement.json']
)
def test_validate_generic_element(json_file):
    with open(os.path.join(HERE, json_file)) as file:
        json_value = json.loads(file.read())
    validate_generic_element(json_value)


@pytest.mark.parametrize(
"json_file", ["fixtures/GenericDataset.json"]
)
def test_validate_generic_dataset(json_file):
    with open(os.path.join(HERE, json_file)) as file:
        json_value = json.loads(file.read())
    validate_generic_dataset(json_value)


@pytest.mark.parametrize(
"json_file", ["fixtures/GenericSegment.json"]
)
def test_validate_generic_segment(json_file):
    with open(os.path.join(HERE, json_file)) as file:
        json_value = json.loads(file.read())
    validate_generic_segment(json_value)

@pytest.mark.parametrize(
    "json_to_test",
    [
        {
            "aaa": {
                "options": [
                    {
                        "key": "a",
                        "label": "a"
                    },
                    {
                        "key": "b",
                        "label": "b"
                    }
                ]
            }
        },
        {
            "aBa": {
                "options": [
                    {
                        "key": "a",
                        "label": "a"
                    }
                ]
            }
        }
    ]
)
def test_generic_selection_schema_success(json_to_test):
    assert validate(json_to_test, generic_schema) is None

@pytest.mark.parametrize(
    "json_to_test",
    [
        {
            "aaa": {

            }
        },
        {
            "aBa": {
                "options": [
                    {
                        "key": "a",
                    }
                ]
            }
        },
        {
            "aBa": {
                "options": [
                    {
                        "label": "a",
                    }
                ]
            }
        },
        {
            "aa": {
                "options": [
                    {
                        "key": "a",
                        "label": "a",
                    }
                ]
            }
        }
    ]
)
def test_generic_selection_schema_error(json_to_test):
    try:
        validate(json_to_test, generic_schema)
        assert False
    except ValidationError:
        assert True


def test_read_generic_elements(instance_with_collection):
    try:
        all_gs = instance_with_collection['instance'].generic_manager().load_all_elements()
    except ValidationError:
        assert False

    # The number of built-in klasses grows with the server release (9 on 2.1.1, 10 on 3.1.2);
    # what the seed guarantees is the two generic klasses (wrk, try).
    assert len(all_gs) >= 9
    all_gs = [x for x in all_gs if x.is_generic]
    assert len(all_gs) == 2
    all_gs[0].label += '_TEST'
    old_dict = copy.deepcopy(all_gs[0]._json_data)
    dict_element = all_gs[0].to_dict()
    old_dict['label'] += '_TEST'
    old_dict['properties_template']['identifier'] = dict_element['properties_template']['identifier']
    old_dict['uuid'] = dict_element['uuid']
    for _key, layer  in old_dict['properties_template']['layers'].items():
        for field in layer['fields']:
            if field['type'] == 'text' and 'required' not in field:
                field['required'] = False

    assert old_dict == dict_element

def test_read_generic_segments(instance_with_collection):
    try:
        all_gs = instance_with_collection['instance'].generic_manager().load_all_segments()
    except ValidationError:
        assert False
    assert len(all_gs) == 1
    pass

def test_read_generic_datasets(instance_with_collection):
    try:
        all_gs = instance_with_collection['instance'].generic_manager().load_all_datasets()
    except ValidationError:
        assert False

    assert len(all_gs) == 8
    pass

def test_upload_generic_element(instance_with_collection):
    all_old_gs = instance_with_collection['instance'].generic_manager().load_all_elements()
    element_fp = os.path.join(os.path.dirname(__file__), 'fixtures/GenericElement.json')
    all_gs = instance_with_collection['instance'].generic_manager().upload_elements_json(element_fp)
    assert len(all_old_gs) + 1 == len(all_gs)

def test_upload_generic_segment(instance_with_collection):
    all_old_gs = instance_with_collection['instance'].generic_manager().load_all_segments()
    element_fp = os.path.join(os.path.dirname(__file__), 'fixtures/GenericSegment.json')
    all_gs = instance_with_collection['instance'].generic_manager().upload_segment_json(element_fp)
    assert len(all_old_gs) + 1 == len(all_gs)



def test_new_element(instance_with_collection):
    gm: GenericManager = instance_with_collection['instance'].generic_manager()
    all_gs = gm.load_all_elements()
    new_all_gs = gm.create_new_element('T TEST', 'american-sign-language-interpreting')
    assert len(all_gs) == len(new_all_gs) - 1
    new_all_gs = gm.create_new_element('T TEST', 'american-sign-language-interpreting')
    assert len(all_gs) == len(new_all_gs) - 2



def test_new_segment(instance_with_collection):
    gm: GenericManager = instance_with_collection['instance'].generic_manager()
    all_gs = gm.load_all_segments()
    all_ge = gm.load_all_elements()
    new_all_gs = gm.create_new_segment('T TEST', 'Some', all_ge[0])
    assert len(all_gs) == len(new_all_gs) - 1
    try:
        new_all_gs = gm.create_new_segment('T TEST', 'thing', all_ge[-1])
        assert False
    except ValueError:
        assert True
    all_ge[-1].activate()
    ttes = gm.get_segment(label = 'T TEST')
    ttes.label = "T Test 2"
    ttes.save()
    new_all_gs = gm.create_new_segment('T TEST', 'thing', all_ge[-1])
    assert len(all_gs) == len(new_all_gs) - 2

def test_element_new_layer(instance_with_collection):
    gm: GenericManager = instance_with_collection['instance'].generic_manager()
    ttes = gm.get_element(name = 'ttes')
    ttes.properties.add_new_layer('My New Layer')
    dc = ttes.to_dict()
    try:
        ttes.validate(dc)
    except ValidationError:
        assert False
    ttes.save()
    ttes.save(SaveActionType.MAJOR)
    ttes.save(SaveActionType.MINOR)
    ttes = gm.get_element(name = 'ttes')
    assert '1.1' == ttes.version


def test_element_new_fields(instance_with_collection):
    gm: GenericManager = instance_with_collection['instance'].generic_manager()
    ttes = gm.get_element(name = 'ttes')
    ttes.properties.add_select_option('test', ['Yes', 'No'])
    layer = ttes.properties.add_new_layer('My New Layer 2')
    for field_name in FieldType.list():
        field = layer.add_field(FieldType(field_name),  field_name)
        if field.field_type == FieldType.SELECT:
            field.option_layers = 'test'
    for field in layer.fields:
        if field.field_type == FieldType.FORMULA_FIELD:
            field.formula = '(integer+3.5)*5'
            field.decimal = 5
        if field.field_type == FieldType.INPUT_GROUP:
            for sf_type in SubFieldType.list():
                sub_field = field.add_subfield(SubFieldType(sf_type))
                if sub_field.field_type == SubFieldType.NUMBER:
                    sub_field.value = 2.4
                elif sub_field.field_type == SubFieldType.LABEL:
                    sub_field.value = "TEST LABEL"
                elif sub_field.field_type == SubFieldType.TEXT:
                    sub_field.value = "TEST TEXT"
                elif sub_field.field_type == SubFieldType.SYSTEM_DEFINED:
                    sub_field.option_layers = FieldUnit.ELECTRIC_FIELD

        if field.field_type == FieldType.TABLE:
            for sf_type in SubTableFieldType.list():
                sub_field = field.add_subfield(SubTableFieldType(sf_type), sf_type)
                if sub_field.field_type == SubTableFieldType.DRAG_SAMPLE:
                    sub_field.set_sample_display(name = True, external_label = True, molecular_weight = True)
                elif sub_field.field_type == SubTableFieldType.DRAG_MOLECULE:
                    sub_field.set_sample_display(inchikey = True, smiles = True, iupac = True, molecular_weight = True)
                elif sub_field.field_type == SubTableFieldType.SELECT:
                    sub_field.option_layers = 'test'
                elif sub_field.field_type == SubTableFieldType.SYSTEM_DEFINED:
                    sub_field.option_layers = FieldUnit.ELECTRIC_FIELD
    dc = ttes.to_dict()
    try:
        ttes.validate(dc)
    except ValidationError:
        assert False
    ttes.save()

def test_condition(instance_with_collection):
    gm: GenericManager = instance_with_collection['instance'].generic_manager()
    ttes = gm.get_element(name = 'ttes')
    layer_src = ttes.properties.get_layer_by_label('My New Layer 2')
    layer_trg = ttes.properties.get_layer_by_key('my_new_layer')
    for f in layer_src.fields:
        if f.field_type == FieldType.SELECT:
            layer_trg.add_condition(f, 'Yes')
        if f.field_type == FieldType.CHECKBOX:
            layer_trg.add_condition(f, True)
        if f.field_type == FieldType.TEXT:
            layer_trg.add_condition(f, "True")

    ttes.save()

def test_segment_new_layer(instance_with_collection):
    gm: GenericManager = instance_with_collection['instance'].generic_manager()
    ttes = gm.get_segment(label = 'T TEST')
    ttes.properties.add_new_layer('My New Layer')
    dc = ttes.to_dict()
    try:
        ttes.validate(dc)
    except ValidationError:
        assert False
    ttes.save()
    ttes.save(SaveActionType.MAJOR)
    ttes.save(SaveActionType.MINOR)
    ttes = gm.get_segment(label = 'T TEST')
    assert '1.1' == ttes.version

def test_dataset_new_layer(instance_with_collection):
    gm: GenericManager = instance_with_collection['instance'].generic_manager()
    ttes = gm.get_dataset(ols_term_id = 'CHMO:0000593')
    ttes.properties.add_new_layer('My New Layer')
    dc = ttes.to_dict()
    try:
        ttes.validate(dc)
    except ValidationError:
        assert False
    ttes.save()
    ttes.save(SaveActionType.MAJOR)
    ttes.save(SaveActionType.MINOR)
    ttes = gm.get_dataset(ols_term_id = 'CHMO:0000593')
    assert '1.1' == ttes.version