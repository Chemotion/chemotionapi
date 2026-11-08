"""Downloading LabIMotion templates and exporting generic elements on a live ELN (M6.2)."""
import json
import zipfile

import pytest

pytestmark = pytest.mark.integration


def test_download_template_and_export_element(instance_with_collection, tmp_path):
    instance = instance_with_collection['instance']
    klass = instance.generic_manager().get_element(name='wrk')
    data = json.loads(open(klass.download(str(tmp_path / 'wrk.json'))).read())
    assert (data['name'], data['label']) == ('wrk', klass.label) and data['properties_release']

    element = instance_with_collection['main_collection'].new_generic('wrk')
    element.save()
    assert zipfile.is_zipfile(element.export_docx(str(tmp_path / 'element.docx')))
