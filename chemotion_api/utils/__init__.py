"""Shared utilities: the attribute-accessible :class:`PropertyDict`, :class:`TypedList`, unit/Quill helpers and dict merging."""
import copy
import os
import uuid
from collections.abc import MutableMapping
from collections import OrderedDict
from typing import Any, cast


class PropertyDict(MutableMapping):
    """A dict-like mapping that also supports attribute access and notifies a callback on changes.

    Keys may be read and written either via item access (``d['purity']``) or, when they are valid
    identifiers, via attribute access (``d.purity``). Whenever a value is set, the ``on_change``
    callback is invoked and the write is applied only if it returns a truthy value; if no callback
    is set the write is dropped.
    """

    def __init__(self, on_change, kwargs):
        self.data = kwargs
        self._on_change = on_change

    @property
    def on_change(self):
        """:return: The callback invoked before a value is written, or ``None`` if not set."""
        return self._on_change

    @on_change.setter
    def on_change(self, value):
        """Set the callback invoked before a value is written.

        :param value: The change callback, or ``None`` to disable change notification
        """
        self._on_change = value

    def __getitem__(self, name):
        ret_val = self.data.__getitem__(name)
        if isinstance(ret_val, dict):
            ret_val = PropertyDict(None, ret_val)
        if isinstance(ret_val, PropertyDict):
            def inner_on_change(inner_dict_obj, inner_name, inner_value):
                return self._on_change([self.to_dict(), *inner_dict_obj], [name, *inner_name], [ret_val.to_dict(), *inner_value])
            ret_val.on_change = inner_on_change
        return ret_val

    def __setitem__(self, name, value):
        if self._on_change is not None and self._on_change([self.data], [name], [value]):
            self.data.__setitem__(name, value)

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __delitem__(self, k):
        raise NotImplementedError

    def __contains__(self, k):
        return k in self.data

    def __dir__(self):
        # Expose dict keys so attribute access (sample.properties.purity) is discoverable
        # in the REPL and IDE autocompletion.
        base = list(super().__dir__())
        keys = [k for k in self.data.keys() if isinstance(k, str) and k.isidentifier()]
        return base + keys

    @property
    def __dict__(self):
        return self.to_dict()

    def to_dict(self):
        """:return: The underlying plain ``dict`` backing this mapping."""
        return self.data

    def _attr_error(self, name):
        import difflib
        keys = [k for k in self.data.keys() if isinstance(k, str)]
        hint = difflib.get_close_matches(name, keys, n=3)
        suffix = f" Did you mean: {', '.join(hint)}?" if hint else (
            f" Available keys: {', '.join(sorted(keys))}" if keys else "")
        return AttributeError(f"'PropertyDict' object has no property '{name}'.{suffix}")

    def __getattr__(self, name):
        if name.startswith('_') or name in ('data', 'on_change', 'to_dict'):
            raise AttributeError(f"'PropertyDict' object has no attribute '{name}'")
        try:
            return self[name]
        except KeyError:
            raise self._attr_error(name) from None

    def __setattr__(self, name, value):
        if name.startswith('_') or name in ('data', 'on_change'):
            super().__setattr__(name, value)
        elif hasattr(self.__class__, name) and isinstance(getattr(self.__class__, name), property):
            super().__setattr__(name, value)
        else:
            try:
                self[name] = value
            except KeyError:
                raise AttributeError(f"'PropertyDict' object has no attribute '{name}'") from None



def resource_path(file_path):
    """Get the absolute path to the resource, works for development and PyInstaller build."""
    return os.path.dirname(file_path)


def fixeddict_serializer(obj):
    """JSON serializer hook that unwraps :class:`PropertyDict` instances to plain dicts.

    Intended for use as the ``default`` argument of :func:`json.dumps`.

    :param obj: The object being serialized
    :return: The underlying dict for a :class:`PropertyDict`, otherwise ``obj`` unchanged
    """
    if isinstance(obj, PropertyDict):
        return obj.to_dict()  # Return the underlying dictionary
    return obj

class FixedDict(PropertyDict):
    """A :class:`PropertyDict` with a fixed set of keys: assigning an unknown key raises ``KeyError``."""

    def __init__(self, data):
        super().__init__(None, data)

    def __setitem__(self, k, v):
        if k not in self.data:
            raise KeyError(k)

        super().__setitem__(k,v)

    def __delitem__(self, k):
        raise NotImplementedError

    def __getitem__(self, k):
        return super().__getitem__(k)


class UnitDict(FixedDict):
    """A fixed mapping holding a physical quantity as a ``unit`` string and a numeric ``value``."""

    def __init__(self, unit: str, value: float | None):
        super().__init__({'unit': unit, 'value': value})

    def set_value_unit(self, value: float):
        """Set the numeric value.

        :param value: The new value
        """
        self.__setitem__('value', value)

    def set_value(self, value: float):
        """Set the numeric value.

        :param value: The new value
        """
        self.__setitem__('value', value)

    def set_unit(self, unit: str):
        """Set the unit.

        :param unit: The new unit string
        """
        self.__setitem__('unit', unit)


