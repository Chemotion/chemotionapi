import chemotion_api


def test_get_reaction_success(logged_in_instance: chemotion_api.Instance):
    d_col = logged_in_instance.get_root_collection().get_or_create_collection('DUMMIES')
    s = d_col.new_sample()
    s.toggle_decoupled()
    s.save()
    ra = d_col.new_reaction()
    ra.properties['starting_materials'].append(s)
    ra.save()