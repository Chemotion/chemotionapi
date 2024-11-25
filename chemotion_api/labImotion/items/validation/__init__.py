import importlib
import os

from jsonschema import ValidationError

from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

for module in os.listdir(os.path.join(os.path.dirname(__file__), 'schemas')):
    if module.startswith('schema_') and module[-3:] == '.py':
        importlib.import_module(f'chemotion_api.labImotion.items.validation.schemas.{module[:-3]}')

def validate_selection_options(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/select_option/draft-01')
    validator.validate(json_to_test)

def validate_generic_element(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/element/draft-01')
    validator.validate(json_to_test)

def validate_generic_dataset(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/dataset/draft-01')
    validator.validate(json_to_test)

def validate_generic_segment(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/segment/draft-01')
    validator.validate(json_to_test)

def validate_generic_properties(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/properties/draft-01')
    validator.validate(json_to_test)

def validate_generic_dataset_properties(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/dataset_properties/draft-01')
    validator.validate(json_to_test)


def validate_generic_segment_properties(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/segment_properties/draft-01')
    validator.validate(json_to_test)

def validate_generic_layer(json_to_test: dict):
    validator = SchemaRegistry.instance().validator_for('chmotion://generic/layer/draft-01')
    validator.validate(json_to_test)