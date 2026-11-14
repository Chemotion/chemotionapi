"""LabIMotion Hub on a live ELN (M6.3). The import test needs the ELN to reach the central hub."""
import pytest

from chemotion_api.labImotion.items.options import ElementType

pytestmark = pytest.mark.integration


def test_this_eln_as_a_hub(logged_in_instance):
    gm = logged_in_instance.generic_manager()
    names = gm.active_element_names()
    assert {'sample', 'reaction', 'wrk'} <= set(names)
    assert 'sample' not in gm.active_element_names(generic_only=True)
    published = {t['name'] for t in gm.published_templates()}
    assert 'wrk' in published and published <= set(names)


def test_import_a_segment_template_from_the_hub(logged_in_instance):
    gm = logged_in_instance.generic_manager()
    try:
        offered = gm.hub_templates(ElementType.SEGMENT)
    except ConnectionError as e:
        pytest.skip(f'The LabIMotion Hub is not reachable from the ELN: {e}')
    if not offered:
        pytest.skip('The hub offers no segment templates.')
    template = offered[0]
    segments = gm.import_hub_template(template['identifier'], ElementType.SEGMENT)
    assert template['identifier'] in {s.identifier for s in segments}
    with pytest.raises(ConnectionError, match='failed'):
        gm.import_hub_template('00000000-0000-0000-0000-000000000000', ElementType.SEGMENT)
