"""Two-factor login, API tokens and short-label counters on a live ELN (M7.2, M7.3).

The seeded accounts have no two-factor login, and enabling it needs the emailed link, so token
creation is checked only for its refusal here; the round trip is unit-tested.
"""
import pytest

pytestmark = pytest.mark.integration


def test_tokens_need_two_factor_login(logged_in_instance):
    assert logged_in_instance.two_factor_enabled() is False
    assert isinstance(logged_in_instance.api_tokens(), list)
    with pytest.raises(PermissionError, match='two-factor'):
        logged_in_instance.create_api_token('000000')


def test_short_label_counters(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    instance.set_short_label_counter('wellplates', 500)
    plate = col.new_wellplate()
    plate.save()
    assert plate.short_label.endswith('-WP501')
    user = instance._con.get('/api/v1/users/current').json()['user']
    instance.set_reaction_short_label(user.get('reaction_name_prefix') or 'R', int(user['counters']['reactions']))
