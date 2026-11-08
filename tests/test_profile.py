"""Profile, editor settings and structure templates on a live ELN (M7.1)."""
import pytest

pytestmark = pytest.mark.integration


def test_display_options(logged_in_instance):
    profile = logged_in_instance.profile()
    original = profile.show_external_name
    try:
        profile.show_external_name = not original
        profile.save()
        assert logged_in_instance.profile().show_external_name is (not original)
    finally:
        profile.show_external_name = original
        profile.save()
    assert 'layout' in profile.data


def test_ketcher_options(logged_in_instance):
    original = logged_in_instance.ketcher_options()
    try:
        logged_in_instance.save_ketcher_options(original | {'showAtomIds': True})
        assert logged_in_instance.ketcher_options()['showAtomIds'] is True
    finally:
        logged_in_instance.save_ketcher_options(original or {'showAtomIds': False})


def test_structure_templates(logged_in_instance):
    profile = logged_in_instance.profile()
    profile.add_structure_template('{"struct": "", "props": {"atomid": 0, "bondid": 0}}')
    profile = logged_in_instance.profile()
    added = profile.structure_templates[-1]
    profile.delete_structure_template(added)
    assert added['props']['path'] not in {t['props']['path'] for t in logged_in_instance.profile().structure_templates}
    with pytest.raises(ValueError, match='Not one of'):
        profile.delete_structure_template({'props': {'path': '/etc/hostname'}})
