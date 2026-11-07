"""Text templates on a live ELN (M3.8)."""
import uuid

import pytest

from chemotion_api import Instance

pytestmark = pytest.mark.integration


def test_predefined_templates(logged_in_instance):
    tt = logged_in_instance.text_templates()
    names = tt.predefined_names()
    assert 'esi' in names
    assert tt.predefined('esi').text.startswith('MS (ESI)') or tt.predefined('esi').ops


def test_personal_templates(logged_in_instance):
    tt = logged_in_instance.text_templates()
    name = f'api test {uuid.uuid4().hex[:6]}'
    created = tt.create_personal(name, 'Yield after column: ')
    try:
        assert created.text == 'Yield after column: '
        with pytest.raises(ValueError):
            tt.create_personal(name, 'again')
        created.data = {'ops': [{'insert': 'changed'}]}
        assert tt.update_personal(created).text == 'changed'
        assert created.id in {t.id for t in tt.personal()}
    finally:
        tt.delete_personal(created)
    assert created.id not in {t.id for t in tt.personal()}


def test_toolbar_round_trip(logged_in_instance):
    tt = logged_in_instance.text_templates()
    original = tt.toolbar('reaction')
    try:
        assert tt.set_toolbar('reaction', {'_toolbar': ['h-nmr']}) == {'_toolbar': ['h-nmr']}
        assert tt.toolbar('reaction') == {'_toolbar': ['h-nmr']}
    finally:
        tt.set_toolbar('reaction', original)


def test_predefined_needs_an_editor(logged_in_instance, config_login):
    with pytest.raises(PermissionError):
        logged_in_instance.text_templates().create_predefined('api-test', 'x')
    admin = Instance(config_login['ELN_URL']).login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS'])
    tt = admin.text_templates()
    name = f'api-{uuid.uuid4().hex[:6]}'
    created = tt.create_predefined(name, 'shared snippet')
    try:
        assert tt.predefined(name).text == 'shared snippet'
    finally:
        tt.delete_predefined(name)
    assert tt.predefined(name) is None
