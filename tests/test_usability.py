import pytest
from chemotion_api import Instance

def test_instance_inline_login_and_context_manager(config_login):
    # Test context manager and constructor login
    with Instance(
        config_login.get('ELN_URL'),
        username=config_login.get('ELN_USER'),
        password=config_login.get('ELN_PASS')
    ) as instance:
        assert instance.token is not None
        # Test direct collection helper
        root_col = instance.get_root_collection()
        path = "Usability Test Collection"
        
        # Cleanup if exists
        try:
            old_col = instance.get_collection(path)
            old_col.delete()
            # Save parent
            root_col.save()
        except Exception:
            pass

        # Create collection directly from instance
        col = instance.get_or_create_collection(path)
        assert col is not None
        assert col.label == path
        
        # Retrieve collection directly from instance
        retrieved_col = instance.get_collection(path)
        assert retrieved_col.id == col.id

        # Clean up
        col.delete()
        root_col.save()

def test_property_dict_attribute_access(instance_with_collection):
    mc = instance_with_collection['main_collection']
    
    # Create sample
    s = mc.new_sample_smiles("CCO")
    s.name = "Usability Ethanol"
    
    # Verify attribute getter works
    assert s.properties.description == ""
    
    # Verify attribute setter works
    s.properties.description = "Usability test description"
    assert s.properties["description"] == "Usability test description"
    assert s.properties.description == "Usability test description"

    # Verify Pydantic validation works through attribute assignment
    s.properties.purity = 0.98
    assert s.properties["purity"] == 0.98
    assert s.properties.purity == 0.98

    # Verify AttributeError is raised for invalid keys on retrieval
    with pytest.raises(AttributeError):
        _ = s.properties.invalid_key_name_xyz
        
    # Dynamic PropertyDict allows setting new attributes (like normal dict item assignment)
    s.properties.dynamic_new_attribute_abc = "dynamic value"
    assert s.properties.dynamic_new_attribute_abc == "dynamic value"
    assert s.properties["dynamic_new_attribute_abc"] == "dynamic value"

    # FixedDict/UnitDict (like molarity) raises AttributeError on setting invalid keys
    assert s.properties.molarity is not None
    with pytest.raises(AttributeError):
        s.properties.molarity.invalid_key_xyz = "value"


def test_representations(instance_with_collection):
    mc = instance_with_collection['main_collection']
    
    # Create element
    s = mc.new_sample_smiles("CCO")
    s.name = "Repr test"
    s.save()
    
    # Verify custom __str__ and __repr__ on Sample element
    s_str = str(s)
    s_repr = repr(s)
    assert s_str == f"Sample(id={s.id}, name='Repr test')"
    assert s_repr == f"Sample(id={s.id}, name='Repr test')"
    
    # Verify custom __repr__ on Collection
    col_repr = repr(mc)
    assert f"id={mc.id}" in col_repr
    assert f"path={mc.get_path()!r}" in col_repr
