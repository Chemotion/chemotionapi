"""Vessels on a live ELN (M4.2)."""
import uuid

import pytest

pytestmark = pytest.mark.integration


def test_vessel_lifecycle(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    template = instance.new_vessel_template(f'API flask {uuid.uuid4().hex[:6]}', vessel_type='round bottom flask',
                                            material_type='glass', volume_amount=250, volume_unit='ml').save()
    assert template.id in {t.id for t in instance.vessel_templates()}
    template.details = 'NS 29'
    template.save()
    assert instance.get_vessel_template(template.id).details == 'NS 29'

    vessel = col.new_vessel(template, weight_amount=120.5, weight_unit='g')
    assert vessel.template.id == template.id and vessel.short_label
    vessel.description = 'dried at 120 C'
    vessel.save()
    assert instance.get_vessel(vessel.id).description == 'dried at 120 C'

    rack = col.new_vessels(template, 3, base_name='rack')
    assert [v.name for v in rack] == ['rack 1', 'rack 2', 'rack 3']
    assert {v.id for v in col.get_vessels()} == {vessel.id, *(v.id for v in rack)}
    assert len(template.vessels(col)) == 4

    with pytest.raises(ValueError, match='still has vessels'):
        template.delete()
    for v in [vessel, *rack]:
        v.delete()
    assert col.get_vessels() == []
    template.delete()
    assert template.id not in {t.id for t in instance.vessel_templates()}
