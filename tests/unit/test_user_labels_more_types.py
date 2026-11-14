"""User labels on wellplates, research plans and screens (ported from M1.6)."""
import json
import os


def test_screen_wellplate_and_research_plan_round_trip_user_labels():
    from chemotion_api.elements.research_plan import ResearchPlan
    from chemotion_api.elements.screen import Screen
    from chemotion_api.elements.wellplate import Wellplate
    from chemotion_api.schema_manager import SchemaManager

    class _About:
        status_code, text = 200, '<h4>Version: v4.0.0</h4>'

    session = type('_S', (), {'schema_manager': SchemaManager(_About()), '_host_url': 'http://x'})()
    segments = type('_Seg', (), {'all_classes': []})()
    with open(os.path.join(os.path.dirname(__file__), 'data', 'screen_v4_main.json')) as f:
        screen_json = json.load(f)
    screen_json['user_labels'] = [4]
    plate_json = dict(screen_json['wellplates'][0], user_labels=[4])
    plan_json = dict(screen_json['research_plans'][0], user_labels=[4])

    for cls, payload in [(Screen, screen_json), (Wellplate, plate_json), (ResearchPlan, plan_json)]:
        element = cls(segments, session, json_data=payload)
        assert element.properties['user_labels'] == [4], cls.__name__
        element.properties['user_labels'] = [4, 8]
        assert element.clean_data()['user_labels'] == [4, 8], cls.__name__
