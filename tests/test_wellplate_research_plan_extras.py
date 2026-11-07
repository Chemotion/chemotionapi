"""Wellplate splitting, bulk creation and spreadsheets; research plan extras (M3.7)."""
import uuid
import zipfile

import pytest

pytestmark = pytest.mark.integration


def test_bulk_create_and_split_wellplates(instance_with_collection):
    col = instance_with_collection['main_collection']
    first, second = col.create_wellplates('Plate 1', 'Plate 2')
    assert [(p.properties['name'], p.width, p.height) for p in (first, second)] == [('Plate 1', 12, 8), ('Plate 2', 12, 8)]
    (sub,) = col.split_wellplates(first)
    assert sub.properties['name'] == 'Plate 1-Split' and sub.id not in (first.id, second.id)


def test_spreadsheet_template_round_trip(instance_with_collection, tmp_path):
    plate = instance_with_collection['main_collection'].new_wellplate()
    plate.save()
    template = plate.download_template(str(tmp_path / 'template.xlsx'))
    assert zipfile.is_zipfile(template)
    assert plate.import_spreadsheet(template) is plate
    assert any(a['filename'] == 'template.xlsx' for a in plate.attachments)


def test_research_plan_extras(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    plan = col.new_research_plan()
    plan.save()
    name = plan.upload_svg('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="4" height="4"/></svg>')
    assert name.endswith('.svg')

    schema = instance.save_research_plan_table_schema('api test schema', {'columns': [{'headerName': 'a', 'field': 'a'}], 'rows': []})
    assert schema['id'] in {s['id'] for s in instance.research_plan_table_schemas()}
    instance.delete_research_plan_table_schema(schema['id'])
    assert schema['id'] not in {s['id'] for s in instance.research_plan_table_schemas()}

    sample = col.new_sample_smiles('CCO')
    sample.save()
    assert sample.linked_research_plans() == []
    plan.body.append({'id': str(uuid.uuid4()), 'type': 'sample', 'value': sample})
    plan.save()
    assert {'id': plan.id, 'name': plan.name} in sample.linked_research_plans()
