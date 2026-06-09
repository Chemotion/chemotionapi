"""Singleton registry holding all JSON schemas and building validators for them."""

from typing import cast

from referencing import Registry, Resource
from jsonschema.validators import validator_for


class SchemaRegistry:
    """
    This calls manages all reader. It must be used as Singleton
    """
    _instance = None
    _schema_store: list = []
    _registry = None

    def __init__(self):
        """Block direct construction; use :meth:`instance` to obtain the singleton."""
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls):
        """
        Singleton constructor
        :return: Readers Singleton
        """
        if cls._instance is None:
            cls._instance = cls.__new__(cls)

        return cls._instance

    @property
    def registry(self):
        """List of ``($id, Resource)`` tuples for every registered schema."""
        return self._schema_store

    def validator_for(self, id: str):
        """Build a ``jsonschema`` validator for the schema registered under ``id``.

        :param id: The ``$id`` of the schema to validate against.
        :return: A validator instance bound to the registered schema store.
        """
        if self._registry is None:
            self._registry = Registry().with_resources(self._schema_store)
        schema = cast(Resource, self._registry.get(id)).contents
        return validator_for(schema)(schema, registry=self._registry)


    def register(self, schema: dict):
        """
        Register a schema in the schema store keyed by its ``$id``.

        :param schema: A JSON-Schema document containing a ``$id`` key.
        :return:
        """
        self._schema_store.append((schema["$id"], Resource.from_contents(schema)))
