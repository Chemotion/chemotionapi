"""Builds and caches the JSON-LD ``@type`` IRIs (model-type strings) used to tag elements."""
import re

import requests


class SchemaManager:
    """Builds the JSON-LD ``@type`` IRIs used to tag Chemotion elements.

    The Chemotion instance version is parsed from the ``/about`` response on construction and
    used as the trailing segment of non-generic model-type IRIs.
    """

    iri_prefix = 'chemotion'
    def __init__(self, res: requests.Response):
        a = re.findall(r'Version: .*(\d+\.\d+.\d+)', res.text)
        if len(a) > 0:
            self.version = a[0]
        else:
            self.version = 'TEST'

    def generate_model_type(self, tpye_name: str, schema_version):
        """Build the JSON-LD model-type IRI for an element class and schema version.

        :param tpye_name: name of the element class (case-insensitive; lower-cased in the IRI).
        :param schema_version: schema version of a generic class, or ``None`` for a built-in
            (non-generic) class, in which case the instance version is used instead.
        :return: the fully qualified ``chemotion:…`` model-type IRI.
        """
        if schema_version is not None:
            return f'{self.iri_prefix}:generic_type/{tpye_name.lower()}/{schema_version}'
        return f'{self.iri_prefix}:type/{tpye_name.lower()}/{self.version}'