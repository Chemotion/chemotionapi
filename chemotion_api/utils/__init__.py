import copy
import os
import re
import sys
import uuid
from abc import ABC
from collections.abc import MutableMapping, MutableSequence
from collections import OrderedDict
from typing import Any, Optional

from chemotion_api.utils.segment_fields import SegmentField


class PropertyDict(MutableMapping):

    def __init__(self, on_change, kwargs):
        self.data = kwargs
        self._on_change = on_change

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, value):
        self._on_change = value

    def __getitem__(self, name):
        ret_val = self.data.__getitem__(name)
        # Dict subclasses with their own methods (e.g. Temperature) are returned as they are
        if type(ret_val) is dict:
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
    if isinstance(obj, PropertyDict):
        return obj.to_dict()  # Return the underlying dictionary
    return obj

class FixedDict(PropertyDict):

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
    def __init__(self, unit: str, value: float | None):
        super().__init__({'unit': unit, 'value': value})

    def set_value_unit(self, value: float):
        self.__setitem__('value', value)

    def set_value(self, value: float):
        self.__setitem__('value', value)

    def set_unit(self, unit: str):
        self.__setitem__('unit', unit)


class AttrAccessMixin:
    """
    Makes the keys of a dict readable and writable as attributes: ``obj.name`` is ``obj['name']``.
    Real attributes take precedence over keys.
    """

    def __getattr__(self, name: str) -> Any:
        if not name.startswith('_'):
            try:
                return self[name]
            except KeyError:
                pass
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any):
        if not name.startswith('_') and name in self and name not in self.__dict__ and \
                not hasattr(type(self), name):
            self[name] = value
        else:
            super().__setattr__(name, value)


def add_to_dict(obj: dict, key: str, val: any) -> str:
    origen_key = key
    idx = 1
    while key in obj and obj[key] is not None:
        key = f"{origen_key}.{idx}"
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
        sorted(segment_json_data.get('properties', {}).get('layers', {}).items(),
               key=lambda x: (x[1].get('position'), x[1].get('wf_position') or 0)))
    for key, layer in layers.items():
        parse_generic_object_layer_json(key, layer, temp_segment, temp_id_segment)
    return {'values': temp_segment, 'obj_mapping': temp_id_segment}


def parse_generic_object_layer_json(key, layer, values, obj_mapping) -> str:
    """
    Adds a layer to the values as ``values[name] = {field: value}`` and returns the name. The name is the layer
    label; a duplicated layer (key ``three.1``) gets the suffix of its key (``Nr 3.1``), so the name does not
    depend on the order the layers are read in.
    """
    temp_layer = parse_generic_layer(key, layer)
    layer_name = layer.get('label') if len(layer.get('label')) > 0 else layer.get('key')
    suffix = re.fullmatch(r'.+\.(\d+)', key or '')
    if suffix is not None and not layer_name.endswith(f".{suffix.group(1)}") and \
            f"{layer_name}.{suffix.group(1)}" not in values:
        layer_name = f"{layer_name}.{suffix.group(1)}"
    key = add_to_dict(values, layer_name, temp_layer.get('values'))
    obj_mapping[key] = temp_layer.get('obj_mapping')
    return key


def clean_generic_field(field_obj: dict, values: Any, field_mapping: dict | str | None = None,
                        select_options: dict | None = None) -> dict[str, Any]:
    sub_fields = field_obj.get('sub_fields')
    if field_obj.get('type') in ('select', 'system-defined', 'integer'):
        values = _check_generic_field_value(field_obj, values, select_options)
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
    properties: dict = segment_json_data['properties']
    for (k, v) in values.items():
        layer_mapping = mapping.get(k, {})
        layer_key = layer_mapping.get('__key')
        layer = properties.get('layers').get(layer_key)
        if layer is None:
            available = [name for name in mapping if not name.startswith('__')]
            raise ValueError(f'Unknown layer "{k}". Available: {", ".join(available)}')
        fields = layer.get('fields')
        for (value_name, value_ob) in v.items():
            field_mapping = layer_mapping.get(value_name)
            field_key = ''
            if type(field_mapping) is str:
                field_key = field_mapping
            elif type(field_mapping) is dict:
                field_key = field_mapping.get('__field')
            field_obj = next((x for x in fields if x.get('field') == field_key), None)
            if field_obj is None:
                available = [name for name in layer_mapping if not name.startswith('__')]
                raise ValueError(f'Unknown field "{value_name}" in layer "{k}". Fields are named as in the template '
                                 f'version the element uses. Available: {", ".join(available)}')
            clean_generic_field(field_obj, value_ob, field_mapping, properties.get('select_options'))


