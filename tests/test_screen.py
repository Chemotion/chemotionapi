"""Screens on a live ELN (M1.1): create, link wellplates and research plans, list, move, delete."""
import pytest

from chemotion_api.connection import ChemotionRequestError

pytestmark = pytest.mark.integration


@pytest.fixture()
def screen_setup(instance_with_collection):
    col = instance_with_collection['main_collection']
    plate = col.new_wellplate()
    plate.save()
    screen = col.new_screen()
    screen.properties['name'] = 'Kinase panel'
    screen.properties['conditions'] = '37 °C'
    screen.add_wellplate(plate)
    screen.save()
    return instance_with_collection['instance'], col, screen, plate


def test_create_and_reload(screen_setup):
    instance, _, screen, plate = screen_setup
    loaded = instance.get_screen(screen.id)
    assert loaded.properties['name'] == 'Kinase panel'
    assert loaded.properties['conditions'] == '37 °C'
    assert [w.id for w in loaded.wellplates] == [plate.id]


def test_update_text_and_unlink_a_wellplate(screen_setup):
    instance, _, screen, plate = screen_setup
    loaded = instance.get_screen(screen.id)
    loaded.properties['result'] = 'no hits'
    loaded.remove_wellplate(plate)
    loaded.save()

    again = instance.get_screen(screen.id)
    assert again.properties['result'] == 'no hits'
    assert again.wellplates == []
    assert instance.get_wellplate(plate.id).id == plate.id  # unlinked, not deleted


def test_link_an_existing_research_plan(screen_setup):
    instance, col, screen, _ = screen_setup
    plan = col.new_research_plan()
    plan.save()
    screen.add_research_plan(plan)
    screen.save()
    assert [r.id for r in instance.get_screen(screen.id).research_plans] == [plan.id]


def test_the_server_creates_a_linked_research_plan(screen_setup):
    instance, col, screen, _ = screen_setup
    plan = screen.new_research_plan(col)
    assert plan.id is not None
    assert plan.json_data['name'] == 'New Research Plan 1 for Kinase panel'
    assert [r.id for r in instance.get_screen(screen.id).research_plans] == [plan.id]


def test_list_screens_of_a_collection(screen_setup):
    _, col, screen, _ = screen_setup
    assert [s.id for s in col.get_screens(per_page=None)] == [screen.id]


def test_move_a_screen_between_collections(screen_setup):
    _, col, screen, _ = screen_setup
    dest = col.get_or_create_collection('Dest')
    col.get_root().save()
    col.move_elements(dest, screen)
    assert [s.id for s in dest.get_screens(per_page=None)] == [screen.id]
    assert list(col.get_screens(per_page=None)) == []


def test_delete_a_screen(screen_setup):
    instance, _, screen, plate = screen_setup
    assert screen.delete() is True
    with pytest.raises(ChemotionRequestError, match='404'):
        instance.get_screen(screen.id)
    assert instance.get_wellplate(plate.id).id == plate.id
