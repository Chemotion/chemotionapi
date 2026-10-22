from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.workflow_interface import WorkflowInterface
from chemotion_api.elements.workflow_manager import Workflow
from chemotion_api.utils import parse_generic_object_json, clean_generic_object_json, parse_generic_object_layer_json


class GenericElement(AbstractElement, WorkflowInterface):
    """
    By default Chemotion ELN contains five elements: samples,
    reactions, wellplates, screens, and research plans. Optionally,
    generic elements can be added by the administration (LabIMotion).

    The properties of a generic element are its layers and fields:
    ``properties[layer][field] = value``. Layers can be added to the element
    using its workflow (:meth:`wf_next`) or directly (:meth:`wf_add_layer`).

    Usage::

    >>> from chemotion_api import Instance
    >>> from chemotion_api.collection import Collection
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> # Get the Element 'plan' with ID 1
    >>> elem = instance.get_generic_by_name('plan', 1)
    >>> # Set field 'Title' of layer 'General'
    >>> elem.properties['General']['Title'] = 'My plan'
    >>> elem.save()

    The server sets the :attr:`short_label` of a new element on its first save:
    ``<initials of the creator>-<klass_prefix of the template><counter>``, e.g. ``API-WRK10``, where the counter
    counts the elements of this type the user has created. A split of an element is labelled
    ``<short label of the parent>-<n>``.

    Layers without fields (e.g. a heading layer) appear in :attr:`properties` as empty dicts, see
    :meth:`layers_without_fields`. The generic segments available for the element type are listed by
    ``elem.segments.available()``.



    """

    def _set_json_data(self, json_data: dict):
        super()._set_json_data(json_data)

    @property
    def label(self) -> str | None:
        """
        The label of the element's generic type, e.g. 'Workflow'
        """
        return self.json_data.get('element_klass', {}).get('label')

    @property
    def klass_name(self) -> str | None:
        """
        The internal name of the element's generic type, e.g. 'wrk' (the same as :attr:`element_type`)
        """
        return self.json_data.get('element_klass', {}).get('name')

    @property
    def klass_version(self) -> str | None:
        """
        The version of the template the element was created with, e.g. '2.0'
        """
        return self.json_data.get('element_klass', {}).get('version')

    @property
    def klass_prefix(self) -> str | None:
        """
        The prefix of the template used in the short label, e.g. 'WRK'
        """
        return self.json_data.get('element_klass', {}).get('klass_prefix')

    def layers_without_fields(self) -> list[str]:
        """
        :return: the keys of the layers in :attr:`properties` that have no fields to fill in
        """
        return [key for key, fields in self.properties.items() if len(fields) == 0]

    def save_url(self) -> str:
        if not self.is_new:
            return "/api/v1/generic_elements/{}".format(self.id)
        return "/api/v1/generic_elements"

    @property
    def workflow(self) -> Workflow:
        """
        The workflow of the element's layers
        """
        self._load_if_partial()
        return self._workflow

    def _parse_properties(self) -> dict:
        self._workflow = Workflow(self.json_data['properties_release'])
        self._workflow.init_wf(self.json_data)
        data = parse_generic_object_json(self.json_data)
        self._properties_mapping = data['obj_mapping']
        return data['values']

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        clean_generic_object_json(self.json_data, self.properties, self._properties_mapping)
        return self.json_data

    def wf_tree(self) -> dict[str,list]:
        """
        :return: the workflow defined by the template as tree of layer labels
        """
        wf_tree = self.workflow.wf_tree

        def reg_wf_tree(wf_tree):
            return {wf_tree['layer']['label']: [reg_wf_tree(x) for x in wf_tree['next'].values()]}

        res = {}
        for node in wf_tree.values():
            res |= reg_wf_tree(node)
        return res

    def wf_current_workflow(self) -> list[list[str]]:
        """
        :return: the workflows of the element, each as list of the labels of its layers
        """
        current_wf = self.workflow.workflows
        wfs = []
        for wf in current_wf:
            wfs.append([x['label'] for x in wf['layers']])
        return wfs

    def wf_workflows(self) -> list[dict]:
        """
        The workflows of the element with the layers they consist of. The ``properties_key`` of a layer is its
        key in :attr:`properties`::

            [{'wf_id': '...', 'wf_idx': 0,
              'layers': [{'key': 'one', 'label': 'Nr 1', 'properties_key': 'Nr 1'},
                         {'key': 'three.1', 'label': 'Nr 3', 'properties_key': 'Nr 3.1'}]}, ...]

        :return: the workflows in the order of :meth:`wf_current_workflow`
        """
        workflows = self.workflow.workflows
        properties_keys = {mapping.get('__key'): name for name, mapping in self._properties_mapping.items()
                           if isinstance(mapping, dict)}
        return [{'wf_id': wf['id'], 'wf_idx': wf_idx,
                 'layers': [{'key': x['key'], 'label': x['label'], 'properties_key': properties_keys.get(x['key'])}
                            for x in wf['layers']]}
                for wf_idx, wf in enumerate(workflows)]

    def wf_layer(self, workflow: int | str, layer: str) -> dict:
        """
        A layer of a workflow, as an alternative to ``properties['Nr 3.1']``:

        >>> elem.wf_layer(1, 'Nr 3')['name_three'] = 'B'

        :param workflow: the index (``wf_idx``) or the id (``wf_id``) of the workflow
        :param layer: the label or the key of the layer. The template key matches its copies as well
        :return: the fields of the layer, the same object as in :attr:`properties`

        :raises ValueError: if the workflow or the layer does not exist or the layer is not unique
        """
        workflows = self.wf_workflows()
        wf = next((x for x in workflows if x['wf_id'] == workflow or x['wf_idx'] == workflow), None)
        if wf is None or isinstance(workflow, bool):
            raise ValueError(f'No workflow "{workflow}". Workflows: ' + ', '.join(
                f"{x['wf_idx']}: {' -> '.join(y['label'] for y in x['layers'])} ({x['wf_id']})" for x in workflows))
        matches = [x for x in wf['layers'] if layer in (x['label'], x['key'], x['key'].split('.')[0])]
        if len(matches) != 1:
            found = 'is not unique' if matches else 'does not exist'
            raise ValueError(f'Layer "{layer}" {found} in workflow {wf["wf_idx"]}. Layers: ' + ', '.join(
                f"{x['label']} ({x['key']})" for x in wf['layers']))
        return self.properties[matches[0]['properties_key']]

    def wf_next_options(self, flat: bool = True) -> list:
        """
        :param flat: if true, the options of all workflows are returned in one list
        :return: the layers which can be added as next step of the workflows. Each option contains the
            ``layer_id`` and ``wf_id`` to be passed to :meth:`wf_next`, ``wf_idx`` (the index of the workflow),
            ``layer_key`` and ``layer_label`` (the template layer) and ``source_key`` (the key of the
            workflow's last layer). Flat options also contain ``source_layer``, the labels of the workflow's
            layers joined by ``' -> '``
        """
        return self.workflow.next_options(flat)

    def wf_next(self, layer_id: None | str = None, wf_idx: int = 0, wf_id: str = None, **kwargs) -> str:
        """
        Adds the next layer of a workflow to the element (see :meth:`wf_next_options`).

        >>> option = next(x for x in elem.wf_next_options() if x['wf_idx'] == 1 and x['layer_label'] == 'Nr 4')
        >>> key = elem.wf_next(**option)
        >>> elem.properties[key]['name_four'] = 'Done'

        :param layer_id: id of the next layer. If None, the first option is used
        :param wf_idx: index of the workflow, used if wf_id is None
        :param wf_id: id of the workflow
        :return: the key of the new layer in :attr:`properties`

        :raises ValueError: if the workflow does not exist, the layer is not a next step of the workflow or no
            next step is found
        """
        key, layer = self.workflow.next(
            json_data=self.json_data,
            layer_id=layer_id,
            wf_idx=wf_idx,
            wf_id=wf_id,
            **kwargs
        )
        if layer is None:
            raise ValueError('No next step has been found. This could be that the workflow is completed or that the '
                             'arguments are not correct!')
        return parse_generic_object_layer_json(key, layer, self.properties, self._properties_mapping)

    def wf_add_layer(self, layer_label: str, pos: int | None = None) -> str:
        """
        Adds a layer of the template to the element, independent of the workflow.

        :param layer_label: label of the layer
        :param pos: position of the layer
        :return: the key of the new layer in :attr:`properties`

        :raises ValueError: if the layer is not found
        """
        key, layer = self.workflow.add_layer(
            json_data=self.json_data,
            layer_label=layer_label,
            pos=pos
        )

        if layer is None:
            raise ValueError(f'Layer {layer_label} has not been found.')

        return parse_generic_object_layer_json(key, layer, self.properties, self._properties_mapping)