def _check_generic_field_value(field_obj: dict, values: Any, select_options: dict | None) -> Any:
    """
    Checks a changed value of a select, system-defined or integer field against the template and
    returns it in the stored format. Unchanged values are returned as they are, so data loaded from
    the server can always be saved again.
    """
    current: Any
    if field_obj.get('type') == 'system-defined':
        current = {'value': field_obj.get('value'), 'unit': field_obj.get('value_system')}
    else:
        current = field_obj.get('value')
    if values == current:
        return values
    field = SegmentField(field_obj, '', select_options)
    try:
        return field.clean_value(values)
    except ValueError as e:
        raise ValueError(f'Invalid value for field "{field.label}": {e}') from None


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

    def after_append(self, element):
        pass

    def _check_elements(self):
        for element in self:
            self._check_element(element)

    def _check_element(self, element):
        if not isinstance(element, self.element_type):
            raise TypeError(f"All elements must be of type {self.element_type.__name__}")

    def append(self, element):
        self._check_element(element)
        prepared_element = self._prepare_element(element)
        super().append(prepared_element)
        self.after_append(prepared_element)
        return prepared_element

    def extend(self, iterable):
        for element in iterable:
            self.append(element)

    def insert(self, index, element):
        self._check_element(element)
        prepared_element = self._prepare_element(element)
        super().insert(index, prepared_element)
        self.after_append(prepared_element)

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
    if not isinstance(input, (dict, PropertyDict)) or 'ops' not in input or not isinstance(input['ops'], list):
        raise ValueError(f'{name} must be in the Quill.js format. (https://quilljs.com/docs/delta)')
    return input


def quill_to_text(value) -> str:
    """Flatten a Chemotion rich-text value to plain text.

    Chemotion stores descriptions and observations as Quill deltas
    (``{"ops": [{"insert": "..."}]}``), not strings. Anything that only accepts ``str`` therefore
    silently drops exactly the fields whose narrative matters.

    :param value: a delta mapping, a plain string, or ``None``.
    :return: the text, or ``""`` when there is none.
    """
    from collections.abc import Iterable, Mapping

    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping) and "ops" in value:
        ops = value["ops"]
        if isinstance(ops, Iterable):
            return "".join(op.get("insert", "") for op in ops
                           if isinstance(op, Mapping)).strip()
    return ""


def normalise_range_value(value: str) -> str | None:
    """Turn Chemotion's Ruby range strings into something a reader can use.

    Melting and boiling points arrive as serialised Ruby ranges. The ELN sets both to an infinite
    range on create (``sample.rb``: ``before_create :set_boiling_melting_points``), which
    serialises as ``"(,)"`` — so *every* sample carries two of them, meaning "unset". A degenerate
    range (``"-114...-114"``) is just a single value written twice.

    :param value: the raw range string.
    :return: a usable value, or ``None`` when the range carries no information.
    """
    text = value.strip()
    if not text or text in ("(,)", "(...)", "..."):
        return None
    for separator in ("...", ".."):
        if separator in text:
            low, _, high = text.partition(separator)
            low, high = low.strip("( )"), high.strip("( )")
            if not low and not high:
                return None
            if low == high:
                return low or None
            return f"{low}-{high}" if low and high else (low or high)
    return text


def break_parent_cycles(parent_of: dict) -> set:
    """Find nodes whose parent chain loops, so a caller can treat them as roots instead.

    A collection tree is built by pointing each node at its parent. If those links form a cycle —
    A's parent is B and B's parent is A, or a node is its own parent — then *every* node has a
    parent, no node qualifies as a root, and a tree builder that collects roots ends up with an
    empty list. The observed consequence was an export that silently produced an archive
    containing nothing at all, and exited successfully.

    Returning the offenders rather than raising lets the caller keep the salvageable data: promote
    them to roots and say so, instead of discarding the whole dump over one bad link.

    :param parent_of: node key -> parent key (or ``None`` for a root).
    :return: the keys that sit on a cycle; empty when the links form a proper forest.
    """
    cyclic: set = set()
    settled: set = set()          # known to terminate at a root
    for start in parent_of:
        if start in settled or start in cyclic:
            continue
        chain: list = []
        seen: set = set()
        node = start
        while node is not None and node in parent_of and node not in seen:
            seen.add(node)
            chain.append(node)
            node = parent_of.get(node)
        if node is not None and node in seen:
            cyclic.update(chain)          # the walk re-entered itself
        else:
            settled.update(chain)
    return cyclic


def safe_join(base, name: str):
    """Join ``name`` under ``base``, refusing anything that would escape it.

    Filenames that arrive in data — a crate's ``File.name``, a server's ``Content-Disposition``,
    an attachment record — are not trustworthy paths. Two ways they escape:

    * an **absolute** name: ``Path('/safe/out') / '/etc/passwd'`` is ``/etc/passwd``; pathlib
      discards the base entirely;
    * a **relative** traversal: ``../../`` is not normalised away by ``/``, and code that calls
      ``mkdir(parents=True)`` first will helpfully build the path there.

    :param base: the directory the result must stay inside.
    :param name: the untrusted filename.
    :return: the resolved path, guaranteed to be inside ``base``.
    :raises ValueError: if ``name`` escapes ``base``.
    """
    import os
    from pathlib import Path

    root = Path(base).resolve()
    leaf = os.path.basename(str(name or "").strip()) or "unnamed"
    dest = (root / leaf).resolve()
    if not dest.is_relative_to(root):
        raise ValueError(f"refusing to write outside {root}: {name!r}")
    return dest
