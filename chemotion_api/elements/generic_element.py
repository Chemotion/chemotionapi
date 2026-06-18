"""GenericElement: a LabIMotion user-defined element type backed by a dynamic schema."""
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.workflow_interface import WorkflowInterface
from chemotion_api.elements.workflow_manager import Workflow
from chemotion_api.utils import parse_generic_object_json, clean_generic_object_json, parse_generic_object_layer_json
from typing import cast


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
        """
        The API endpoint used to save this generic element (create or update).

        :return: The save URL
        """
        if not self.is_new:
            return f"/api/v1/generic_elements/{self.id}"
        return "/api/v1/generic_elements"

    def _parse_properties(self) -> dict:
        self.workflow = Workflow(cast(dict, self.json_data)['properties_release'])
        self.workflow.init_wf(self.json_data)
        data = parse_generic_object_json(cast(dict, self.json_data))
        self._properties_mapping = data['obj_mapping']
        return data['values']

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        clean_generic_object_json(cast(dict, self.json_data), cast(dict, self.properties), self._properties_mapping)
        return cast(dict, self.json_data)

    def eln_node_content(self) -> dict:
        """Emit this generic element's segment fields as schema.org ``PropertyValue`` entries."""
        property_values: list[dict] = []
        try:
            props = self.properties
            items = (props.to_dict() if hasattr(props, "to_dict") else dict(props)).items()
        except Exception:
            items = []  # type: ignore[assignment]
        for key, val in items:
            if val is None or val == "" or val == []:
                continue
            pv: dict = {"@type": "PropertyValue", "name": str(key)}
            if isinstance(val, dict) and "value" in val and "unit" in val:
                pv["value"] = val.get("value")
                if val.get("unit"):
                    pv["unitText"] = str(val.get("unit"))
            elif isinstance(val, (str, int, float, bool)):
                pv["value"] = val
            else:
                pv["value"] = str(val)
            property_values.append(pv)
        return {"variableMeasured": property_values} if property_values else {}

    def wf_tree(self) -> dict[str,list]:
        """
        The element's workflow graph as a nested tree of layer labels.

        :return: The workflow tree keyed by layer label
        """
        wf_tree = self.workflow.wf_tree

        def reg_wf_tree(wf_tree):
            return {wf_tree['layer']['label']: [reg_wf_tree(x) for x in wf_tree['next'].values()]}

        res: dict = {}
        for node in wf_tree.values():
            res |= reg_wf_tree(node)
        return res

    def wf_current_workflow(self) -> list[list[str]]:
        """
        The layer labels of each workflow currently present on the element.

        :return: A list of workflows, each as a list of its layer labels
        """
        current_wf = self.workflow.workflows
        wfs = []
        for wf in current_wf:
            wfs.append([x['label'] for x in wf['layers']])
        return wfs

    def wf_next_options(self, flat: bool = True) -> list:
        """
        List the possible next layers for each current workflow.

        :param flat: if True (default) return a flat list of options, otherwise group them per workflow

        :return: The available next-step options
        """
        return self.workflow.next_options(flat)

    def wf_next(self, layer_id: None | str = None, wf_idx: int = 0, wf_id: str | None = None, **kwargs):
        """
        Advance a workflow to its next layer and parse the new layer into this element's properties.

        :param layer_id: node id of the next layer; defaults to the first available option
        :param wf_idx: index of the workflow to advance (used when ``wf_id`` is None)
        :param wf_id: id of the workflow to advance

        :raises ValueError: if no next step is found (workflow completed or arguments incorrect)
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
        parse_generic_object_layer_json(key, layer, self.properties, self._properties_mapping)

    def wf_add_layer(self, layer_label: str, pos: int | None = None):
        """
        Add a workflow layer by its label and parse it into this element's properties.

        :param layer_label: label of the workflow layer to add
        :param pos: position for the new layer; if None it is placed after the existing layers

        :raises ValueError: if no workflow layer with the given label exists
        """
        key, layer = self.workflow.add_layer(
            json_data=self.json_data,
            layer_label=layer_label,
            pos=pos
        )

        if layer is None:
            raise ValueError(f'Layer {layer_label} has been found.')

        parse_generic_object_layer_json(key, layer, self.properties, self._properties_mapping)
