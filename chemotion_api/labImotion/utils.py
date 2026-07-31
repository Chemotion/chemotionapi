"""Shared helpers and the serializable base class used across LabIMotion items."""

from abc import ABC, abstractmethod


def all_instances_of(lst: list, cls: type):
    """Return ``True`` if ``lst`` is a list whose every item is an instance of ``cls``.

    :param lst: The value to inspect; only lists can return ``True``.
    :param cls: The class every item must be an instance of.
    :return: ``True`` when ``lst`` is a list and all items are instances of ``cls``.
    """
    return isinstance(lst, list) and all(isinstance(item, cls) for item in lst)

class ChemotionSerializable(ABC):
    """Abstract base for objects that can serialise themselves to a Chemotion dict."""

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialise this object into its Chemotion JSON-compatible dictionary."""
        pass


def generate_pkg_info():
    """Return the LabIMotion package metadata expected by the Chemotion backend.

    :return: A dict with the ``pkg`` name and version of the generic-UI package.
    """
    return {
        'pkg': {
            "name": "chem-generic-ui",
            "version": "1.4.4"
        }
    }