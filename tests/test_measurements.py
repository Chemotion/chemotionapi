"""Measurements on a live ELN (M5.2)."""
import pytest

from chemotion_api.measurements import MeasurementError

pytestmark = pytest.mark.integration


def test_create_list_delete(instance_with_collection):
    col = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.save()
    plan = col.new_research_plan()
    plan.save()
    created = plan.create_measurements([
        {'sample': sample, 'description': 'yield', 'value': 87.5, 'unit': '%'},
        {'sample': sample.short_label, 'description': 'mp', 'value': 120, 'unit': '°C', 'metadata': {'row': 1}}])
    assert all(r['id'] for r in created)
    found = sorted(sample.measurements(), key=lambda m: m.description)
    assert [(m.description, m.value, m.unit, m.source_type, m.source_id) for m in found] == [
        ('mp', 120.0, '°C', 'research_plan', plan.id), ('yield', 87.5, '%', 'research_plan', plan.id)]
    assert found[0].metadata == {'row': 1}
    assert len(sample.measurements(source=plan)) == 2

    with pytest.raises(MeasurementError, match='Could not find sample') as err:
        plan.create_measurements([{'sample': 'NO-SUCH-LABEL-1', 'description': 'x', 'value': 1, 'unit': 'g'}])
    assert err.value.results[0]['errors']

    found[0].delete()
    assert [m.description for m in sample.measurements()] == ['yield']
