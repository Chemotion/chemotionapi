import copy
import uuid
from collections import OrderedDict


def add_to_dict(obj: dict, key: str, val: any) -> str:
    origen_key = key
    idx = 1
    while key in obj and obj[key] is not None:
        key = "{}.{}".format(origen_key, idx)
        idx += 1

    obj[key] = val
    return key


def parse_generic_field(field: dict) -> dict[str, any]:
    sub_fields = field.get('sub_fields')
    if type(sub_fields) is list and len(sub_fields) > 0:
        field_mapping = {'__field': field.get('field')}
        field_vals = None
        if field.get('type') == 'input-group':
            field_vals = []
            for sub_field in sub_fields:
                temp_sub_field = parse_generic_field(sub_field)
                field_vals.append(temp_sub_field.get('values'))

        elif field.get('type') == 'table':
            value_list = field.get('sub_values', [])
            field_vals = [{} for x in value_list]
            for sub_field in sub_fields:
                add_to_dict(field_mapping, sub_field.get('col_name'), sub_field.get('id'))
                for (idx, value) in enumerate(value_list):
                    add_to_dict(field_vals[idx], sub_field.get('col_name'), value[sub_field.get('id')])

        return {'values': field_vals, 'obj_mapping': field_mapping}
    elif field.get('type') == 'system-defined':
        return {'values': {'value': field.get('value'), 'unit': field.get('value_system')},
                'obj_mapping': field.get('id', field.get('field'))}
    elif field.get('type') == 'drag_element':
        return {'values': {'value': field.get('value')}, 'obj_mapping': field.get('id', field.get('field'))}
    return {'values': field.get('value'), 'obj_mapping': field.get('id', field.get('field'))}


def parse_generic_layer(key: str, layer: dict) -> dict[str, dict]:
    temp_layer = {}
    temp_id_layer = {'__key': key}
    fields = layer.get('fields', [])
    fields.sort(key=lambda x: x.get('position'))
    for field in fields:
        if field.get('type') != 'wf-next':
            temp_field = parse_generic_field(field)
            field_name = field.get('label') if len(field.get('label')) > 0 else field.get('field')
            key = add_to_dict(temp_layer, field_name, temp_field.get('values'))
            temp_id_layer[key] = temp_field.get('obj_mapping')

    return {'values': temp_layer, 'obj_mapping': temp_id_layer}


def parse_generic_object_json(segment_json_data: dict) -> dict:
    temp_segment = {}
    temp_id_segment = {'__id': segment_json_data.get('id')}
    layers = OrderedDict(
        sorted(segment_json_data.get('properties', {}).get('layers', {}).items(), key=lambda x: x[1].get('position')))
    for key, layer in layers.items():
        parse_generic_object_layer_json(key, layer, temp_segment, temp_id_segment)
    return {'values': temp_segment, 'obj_mapping': temp_id_segment}


def parse_generic_object_layer_json(key, layer, values, obj_mapping):
    temp_layer = parse_generic_layer(key, layer)
    layer_name = layer.get('label') if len(layer.get('label')) > 0 else layer.get('key')
    key = add_to_dict(values, layer_name, temp_layer.get('values'))
    obj_mapping[key] = temp_layer.get('obj_mapping')


def clean_generic_field(field_obj: dict, values: any, field_mapping: dict | str = None) -> dict[str, any]:
    sub_fields = field_obj.get('sub_fields')
    if type(sub_fields) is list and len(sub_fields) > 0:
        if field_obj.get('type') == 'input-group':
            for (idx, val) in enumerate(values):
                clean_generic_field(sub_fields[idx], val)

        elif field_obj.get('type') == 'table':
            field_obj['sub_values'] = value_list = field_obj.get('sub_values', [])
            while len(value_list) < len(values):
                value_list.append({'id': uuid.uuid4().__str__()})
            for (k, v) in enumerate(values):
                for (k1, v1) in v.items():
                    value_list[k][field_mapping[k1]] = v1

    elif field_obj.get('type') == 'system-defined':
        field_obj['value'] = values['value']
        field_obj['value_system'] = values['unit']
    elif field_obj.get('type') == 'drag_element':
        field_obj['value'] = values['value']
    else:
        field_obj['value'] = values
    return field_obj


