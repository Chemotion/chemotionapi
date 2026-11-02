"""Abstract workflow-interface mixin shared by generic elements."""
from abc import ABC, abstractmethod


class WorkflowInterface(ABC):
    """Abstract interface implemented by elements that carry a workflow (e.g. generic elements)."""

    @abstractmethod
    def wf_tree(self):
        """
        The element's workflow graph as a nested tree of layer labels.

        :return: The workflow tree
        """
        raise NotImplementedError()

    @abstractmethod
    def wf_next_options(self, flat=True) -> list:
        """
        List the possible next layers for each current workflow.

        :param flat: if True return a flat list of options, otherwise group them per workflow

        :return: The available next-step options
        """
        raise NotImplementedError()

    @abstractmethod
    def wf_next(self, layer_id: None | str = None, wf_idx: int = 0, wf_id: str | None = None, **kwargs):
        """
        Advance a workflow to its next layer.

        :param layer_id: node id of the next layer; defaults to the first available option
        :param wf_idx: index of the workflow to advance (used when ``wf_id`` is None)
        :param wf_id: id of the workflow to advance
        """
        raise NotImplementedError()

    @abstractmethod
    def wf_add_layer(self, layer_label: str, pos: int | None = None):
        """
        Add a workflow layer identified by its label.

        :param layer_label: label of the workflow layer to add
        :param pos: position for the new layer; if None it is placed after the existing layers
        """
        raise NotImplementedError()

    @abstractmethod
    def wf_current_workflow(self):
        """
        The layers of each workflow currently present on the element.

        :return: The current workflow(s)
        """
        raise NotImplementedError()
