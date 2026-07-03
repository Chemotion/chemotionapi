from chem_dcat_ap.datamodel.chem_dcat_ap_pydantic import (
    SubstanceSample,
    StartingMaterial,
    Reagent,
    ChemicalProduct,
    ChemicalReaction,
)

def test_sample_to_dcat_ap_standalone(instance_with_collection):
    mc = instance_with_collection['main_collection']
    
    # Create a simple sample
    s = mc.new_sample_smiles("CCO")
    s.name = "Ethanol sample"
    s.properties["external_label"] = "EXT-123"
    s.properties["description"] = "Test ethanol sample"
    s.save()

    # Standalone sample should map to SubstanceSample
    dcat_obj = s.to_dcat_ap()
    assert isinstance(dcat_obj, SubstanceSample)
    assert dcat_obj.title == s.properties.get("short_label") or s.name
    assert dcat_obj.description == "Test ethanol sample"
    
    # Composed of chemical entity should contain smiles and molecular mass
    assert dcat_obj.composed_of is not None
    assert len(dcat_obj.composed_of) == 1
    entity = dcat_obj.composed_of[0]
    assert entity.smiles is not None
    assert entity.smiles[0].value == "CCO"
    assert entity.has_molar_mass is not None
    assert entity.has_molar_mass[0].value > 46.0

def test_reaction_and_components_to_dcat_ap(instance_with_collection):
    instance = instance_with_collection['instance']
    mc = instance_with_collection['main_collection']

    # Create a reaction
    r = mc.new_reaction()
    r.name = "Synthesis of water"
    r.properties["description"] = "Reaction description test"
    r.properties["yield"] = 95.0
    r.save()

    # Create components
    s1 = mc.new_sample_smiles("[H][H]") # Hydrogen
    s1.properties["purity"] = 0.99
    s1.save()

    s2 = mc.new_sample_smiles("O=O") # Oxygen
    s2.properties["purity"] = 0.98
    s2.save()

    s3 = mc.new_sample_smiles("O") # Water
    s3.save()

    # Add components to reaction
    r.starting_materials.append(s1)
    r.reactants.append(s2)
    r.products.append(s3)
    r.save()

    # Get reaction from instance to ensure clean properties
    r_loaded = instance.get_reaction(r.id)
    
    # Verify mapping to ChemicalReaction
    dcat_reaction = r_loaded.to_dcat_ap()
    assert isinstance(dcat_reaction, ChemicalReaction)
    assert dcat_reaction.description == ["Reaction description test"]
    assert dcat_reaction.has_yield is not None
    assert dcat_reaction.has_yield[0].value == 95.0

    # Verify nested lists are correctly typed
    assert dcat_reaction.used_starting_material is not None
    assert len(dcat_reaction.used_starting_material) == 1
    assert isinstance(dcat_reaction.used_starting_material[0], StartingMaterial)
    
    assert dcat_reaction.used_reactant is not None
    assert len(dcat_reaction.used_reactant) == 1
    assert isinstance(dcat_reaction.used_reactant[0], Reagent)
    
    assert dcat_reaction.generated_product is not None
    assert len(dcat_reaction.generated_product) == 1
    assert isinstance(dcat_reaction.generated_product[0], ChemicalProduct)
