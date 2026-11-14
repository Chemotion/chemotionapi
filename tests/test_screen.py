"""Screens against a live ELN v4: create with links, reload, edit from a listing, unlink."""
from chemotion_api.collection import Collection
from chemotion_api.elements import Screen


def test_screen_round_trip(instance_with_collection: dict):
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    wellplate = col.new_wellplate()
    wellplate.save()
    plan = col.new_research_plan()
    plan.save()

    screen = col.new_screen()
    assert isinstance(screen, Screen)
    screen.properties['name'] = 'API test screen'
    screen.properties['conditions'] = '37 °C'
    screen.wellplate_ids.append(wellplate.id)
    screen.research_plan_ids.append(plan.id)
    screen.save()

    loaded = instance.get_screen(screen.id)
    assert loaded.properties['name'] == 'API test screen'
    assert loaded.properties['conditions'] == '37 °C'
    assert loaded.wellplate_ids == [wellplate.id]
    assert loaded.research_plan_ids == [plan.id]
    assert [w.id for w in loaded.wellplates] == [wellplate.id]

    # A listing sends empty link lists; saving from it must not unlink anything.
    listed = next(s for s in col.get_screens() if s.id == screen.id)
    listed.properties['requirements'] = 'none'
    listed.save()
    again = instance.get_screen(screen.id)
    assert again.properties['requirements'] == 'none'
    assert again.wellplate_ids == [wellplate.id]
    assert again.research_plan_ids == [plan.id]

    again.wellplate_ids.clear()
    again.save()
    assert instance.get_screen(screen.id).wellplate_ids == []
