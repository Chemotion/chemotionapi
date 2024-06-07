import re

import requests


class SchemaManager:

    iri_prefix = 'chmotion'
    def __init__(self, res: requests.Response):
        a = re.findall(r'Version: .*(\d+\.\d+.\d+)', res.text)
        if len(a) > 0:
            self.version = a[0]
        else:
            self.version = 'TEST'

    def generate_model_type(self, tpye_name: str, schema_version):
        if schema_version is not None:
            return f'{self.iri_prefix}:generic_type/{tpye_name.lower()}/{schema_version}'
        return f'{self.iri_prefix}:type/{tpye_name.lower()}/{self.version}'