def add_to_dict(obj: dict, key: str, val: Any) -> str:
    """Store ``val`` under ``key`` in ``obj``, suffixing the key to avoid overwriting existing values.

    If ``key`` is already present with a non-``None`` value, an incrementing ``.N`` suffix is appended
    until a free key is found.

    :param obj: The dict to insert into (modified in place)
    :param key: The desired key
    :param val: The value to store
    :return: The key actually used (possibly suffixed)
    """
    origen_key = key
    idx = 1
    while key in obj and obj[key] is not None:
        key = f"{origen_key}.{idx}"
        idx += 1

    obj[key] = val
    return key


def parse_generic_field(field: dict) -> dict[str, Any]:
    """Parse a single generic-element field definition into its values and an id mapping.

    Handles nested ``input-group`` and ``table`` fields recursively as well as ``system-defined``
    (value/unit) and ``drag_element`` field types.

    :param field: The raw field definition from a generic element's JSON
    :return: A dict with ``values`` (the extracted value(s)) and ``obj_mapping`` (the mapping back
        to the field ids needed to write the values out again)
    """
    sub_fields = field.get('sub_fields')
    if type(sub_fields) is list and len(sub_fields) > 0:
        field_mapping = {'__field': field.get('field')}
        field_vals: list | None = None
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
    """Parse a generic-element layer (a group of fields) into its values and an id mapping.

    Fields are processed in their declared ``position`` order; ``wf-next`` workflow fields are skipped.

    :param key: The key of the layer
    :param layer: The raw layer definition from a generic element's JSON
    :return: A dict with ``values`` (a mapping of field label to value) and ``obj_mapping`` (the
        mapping back to the field ids)
    """
    temp_layer: dict = {}
    temp_id_layer: dict = {'__key': key}
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
    """Parse a complete generic object (segment/dataset) JSON into values and an id mapping.

    Layers are processed in their declared ``position`` order.

    :param segment_json_data: The raw generic-object JSON (containing ``properties.layers``)
    :return: A dict with ``values`` (the nested layer/field values) and ``obj_mapping`` (the mapping
        back to the segment id and field ids)
    """
    temp_segment: dict = {}
    temp_id_segment = {'__id': segment_json_data.get('id')}
    layers = OrderedDict(
        sorted(segment_json_data.get('properties', {}).get('layers', {}).items(), key=lambda x: x[1].get('position')))
    for key, layer in layers.items():
        parse_generic_object_layer_json(key, layer, temp_segment, temp_id_segment)
    return {'values': temp_segment, 'obj_mapping': temp_id_segment}


def parse_generic_object_layer_json(key, layer, values, obj_mapping):
    """Parse a single layer and merge its values and id mapping into the given accumulators.

    :param key: The key of the layer
    :param layer: The raw layer definition from a generic element's JSON
    :param values: The values accumulator dict (modified in place)
    :param obj_mapping: The id-mapping accumulator dict (modified in place)
    """
    temp_layer = parse_generic_layer(key, layer)
    layer_name = layer.get('label') if len(layer.get('label')) > 0 else layer.get('key')
    key = add_to_dict(values, layer_name, temp_layer.get('values'))
    obj_mapping[key] = temp_layer.get('obj_mapping')


def clean_generic_field(field_obj: dict, values: Any, field_mapping: dict | str | None = None) -> dict[str, Any]:
    """Write ``values`` back into a raw generic-element field definition.

    This is the inverse of :func:`parse_generic_field`: it handles nested ``input-group`` and
    ``table`` fields as well as ``system-defined`` and ``drag_element`` field types.

    :param field_obj: The raw field definition to update (modified in place)
    :param values: The value(s) to write into the field
    :param field_mapping: The mapping (from :func:`parse_generic_field`) used to map table column
        names back to field ids; ``None`` for simple fields
    :return: The updated ``field_obj``
    """
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
                    value_list[k][cast(dict, field_mapping)[k1]] = v1

    elif field_obj.get('type') == 'system-defined':
        field_obj['value'] = values['value']
        field_obj['value_system'] = values['unit']
    elif field_obj.get('type') == 'drag_element':
        field_obj['value'] = values['value']
    else:
        field_obj['value'] = values
    return field_obj


