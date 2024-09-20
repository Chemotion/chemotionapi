from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.workflow_interface import WorkflowInterface
from chemotion_api.elements.workflow_manager import Workflow
from chemotion_api.utils import parse_generic_object_json, clean_generic_object_json, parse_generic_object_layer_json


class GenericElement(AbstractElement, WorkflowInterface):
    """
    By default Chemotion ELN contains five elements: samples,
    reactions, wellplates, screens, and research plans. Optionally,
    generic elements can be added by the administration.

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
    >>> elem.save()



    """

    def _set_json_data(self, json_data: dict):
        super()._set_json_data(json_data)

    def save_url(self) -> str:
        if self.id is not None:
            return "/api/v1/generic_elements/{}".format(self.id)
        return "/api/v1/generic_elements"

    def _parse_properties(self) -> dict:
        self.workflow = Workflow(self.json_data['properties_release'])
        self.workflow.init_wf(self.json_data)
        data = parse_generic_object_json(self.json_data)
        self._properties_mapping = data['obj_mapping']
        return data['values']

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        clean_generic_object_json(self.json_data, self.properties, self._properties_mapping)
        return self.json_data

    def wf_tree(self) -> dict[str,list]:
        wf_tree = self.workflow.wf_tree

        def reg_wf_tree(wf_tree):
            return {wf_tree['layer']['label']: [reg_wf_tree(x) for x in wf_tree['next'].values()]}

        res = {}
        for node in wf_tree.values():
            res |= reg_wf_tree(node)
        return res

    def wf_current_workflow(self) -> list[list[str]]:
        current_wf = self.workflow.workflows
        wfs = []
        for wf in current_wf:
            wfs.append([x['label'] for x in wf['layers']])
        return wfs

    def wf_next_options(self, flat: bool = True) -> list:
        return self.workflow.next_options(flat)

    def wf_next(self, layer_id: None | str = None, wf_idx: int = 0, wf_id: str = None, **kwargs):
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
        parse_generic_object_layer_json(key, layer, self.properties, self._properties_mapping)

    def wf_add_layer(self, layer_label: str, pos: int | None = None):
        key, layer = self.workflow.add_layer(
            json_data=self.json_data,
            layer_label=layer_label,
            pos=pos
        )

        if layer is None:
            raise ValueError(f'Layer {layer_label} has been found.')

        parse_generic_object_layer_json(key, layer, self.properties, self._properties_mapping)
