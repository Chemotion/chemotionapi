from abc import ABC, abstractmethod
from typing import Type


def all_instances_of(lst: list, cls: Type):
    return isinstance(lst, list) and all(isinstance(item, cls) for item in lst)

class ChemotionSerializable(ABC):
    @abstractmethod
    def to_dict(self) -> dict:
        pass


def generate_pkg_info():
    return {
        'pkg': {
            "name": "chem-generic-ui",
            "version": "1.4.4"
        }
    }