from abc import ABC, abstractmethod


class WorkflowInterface(ABC):
    @abstractmethod
    def wf_tree(self):
        raise NotImplementedError()

    @abstractmethod
    def wf_next_options(self, flat=True) -> list:
        raise NotImplementedError()

    @abstractmethod
    def wf_next(self, layer_id: None | str = None, wf_idx: int = 0, wf_id: str = None, **kwargs):
        raise NotImplementedError()

    @abstractmethod
    def wf_add_layer(self, layer_label: str, pos: int | None = None):
        raise NotImplementedError()

    @abstractmethod
    def wf_current_workflow(self):
        raise NotImplementedError()
