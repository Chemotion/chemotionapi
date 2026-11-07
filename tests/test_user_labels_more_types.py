"""User labels on a live ELN (M1.6): labels on wellplates, research plans and screens."""
import uuid

import pytest

from chemotion_api.user import UserLabel

pytestmark = pytest.mark.integration


@pytest.fixture()
def label(logged_in_instance):
    return logged_in_instance.save_user_label(UserLabel(title=f'API_TEST_{uuid.uuid4().hex[:6]}',
                                                        color='#ff0000'))


def test_create_and_edit_a_label(logged_in_instance, label):
    assert label.id is not None and label.access_level == 0
    label.description = 'edited'
    assert logged_in_instance.save_user_label(label).description == 'edited'
    assert label.id in {lab.id for lab in logged_in_instance.get_user_labels()}


@pytest.mark.parametrize('make, load', [('new_wellplate', 'get_wellplate'),
                                        ('new_research_plan', 'get_research_plan'),
                                        ('new_screen', 'get_screen')])
def test_labels_set_through_properties_are_saved(instance_with_collection, label, make, load):
    instance = instance_with_collection['instance']
    element = getattr(instance_with_collection['main_collection'], make)()
    element.properties['user_labels'] = [label.id]
    element.save()
    assert getattr(instance, load)(element.id).properties['user_labels'] == [label.id]
