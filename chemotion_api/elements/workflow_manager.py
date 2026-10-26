"""Workflow model driving a generic element's layer/field progression."""
import copy
import uuid


class Workflow:
    """
    Models a generic element's workflow: the directed graph of layers (nodes) and their
    transitions (edges) defined in the element's released properties.

    It parses the flow graph into a tree, tracks the workflow instances currently present on an
    element, and offers operations to advance an element to its next layer or to add a layer.
    """

    def __init__(self, props):
        self._props = props
        self.edges = props.get('flowObject', {}).get('edges')
        self.nodes = props.get('flowObject', {}).get('nodes')
        self._wf_tree = None
        self._node_registery = {}

    @property
    def workflows(self):
        """
        The workflow instances currently present on the element (as built by :meth:`init_wf`).

        :return: List of workflow dicts, each with its ``layers``, ``pos`` and ``id``
        """
        return self._wfs

    @property
    def wf_tree(self):
        """
        The parsed workflow graph as a nested tree keyed by node id (parsed lazily and cached).

        :return: The workflow tree
        """
        if self._wf_tree is None:
            self._wf_tree = self._parse_wf()
        return self._wf_tree

    def _parse_wf_reg(self, current_node):
        start = current_node['data'] | {'id': current_node['id'], 'next': {}}
        self._node_registery[current_node['id']] = start
        for edge in self.edges:
            if edge['source'] == current_node['id'] and edge['target'] and len(edge['target']) > 1:
                for next_node in self.nodes:
                    if next_node['id'] == edge['target']:
                        start['next'][next_node['id']] = self._parse_wf_reg(next_node)
        return start

    def _parse_wf(self):
        if self.nodes is None:
            return {}
        current_node = next(x for x in self.nodes if x['id'] == '1')
        start = self._parse_wf_reg(current_node)
        return start['next']

    def _add_layer(self, properties_layers, new_layer):
        key = new_layer['key']
        i = 0
        while key in properties_layers:
            i = i + 1
            key = f"{new_layer['key']}.{i}"
        if key != new_layer['key']:
            # Like the ELN: the copy carries its own key and its conditions refer to it
            self._rename_cond_fields(new_layer, new_layer['key'], key)
            new_layer['key'] = key
        properties_layers[key] = new_layer
        return (key, new_layer)

    @staticmethod
    def _rename_cond_fields(layer, old_key, new_key):
        for field in layer.get('fields', []):
            conds = field.get('cond_fields')
            if not conds or all(not x.get('field') for x in conds):
                continue
            conds = [x | {'layer': new_key} for x in conds if x.get('layer') == old_key]
            if conds:
                field['cond_fields'] = conds
            else:
                del field['cond_fields']

    def _prepare_layer(self, tree_entry, wf_id=None, source_layer_id=None, wf_pos=1, pos=None):
        layer = copy.deepcopy(tree_entry['layer'])
        layer['wf_uuid'] = wf_id
        layer['ai'] = []
        layer['wf'] = wf_id is not None
        if wf_pos is not None:
            layer['wf_position'] = wf_pos
        if pos is not None:
            layer['position'] = pos
        if layer['wf']:
            layer['wf_info'] = {'node_id': tree_entry['id']}
            if source_layer_id is not None:
                layer['wf_info']['source_layer'] = source_layer_id
        if 'next' in tree_entry:
            max_pos = max(0, -1, *[x['position'] for x in layer['fields']])
            layer['fields'].append(
                {'type': 'wf-next', 'field': '_wf_next', 'label': 'Next', 'default': '', 'position': max_pos + 1,
                 'required': False, 'sub_fields': [], 'value': None, 'wf_options': [{'key': key,
                                                                                     'label': f"{val['layer']['label']}({val['lKey']})"}
                                                                                    for key, val in
                                                                                    tree_entry['next'].items()],
                 'text_sub_fields': []})
        return layer

    @staticmethod
    def _wf_next_value(layer):
        return next((x.get('value') for x in layer.get('fields', []) if x.get('type') == 'wf-next'), None)

    def _repair_legacy_layers(self, prop_layers):
        """
        Earlier versions of this API stored the source layer outside of ``wf_info`` and kept the template key in
        duplicated layers (``three`` in slot ``three.1``). The ELN cannot follow such chains, so they are converted
        to the ELN format; the next save writes them back.
        """
        for key, layer in prop_layers.items():
            if 'wf_info' in layer and layer.get('key') != key:
                layer['key'] = key
        for key, layer in prop_layers.items():
            if 'source_layer' not in layer:
                continue
            source = layer.pop('source_layer')
            wf_info = layer.get('wf_info')
            if wf_info is None or 'source_layer' in wf_info:
                continue
            # The source is the closest previous step of the same workflow (same position) which points to this layer
            candidates = sorted((x.get('wf_position', 0), k) for k, x in prop_layers.items() if
                                x.get('position') == layer.get('position') and
                                x.get('wf_position', 0) < layer.get('wf_position', 0) and
                                self._wf_next_value(x) == wf_info.get('node_id'))
            wf_info['source_layer'] = candidates[-1][1] if candidates else source

    def _read_wf(self, wf_tree_id, prev_id, prop_layers):
        if wf_tree_id is not None:
            key_layer_iter = iter((key, x) for key, x in prop_layers.items() if
                                  x.get('wf_info', {}).get('node_id') == wf_tree_id and x.get('wf_info', {}).get(
                                      'source_layer') == prev_id)
            key, layer = next(key_layer_iter, (None, None))
        else:
            key = layer = None
        results = []
        if layer is not None:
            results.append(layer)
            try:
                next_wf_id = next(x['value'] for x in layer['fields'] if x['type'] == 'wf-next')
                current_node = next(x for x in self.nodes if x['id'] == next_wf_id)
                results += self._read_wf(current_node['id'], key, prop_layers)
            except:
                pass
        return results

    def init_wf(self, json_data):
        """
        Build the workflow instances for an element from its property layers.

        Legacy layers are repaired first, then for each root entry in the workflow tree the
        existing matching layers are collected; if none exist yet a fresh starting layer is created
        and appended to the element's properties. The resulting instances are stored in
        :attr:`workflows`.

        :param json_data: the element's JSON data (its ``properties.layers`` are read and extended)
        """
        self._repair_legacy_layers(json_data['properties']['layers'])
        max_pos = max(-1, 0, *[elm['position'] for k, elm in json_data['properties']['layers'].items()])
        self._wfs = []
        for (id, entry) in self.wf_tree.items():
            layers = self._read_wf(id, None, json_data['properties']['layers'])
            if len(layers) == 0:
                _key, layers = self._add_layer(json_data['properties']['layers'],
                                         self._prepare_layer(entry, uuid.uuid4().__str__()))
                max_pos += 10
                layers['position'] = max_pos
                self._wfs.append({
                    'layers': [layers],
                    'pos': layers['position'],
                    'id': layers['wf_uuid']
                })
            else:
                self._wfs.append({
                    'layers': layers,
                    'pos': layers[0]['position'],
                    'id': layers[0]['wf_uuid']
                })

    def next_options(self, flat = True):
        """
        List the possible next layers for each current workflow instance.

        :param flat: if True (default) return a flat list of option dicts; if False return a list
            grouped per workflow, each with a ``label`` and its ``options``

        :return: The available next-step options
        """
        result = []
        for wf_idx, wf in enumerate(self._wfs):
            layer = wf['layers'][-1]
            field = next(iter(x for x in layer['fields'] if x['type'] == 'wf-next'), None)
            if field is not None:
                options = copy.deepcopy(field['wf_options'])
                for option in options:
                    option['wf_id'] = wf['id']
                    option['wf_idx'] = wf_idx
                    option['layer_id'] = option['key']
                    template_layer = self._node_registery.get(option['key'], {}).get('layer', {})
                    option['layer_key'] = template_layer.get('key')
                    option['layer_label'] = template_layer.get('label')
                    option['source_key'] = layer['key']
                    del option['key']
                result.append({
                    'label': ' -> '.join([x['label'] for x in wf['layers']]),
                    'wf_idx': wf_idx,
                    'options': options
                })
        if flat:
            flat_res = []
            for x in result:
                for o in x['options']:
                    o['source_layer'] = x['label']
                    flat_res.append(o)
            return flat_res
        return result

    def add_layer(self, json_data, layer_label, pos):
        """
        Add a workflow layer identified by its label to the element's properties.

        :param json_data: the element's JSON data (its ``properties.layers`` are extended)
        :param layer_label: label of the released workflow layer to add
        :param pos: position for the new layer; if None it is placed after the existing layers

        :return: a ``(key, layer)`` tuple for the added layer, or ``(None, None)`` if no released
            workflow layer with that label exists
        """
        if pos is None:
            pos = max(1,0,*[x['position'] for x in json_data['properties']['layers'].values()]) + 10
        layer = next(iter(x for x in json_data['properties_release']['layers'].values() if x['wf'] and x['label'] == layer_label), None)
        if layer is None:
            return None, None
        return self._add_layer(json_data['properties']['layers'],
                                     self._prepare_layer({'layer': layer},
                                                         wf_id=None,
                                                         pos=pos))

    def next(self, json_data, layer_id=None, wf_idx=0, wf_id=None, **kwargs) -> tuple[int,dict] | tuple[None,None]:
        """
        Advance a workflow instance to its next layer and append that layer to the element.

        The workflow instance is selected by ``wf_id`` if given, otherwise by ``wf_idx``. If
        ``layer_id`` is not given the first available next option of the current layer is used.

        :param json_data: the element's JSON data (its ``properties.layers`` are extended)
        :param layer_id: node id of the next layer to add; defaults to the first available option
        :param wf_idx: index of the workflow instance to advance (used when ``wf_id`` is None)
        :param wf_id: id of the workflow instance to advance

        :return: a ``(key, layer)`` tuple for the added layer, or ``(None, None)`` if there is no
            next layer
        """
        if wf_id is not None:
            wf = next((x for x in self._wfs if x['id'] == wf_id), None)
            if wf is None:
                raise ValueError(f'No workflow with id "{wf_id}". Workflows: {self._describe_wfs()}')
        elif -len(self._wfs) <= wf_idx < len(self._wfs):
            wf = self._wfs[wf_idx]
        else:
            raise ValueError(f'No workflow with index {wf_idx}. Workflows: {self._describe_wfs()}')

        layer = wf['layers'][-1]
        field = next(iter(x for x in layer['fields'] if x['type'] == 'wf-next'), None)
        options = field['wf_options'] if field is not None else []

        if layer_id is None and len(options) > 0:
            layer_id = options[0]['key']
        elif layer_id is not None and layer_id not in [x['key'] for x in options]:
            labels = ', '.join(f'"{x["label"]}" ({x["key"]})' for x in options) or 'none'
            raise ValueError(f'Layer id "{layer_id}" is not a next step of workflow '
                             f'"{" -> ".join(x["label"] for x in wf["layers"])}". Options: {labels}')

        entry = self._node_registery.get(layer_id, None)
        if entry is not None:
            key, layer = self._add_layer(json_data['properties']['layers'],
                                    self._prepare_layer(entry,
                                                        wf_id='',
                                                        source_layer_id=layer['key'],
                                                        wf_pos=layer['wf_position'] + 1,
                                                        pos=layer['position']))

            if field is not None:
                field['value'] = layer_id
            wf['layers'].append(layer)
            return key, layer

        return None, None

    def _describe_wfs(self):
        return ', '.join(f'{idx}: {" -> ".join(x["label"] for x in wf["layers"])} ({wf["id"]})'
                         for idx, wf in enumerate(self._wfs))