def clean_generic_object_json(segment_json_data: dict, values: dict, mapping: dict):
    """Write the nested ``values`` back into a complete generic-object JSON.

    This is the inverse of :func:`parse_generic_object_json`, using ``mapping`` to locate the raw
    field definitions to update.

    :param segment_json_data: The raw generic-object JSON to update (modified in place)
    :param values: The nested layer/field values to write
    :param mapping: The id mapping produced by :func:`parse_generic_object_json`
    """
    for (k, v) in values.items():
        layer_mapping = mapping.get(k, {})
        layer_key = layer_mapping.get('__key')
        for (value_name, value_ob) in v.items():
            field_mapping = layer_mapping.get(value_name)
            field_key: Any = ''
            if type(field_mapping) is str:
                field_key = field_mapping
            elif type(field_mapping) is dict:
                field_key = cast(dict, field_mapping).get('__field')
            fields = cast(dict, cast(dict, cast(dict, segment_json_data.get('properties')).get('layers')).get(layer_key)).get('fields')
            field_obj = next((x for x in cast(list, fields) if x.get('field') == field_key), None)
            clean_generic_field(cast(dict, field_obj), value_ob, field_mapping)


def merge_dicts(*args) -> dict:
    """Deep-merge several dicts into the first one.

    Nested dicts and lists are merged recursively; for any other type the later value overwrites the
    earlier one. The first argument is mutated in place and also returned.

    :param args: The dicts to merge, in order of increasing precedence
    :return: The merged dict (the first argument), or an empty dict if no arguments are given
    """
    dicts = list(args)
    if len(dicts) == 0:
        return {}
    res = dicts.pop(0)
    for d in dicts:
        _merge_dicts(res, d)
    return res


def _merge_dicts(a: dict | list, b: dict | list, path: list | None = None):
    if path is None:
        path = []

    iterator: Any
    if isinstance(b, dict):
        iterator = b.items()
    elif isinstance(b, list):
        iterator = enumerate(b)
    else:
        return

    def get_values(elem: list | dict, idx: str | int) -> Any:
        if isinstance(elem, dict):
            return elem.get(idx)
        elif isinstance(elem, list):
            try:
                return elem[cast(int, idx)]
            except (IndexError, ValueError, TypeError):
                pass
        return None

    def set_values(elem: list | dict, idx: str | int, value: Any):
        if isinstance(elem, dict):
            elem[idx] = value
            return
        elif isinstance(elem, list):
            try:
                elem[cast(int, idx)] = value
            except (IndexError, ValueError, TypeError):
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
    """Convert a ``snake_case`` string to ``CamelCase``.

    :param snake_str: The snake_case input string
    :return: The CamelCase representation
    """
    return "".join(x.capitalize() for x in snake_str.lower().split("_"))


class TypedList(list):
    """A ``list`` that enforces every element is an instance of a given type.

    Subclasses may override :meth:`_prepare_element` to transform elements on insertion and
    :meth:`after_append` to react once an element has been added.
    """

    def __init__(self, element_type, *args):
        self.element_type = element_type
        super().__init__(*args)
        self._check_elements()

    def _prepare_element(self, element):
        return element

    def after_append(self, element):
        """Hook called after an element has been appended or inserted; does nothing by default.

        :param element: The element that was added (after preparation)
        """
        pass

    def _check_elements(self):
        for element in self:
            self._check_element(element)

    def _check_element(self, element):
        if not isinstance(element, self.element_type):
            raise TypeError(f"All elements must be of type {self.element_type.__name__}")

    def append(self, element):
        """Type-check, prepare and append ``element`` to the list.

        :param element: The element to append
        :return: The prepared element that was appended
        :raises TypeError: If ``element`` is not an instance of the list's element type
        """
        self._check_element(element)
        prepared_element = self._prepare_element(element)
        super().append(prepared_element)
        self.after_append(prepared_element)
        return prepared_element

    def extend(self, iterable):
        """Append each element of ``iterable`` via :meth:`append`.

        :param iterable: The elements to append
        :raises TypeError: If any element is not an instance of the list's element type
        """
        for element in iterable:
            self.append(element)

    def insert(self, index, element):
        """Type-check, prepare and insert ``element`` at ``index``.

        :param index: The position at which to insert
        :param element: The element to insert
        :raises TypeError: If ``element`` is not an instance of the list's element type
        """
        self._check_element(element)
        prepared_element = self._prepare_element(element)
        super().insert(index, prepared_element)
        self.after_append(prepared_element)

    def __setitem__(self, index, element):
        if isinstance(index, slice):
            for _i in element:
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


def quill_hedging(input: str | dict, name: str) -> dict[str, list]:
    """Normalise a value into the Quill.js delta format expected for rich-text fields.

    A plain string is wrapped into a single-insert delta; an existing valid delta is returned as is.

    :param input: A plain string or an existing Quill delta (a dict with an ``ops`` list)
    :param name: The field name, used only in the error message
    :return: A Quill.js delta dict containing an ``ops`` list
    :raises ValueError: If ``input`` is neither a string nor a valid Quill delta
    """
    if isinstance(input, str):
        return {
            'ops': [
                {'insert': input}
            ]
        }
    if not isinstance(input, (dict, PropertyDict)) or 'ops' not in input or not isinstance(input['ops'], list):
        raise ValueError(f'{name} must be in the Quill.js format. (https://quilljs.com/docs/delta)')
    return input
