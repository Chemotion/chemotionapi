import os

import chemotion_api.labImotion.items.validation.schemas.imports
from chemotion_api.labImotion.items.validation.registry import SchemaRegistry
from chemotion_api.labImotion.items.validation.schemas import ALL_SCHEMAS
from chemotion_api.utils import resource_path


if __name__ == '__main__':
    A = []
    for module in os.listdir(os.path.join(resource_path(__file__), 'schemas')):
        if module.startswith('schema_') and module[-3:] == '.py':
            A.append(f'import chemotion_api.labImotion.items.validation.schemas.{module[:-3]}')

    with open(os.path.join(resource_path(__file__), 'schemas/imports.py'), 'w') as f:
        f.write('\n'.join(A))
    exit()


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
