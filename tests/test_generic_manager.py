import json

import pytest
from jsonschema import ValidationError
from jsonschema.validators import validate

from chemotion_api.labImotion.items.validation import validate_generic_element, validate_generic_dataset, validate_generic_segment
from chemotion_api.labImotion.items.validation.schemas.schema_select_options import generic_schema

@pytest.mark.parametrize(
"json_file", ['GenericElement.json']
)
def test_validate_generic_element(json_file):
    with open(json_file, 'r') as file:
        json_value = json.loads(file.read())
    validate_generic_element(json_value)


@pytest.mark.parametrize(
"json_file", ["GenericDataset.json"]
)
def test_validate_generic_dataset(json_file):
    with open(json_file, 'r') as file:
        json_value = json.loads(file.read())
    validate_generic_dataset(json_value)


@pytest.mark.parametrize(
"json_file", ["GenericSegment.json"]
)
def test_validate_generic_segment(json_file):
    with open(json_file, 'r') as file:
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
    except ValidationError as e:
        assert True


def test_read_generic_elements(instance_with_collection):
    try:
        all_gs = instance_with_collection['instance'].generic_manager().load_all_elements()
    except ValidationError as e:
        assert False

    assert len(all_gs) == 8
    all_gs = [x for x in all_gs if x.is_generic]
    assert len(all_gs) == 2

    dict_element = all_gs[0].to_dict()
    pass

def test_read_generic_segments(instance_with_collection):
    try:
        all_gs = instance_with_collection['instance'].generic_manager().load_all_segments()
    except ValidationError as e:
        assert False
    assert len(all_gs) == 2
    pass

def test_read_generic_datasets(instance_with_collection):
    try:
        all_gs = instance_with_collection['instance'].generic_manager().load_all_datasets()
    except ValidationError as e:
        assert False

    assert len(all_gs) == 8
    pass