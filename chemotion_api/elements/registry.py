"""Registry of the built-in (non-generic) element types.

Each built-in element class registers itself with :func:`register_element_type`, which records the
REST collection it lives under and the key the server wraps it in. That keeps everything a new
element type needs in its own module: the class, plus one decorator line.

LabIMotion generic elements are not registered: they all share ``/api/v1/generic_elements`` and are
dispatched on the klass's ``is_generic`` flag instead.

This module imports no element class, so :mod:`abstract_element` can use it without a cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import TypeVar

#: The REST collection of LabIMotion generic elements, and the fallback for unregistered names.
GENERIC_ELEMENTS_URL = '/api/v1/generic_elements'
#: The response key the server uses for an element that has no type of its own.
GENERIC_RESPONSE_KEY = 'element'


class UnknownElementType(TypeError):
    """Raised for a non-generic element type the client has no class for.

    Subclasses :class:`TypeError`, which is what the client raised here before, so existing
    ``except TypeError`` handlers keep working.
    """

    def __init__(self, name: str):
        self.name = name
        known = ', '.join(sorted(_REGISTRY)) or 'none'
        super().__init__(f'Element type "{name}" is a built-in Chemotion type this client does not model, '
                         f'so it cannot be loaded. Supported: {known}, and LabIMotion generic types.')


@dataclass(frozen=True)
class ElementTypeInfo:
    """What the client needs to know about one built-in element type."""
    #: The type's name as the server's element klass names it, e.g. ``research_plan``.
    name: str
    #: The element class that wraps its JSON.
    cls: type
    #: The REST collection, e.g. ``/api/v1/research_plans``.
    url: str
    #: The key the server wraps a single element in, e.g. ``research_plan``.
    response_key: str


_REGISTRY: dict[str, ElementTypeInfo] = {}

T = TypeVar('T', bound=type)


def register_element_type(name: str, url: str, response_key: str | None = None) -> Callable[[T], T]:
    """Class decorator registering a built-in element type.

    :param name: the element klass name, e.g. ``'sample'``
    :param url: the REST collection, e.g. ``'/api/v1/samples'``
    :param response_key: the key the server wraps one element in; defaults to ``name``
    """

    def decorator(cls: T) -> T:
        existing = _REGISTRY.get(name)
        if existing is not None and existing.cls is not cls:
            raise ValueError(f'Element type "{name}" is already registered to {existing.cls.__name__}')
        _REGISTRY[name] = ElementTypeInfo(name=name, cls=cls, url=url, response_key=response_key or name)
        return cls

    return decorator


def element_type_info(name: str) -> ElementTypeInfo | None:
    """The registration for ``name``, or ``None`` if it isn't a built-in type."""
    return _REGISTRY.get(name)


def element_class(name: str) -> type:
    """The class registered for ``name``.

    :raises UnknownElementType: if ``name`` isn't a registered built-in type
    """
    info = _REGISTRY.get(name)
    if info is None:
        raise UnknownElementType(name)
    return info.cls


def registered_element_types() -> list[str]:
    """Names of all registered built-in element types, sorted."""
    return sorted(_REGISTRY)