def clean_generic_object_json(segment_json_data: dict, values: dict, mapping: dict):
    for (k, v) in values.items():
        layer_mapping = mapping.get(k, {})
        layer_key = layer_mapping.get('__key')
        for (value_name, value_ob) in v.items():
            field_mapping = layer_mapping.get(value_name)
            field_key = ''
            if type(field_mapping) is str:
                field_key = field_mapping
            elif type(field_mapping) is dict:
                field_key = field_mapping.get('__field')
            fields = segment_json_data.get('properties').get('layers').get(layer_key).get('fields')
            field_obj = next((x for x in fields if x.get('field') == field_key), None)
            clean_generic_field(field_obj, value_ob, field_mapping)


def merge_dicts(*args) -> dict:
    dicts = list(args)
    if len(dicts) == 0:
        return {}
    res = dicts.pop(0)
    for d in dicts:
        _merge_dicts(res, d)
    return res


def _merge_dicts(a: dict | list, b: dict | list, path: list = None):
    if path is None:
        path = []

    if isinstance(b, dict):
        iterator = b.items()
    elif isinstance(b, list):
        iterator = enumerate(b)
    else:
        return

    def get_values(elem: list | dict, idx: str | int) -> any:
        if isinstance(elem, dict):
            return elem.get(idx)
        elif isinstance(elem, list):
            try:
                return elem[idx]
            except:
                pass
        return None

    def set_values(elem: list | dict, idx: str | int, value: any):
        if isinstance(elem, dict):
            elem[idx] = value
            return
        elif isinstance(elem, list):
            try:
                elem[idx] = value
            except:
                elem.append(value)

    for key, b_val in iterator:
        a_val = get_values(a, key)
        if isinstance(a_val, dict) and isinstance(b_val, dict):
            _merge_dicts(a_val, b_val, path + [str(key)])
        elif isinstance(a_val, list) and isinstance(b_val, list):
            _merge_dicts(a_val, b_val, path + [str(key)])
        else:
            set_values(a, key, b_val)
    return a


def snake_to_camel_case(snake_str):
    return "".join(x.capitalize() for x in snake_str.lower().split("_"))


class TypedList(list):
    def __init__(self, element_type, *args):
        self.element_type = element_type
        super().__init__(*args)
        self._check_elements()

    def _prepare_element(self, element):
        return element

    def _check_elements(self):
        for element in self:
            self._check_element(element)

    def _check_element(self, element):
        if not isinstance(element, self.element_type):
            raise TypeError(f"All elements must be of type {self.element_type.__name__}")

    def append(self, element):
        self._check_element(element)
        super().append(self._prepare_element(element))

    def extend(self, iterable):
        for element in iterable:
            self.append(element)

    def insert(self, index, element):
        self._check_element(element)
        super().insert(index, self._prepare_element(element))

    def __setitem__(self, index, element):
        if isinstance(index, slice):
            for i in element:
                self._check_element(element)
        else:
            self._check_element(element)
        super().__setitem__(index, self._prepare_element(element))

    def __add__(self, other):
        x = copy.copy(self)
        x.extend(other)
        return x

    def __iadd__(self, other):
        self.extend(other)
        return self


def quill_hedging(input: str | dict, name: str) -> dict[str:list]:
    if isinstance(input, str):
        return {
            'ops': [
                {'insert': input}
            ]
        }
    if not isinstance(input, dict) or 'ops' not in input or not isinstance(input['ops'], list):
        raise ValueError(f'{name} must be in the Quill.js format. (https://quilljs.com/docs/delta)')
    return input
