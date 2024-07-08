import copy
import uuid


class Workflow:

    def __init__(self, props):
        self._props = props
        self.edges = props.get('flowObject', {}).get('edges')
        self.nodes = props.get('flowObject', {}).get('nodes')
        self._wf_tree = None
        self._node_registery = {}

    @property
    def workflows(self):
        return self._wfs

    @property
    def wf_tree(self):
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
        properties_layers[key] = new_layer
        return (key, new_layer)

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
            layer['source_layer'] = source_layer_id
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
        result = []
        for wf in self._wfs:
            layer = wf['layers'][-1]
            field = next(iter(x for x in layer['fields'] if x['type'] == 'wf-next'), None)
            if field is not None:
                options = copy.deepcopy(field['wf_options'])
                for option in options:
                    option['wf_id'] = wf['id']
                    option['layer_id'] = option['key']
                    del option['key']
                result.append({
                    'label': ' -> '.join([x['label'] for x in wf['layers']]),
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
        if wf_id is not None:
            wf = next(x for x in self._wfs if x['id'] == wf_id)
        else:
            wf = self._wfs[wf_idx]

        layer = wf['layers'][-1]
        field = next(iter(x for x in layer['fields'] if x['type'] == 'wf-next'), None)

        if layer_id is None and field is not None and len(field['wf_options']) > 0:
            layer_id = field['wf_options'][0]['key']

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
