import os
import zipfile
import json
import pytest
from chemotion_api import Author, AuthorAffiliation


def _authors():
    """A valid author list for export_eln (authorship is mandatory: ORCID + ROR affiliation)."""
    return [Author(name="Test Author", orcid="0000-0002-1825-0097",
                   affiliations=[AuthorAffiliation(name="Org", ror="https://ror.org/04t3en479")])]


def test_eln_export_basic(instance_with_collection, tmp_path):
    mc = instance_with_collection['main_collection']
    instance = instance_with_collection['instance']
    
    # Create a simple sample with smiles
    s = mc.new_sample_smiles("CCO")
    s.name = "Ethanol sample"
    s.properties["description"] = "Test ethanol sample"
    s.save()
    
    # Reload sample
    s = instance.get_sample(s.id)
    
    # Add analysis and dataset attachment (path anchored to this file, not the CWD)
    test_file = os.path.join(os.path.dirname(__file__), "data", "SG-V3545-6-13.cif")
    s.analyses.add_analyses("T1").add_dataset(test_file)
    s.save()

    # Create a reaction
    r = mc.new_reaction()
    r.name = "Water synthesis"
    r.properties["description"] = "Synthesizing water"
    r.save()

    # Export the collection to ELN
    eln_file = tmp_path / "test_export.eln"
    mc.export_eln(str(eln_file), authors=_authors())

    # Verify zip structure
    assert eln_file.exists()
    assert zipfile.is_zipfile(eln_file)

    with zipfile.ZipFile(eln_file, 'r') as z:
        namelist = z.namelist()
        
        # Verify the root folder name ends with .eln
        root_folder = os.path.basename(str(eln_file))
        assert any(name.startswith(f"{root_folder}/") for name in namelist)
        
        # Check metadata file exists
        metadata_entry = f"{root_folder}/ro-crate-metadata.json"
        assert metadata_entry in namelist
        
        # Parse ro-crate-metadata.json
        metadata_content = z.read(metadata_entry).decode('utf-8')
        metadata_dict = json.loads(metadata_content)
        
        assert metadata_dict["@context"] == "https://w3id.org/ro/crate/1.1/context"
        graph = metadata_dict["@graph"]
        
        # Helper to check node type
        def has_type(node, type_name_or_uri):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            return any(type_name_or_uri in t for t in types)

        # 1. Verify ro-crate-metadata.json CreativeWork descriptor
        desc = next((node for node in graph if node.get("@id") == "ro-crate-metadata.json"), None)
        assert desc is not None
        assert has_type(desc, "CreativeWork")
        assert desc["about"] == {"@id": "./"}
        
        # 2. Verify root dataset "./"
        root_node = next((node for node in graph if node.get("@id") == "./"), None)
        assert root_node is not None
        assert has_type(root_node, "Dataset")
        assert "hasPart" in root_node
        
        has_parts = [part["@id"] for part in root_node["hasPart"]]
        
        # 3. Verify sample node exists in graph and lists its attachment in hasPart
        sample_node = next((node for node in graph if has_type(node, "SubstanceSample") or has_type(node, "SIO_001378")), None)
        assert sample_node is not None
        assert sample_node["@id"] in has_parts
        assert has_type(sample_node, "Dataset")
        assert "hasPart" in sample_node
        assert len(sample_node["hasPart"]) == 1
        
        att_id = sample_node["hasPart"][0]["@id"]
        assert att_id.startswith(sample_node["@id"])
        assert att_id.endswith("SG-V3545-6-13.cif")
        
        # Verify attachment file node exists in graph
        att_node = next((node for node in graph if node.get("@id") == att_id), None)
        assert att_node is not None
        assert has_type(att_node, "File")
        assert att_node["name"] == "SG-V3545-6-13.cif"
        
        # Verify the attachment file actually exists in the zip
        zip_att_entry = f"{root_folder}/{att_id.lstrip('./')}"
        assert zip_att_entry in namelist
        
        # Verify content matches
        original_content = open(test_file, 'rb').read()
        zip_content = z.read(zip_att_entry)
        assert zip_content == original_content

        # 4. Verify reaction node exists in graph
        reaction_node = next((node for node in graph if has_type(node, "ChemicalReaction") or has_type(node, "SIO_010345")), None)
        assert reaction_node is not None
        assert reaction_node["@id"] in has_parts
        assert has_type(reaction_node, "Dataset")

@pytest.mark.heavy
def test_eln_export_mocked(tmp_path):
    from unittest.mock import MagicMock
    
    # 1. Mock root collection
    root_col = MagicMock()
    root_col._element_manager.all_classes = {
        'sample': {'label': 'Sample'},
        'reaction': {'label': 'Reaction'},
        'wellplate': {'label': 'Wellplate'},
        'research_plan': {'label': 'Research Plan'},
        'custom_generic': {'label': 'Custom Generic'}
    }
    
    # 2. Create target collection
    col = MagicMock()
    col.id = 123
    col.label = "Mock Collection / Special & Chars!"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    
    # 3. Create sub-collection
    sub_col = MagicMock()
    sub_col.id = 456
    sub_col.label = "" # Empty name to trigger "unnamed" fallback
    sub_col.get_root.return_value = root_col
    sub_col._parent = col
    sub_col.collection_json = None
    sub_col.children = []
    
    col.children = [sub_col]
    
    # Mock elements for col
    mock_sample = MagicMock()
    mock_sample.id = 1001
    mock_sample.name = None # Test name fallback
    mock_sample._data_loaded = False
    mock_sample.properties = {"short_label": "S-1001", "description": "Mock sample desc"}
    del mock_sample.element_type
    
    # Direct attachment
    mock_att = MagicMock()
    att_dict = {"filename": "direct.txt", "filesize": 1234, "mime_type": "text/plain"}
    mock_att.get.side_effect = lambda k, default=None: att_dict.get(k, default)
    mock_att.__getitem__.side_effect = lambda k: att_dict[k]
    mock_att.load_file.return_value = b"direct attachment content"
    mock_att.iter_file.return_value = [b"direct attachment ", b"content"]  # streamed in chunks
    mock_sample.attachments = [mock_att]
    
    # Nested dataset attachment
    mock_ana = MagicMock()
    mock_ds = MagicMock()
    mock_ds_att = MagicMock()
    ds_att_dict = {"filename": "dataset.txt", "contentSize": 5678, "content_type": "text/plain"}
    mock_ds_att.get.side_effect = lambda k, default=None: ds_att_dict.get(k, default)
    mock_ds_att.__getitem__.side_effect = lambda k: ds_att_dict[k]
    mock_ds_att.load_file.return_value = b"dataset attachment content"
    mock_ds_att.iter_file.return_value = [b"dataset attachment content"]  # streamed
    mock_ds.attachments = [mock_ds_att]
    mock_ana.datasets = [mock_ds]
    mock_sample.analyses = [mock_ana]
    mock_sample.eln_node_content.return_value = {}  # real dict (Mock would inject junk into the crate)
    
    mock_sample.to_dcat_ap.side_effect = Exception("Mapping failed")
    
    col.get_samples.return_value = [mock_sample]
    col.get_reactions.return_value = []
    
    # Wellplate
    mock_wp = MagicMock()
    mock_wp.id = 2001
    mock_wp.name = "Wellplate 1"
    mock_wp._data_loaded = True
    mock_wp.properties = {}
    mock_wp.attachments = []
    mock_wp.to_dcat_ap.side_effect = Exception("No DCAT")
    del mock_wp.element_type
    mock_wp.eln_node_content.return_value = {}
    del mock_wp.analyses
    col.get_wellplates.return_value = [mock_wp]
    
    # Research plan
    mock_rp = MagicMock()
    mock_rp.id = 3001
    mock_rp.name = "Research Plan 1"
    mock_rp._data_loaded = True
    mock_rp.properties = {}
    mock_rp.attachments = []
    mock_rp.to_dcat_ap.side_effect = Exception("No DCAT")
    del mock_rp.element_type
    mock_rp.eln_node_content.return_value = {}
    del mock_rp.analyses
    col.get_research_plans.return_value = [mock_rp]
    
    # Custom generic
    mock_gen = MagicMock()
    mock_gen.id = 4001
    mock_gen.name = "Custom Generic 1"
    mock_gen._data_loaded = True
    mock_gen.properties = {}
    mock_gen.attachments = []
    mock_gen.to_dcat_ap.side_effect = Exception("No DCAT")
    del mock_gen.element_type
    mock_gen.eln_node_content.return_value = {}
    del mock_gen.analyses
    col.get_generics_by_name.return_value = [mock_gen]
    
    # Empty lists for sub_col
    sub_col.get_samples.return_value = []
    sub_col.get_reactions.return_value = []
    sub_col.get_wellplates.return_value = []
    sub_col.get_research_plans.return_value = []
    sub_col.get_generics_by_name.return_value = []
    
    export_file = tmp_path / "mock_export.eln"
    
    from chemotion_api.collection import Collection
    Collection.export_eln(col, str(export_file), authors=_authors())
    
    assert export_file.exists()
    with zipfile.ZipFile(export_file, 'r') as z:
        namelist = z.namelist()
        root_folder = "mock_export.eln"
        
        assert f"{root_folder}/ro-crate-metadata.json" in namelist
        assert f"{root_folder}/samples/S-1001_1001/direct.txt" in namelist
        assert f"{root_folder}/samples/S-1001_1001/dataset.txt" in namelist
        
        metadata_dict = json.loads(z.read(f"{root_folder}/ro-crate-metadata.json").decode('utf-8'))
        graph = metadata_dict["@graph"]
        
        col_node = next((n for n in graph if n.get("@id") == "./"), None)
        assert col_node is not None
        assert col_node["name"] == "Mock Collection / Special & Chars!"
        
        sub_node = next((n for n in graph if n.get("@id") == "./subcollection_456/"), None)
        assert sub_node is not None
        assert sub_node["isPartOf"] == {"@id": "./"}

@pytest.mark.heavy
def test_eln_export_exceptions(tmp_path):
    from unittest.mock import MagicMock
    import zipfile
    
    root_col = MagicMock()
    root_col._element_manager.all_classes = {
        'sample': {'label': 'Sample'},
        'reaction': {'label': 'Reaction'},
        'wellplate': {'label': 'Wellplate'},
        'research_plan': {'label': 'Research Plan'}
    }
    
    col = MagicMock()
    col.id = 789
    col.label = "Exceptions Test"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = {"description": "Exceptions collection desc"}
    col.children = []
    
    col.get_samples.side_effect = Exception("Samples retrieve error")
    col.get_reactions.side_effect = Exception("Reactions retrieve error")
    col.get_wellplates.side_effect = Exception("Wellplates retrieve error")
    col.get_research_plans.side_effect = Exception("Research plans retrieve error")
    
    export_file = tmp_path / "exceptions_export.eln"
    
    from chemotion_api.collection import Collection
    Collection.export_eln(col, str(export_file), authors=_authors())
    
    assert export_file.exists()
    with zipfile.ZipFile(export_file, 'r') as z:
        namelist = z.namelist()
        root_folder = "exceptions_export.eln"
        assert f"{root_folder}/ro-crate-metadata.json" in namelist

@pytest.mark.heavy
def test_eln_export_load_exceptions(tmp_path):
    from unittest.mock import MagicMock
    
    root_col = MagicMock()
    root_col._element_manager.all_classes = {
        'sample': {'label': 'Sample'},
        'reaction': {'label': 'Reaction'},
        'wellplate': {'label': 'Wellplate'},
        'research_plan': {'label': 'Research Plan'}
    }
    
    col = MagicMock()
    col.id = 789
    col.label = "Load Exceptions Test"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    col.children = []
    
    mock_sample = MagicMock()
    mock_sample.id = 1001
    mock_sample.name = "Sample Load Error"
    mock_sample._data_loaded = False
    mock_sample.load.side_effect = Exception("Load error")
    mock_sample.properties = {}
    mock_sample.attachments = []
    mock_sample.analyses = []
    mock_sample.to_dcat_ap.side_effect = Exception("Mapping failed")
    mock_sample.eln_node_content.return_value = {}
    del mock_sample.element_type
    
    col.get_samples.return_value = [mock_sample]
    col.get_reactions.return_value = []
    col.get_wellplates.return_value = []
    col.get_research_plans.return_value = []
    
    export_file = tmp_path / "load_exceptions_export.eln"
    
    from chemotion_api.collection import Collection
    Collection.export_eln(col, str(export_file), authors=_authors())
    
    assert export_file.exists()

@pytest.mark.heavy
def test_eln_export_attachment_write_exceptions(tmp_path):
    from unittest.mock import MagicMock
    
    root_col = MagicMock()
    root_col._element_manager.all_classes = {
        'sample': {'label': 'Sample'},
        'reaction': {'label': 'Reaction'},
        'wellplate': {'label': 'Wellplate'},
        'research_plan': {'label': 'Research Plan'}
    }
    
    col = MagicMock()
    col.id = 789
    col.label = "Write Exceptions Test"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    col.children = []
    
    mock_sample = MagicMock()
    mock_sample.id = 1001
    mock_sample.name = "Attachment Load Error"
    mock_sample._data_loaded = True
    mock_sample.properties = {}
    
    mock_att = MagicMock()
    att_dict = {"filename": "broken.txt", "filesize": 1234, "mime_type": "text/plain"}
    mock_att.get.side_effect = lambda k, default=None: att_dict.get(k, default)
    mock_att.__getitem__.side_effect = lambda k: att_dict[k]
    mock_att.load_file.side_effect = Exception("Download broken")
    mock_att.iter_file.side_effect = Exception("Download broken")  # streaming path now used
    mock_sample.attachments = [mock_att]
    
    mock_sample.analyses = []
    mock_sample.to_dcat_ap.side_effect = Exception("Mapping failed")
    mock_sample.eln_node_content.return_value = {}
    del mock_sample.element_type
    
    col.get_samples.return_value = [mock_sample]
    col.get_reactions.return_value = []
    col.get_wellplates.return_value = []
    col.get_research_plans.return_value = []
    
    export_file = tmp_path / "write_exceptions_export.eln"
    
    from chemotion_api.collection import Collection
    Collection.export_eln(col, str(export_file), authors=_authors())
    
    assert export_file.exists()


def test_eln_export_properties_and_deduplication(instance_with_collection, tmp_path):
    mc = instance_with_collection['main_collection']

    # 1. Create and save samples
    s1 = mc.new_sample_smiles("CCO")
    s1.name = "Sample 1"
    s1.save()
    
    mol_id = s1.molecule.id
    assert mol_id is not None

    s2 = mc.new_sample_smiles("CCO")
    s2.name = "Sample 2"
    s2.save()
    
    # Assert they share the same molecule ID
    assert s2.molecule.id == mol_id

    # 2. Create and save reaction
    r = mc.new_reaction()
    r.name = "Test Reaction With Properties"
    r.starting_materials.append(s1)
    r.products.append(s2)
    r.save()

    # Mock collection getters to return our in-memory objects during traverse
    mc.get_samples = lambda **kwargs: [s1, s2]
    mc.get_reactions = lambda **kwargs: [r]

    # 3. Enrich properties IN-MEMORY after all saves to prevent server-response overwrite
    s1.properties["dry_solvent"] = True
    s1.properties["impurities"] = "trace water"
    s1.properties["xref"] = {"PubChem": "702"}
    
    # Set cas and names on s1's molecule
    s1.molecule["cas"] = "64-17-5"
    s1.molecule["names"] = ["Ethanol", "Ethyl alcohol"]

    s2.properties["dry_solvent"] = False
    s2.properties["impurities"] = "none"
    s2.properties["xref"] = {"PubChem": "702"}

    # Set custom reaction properties
    r.properties["rxno"] = "RXN-12345"
    r.properties["conditions"] = "nitrogen atmosphere, RT"
    r.properties["purification"] = ["Extraction", "Filtration"]
    r.properties["tlc_solvents"] = "Hexane/EtOAc 4:1"
    r.properties["rf_value"] = "0.35"
    r.properties["volume"] = 10.5
    r.properties["use_reaction_volume"] = True
    r.properties["weight_percentage"] = True
    r.properties["rinchi_string"] = "Long-RInChI-String"
    r.properties["rinchi_web_key"] = "RInChI-Web-Key"
    r.properties["variations"] = {"temp_steps": [25, 50]}

    # Export
    eln_file = tmp_path / "dedup_properties_export.eln"
    mc.export_eln(str(eln_file), authors=_authors())

    # Parse and verify
    assert eln_file.exists()
    assert zipfile.is_zipfile(eln_file)

    with zipfile.ZipFile(eln_file, 'r') as z:
        root_folder = os.path.basename(str(eln_file))
        metadata_entry = f"{root_folder}/ro-crate-metadata.json"
        assert metadata_entry in z.namelist()
        
        metadata_content = z.read(metadata_entry).decode('utf-8')
        metadata_dict = json.loads(metadata_content)
        graph = metadata_dict["@graph"]

        # Helper to check node type
        def has_type(node, type_name_or_uri):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            return any(type_name_or_uri in t for t in types)

        # Verify custom sample properties on s1's and s2's dataset nodes
        node_s1 = next((n for n in graph if n.get("@id").endswith(f"_{s1.id}/")), None)
        node_s2 = next((n for n in graph if n.get("@id").endswith(f"_{s2.id}/")), None)
        
        assert node_s1 is not None
        assert node_s2 is not None
        
        assert node_s1["dry_solvent"] is True
        assert node_s1["impurities"] == "trace water"
        assert node_s1["xref"] == {"PubChem": "702"}
        
        assert node_s2["dry_solvent"] is False
        assert node_s2["impurities"] == "none"
        assert node_s2["xref"] == {"PubChem": "702"}

        # Find the molecule node in the graph
        mol_nodes = [n for n in graph if n.get("@id") == f"#molecule_{mol_id}"]
        assert len(mol_nodes) == 1, f"Expected exactly 1 shared molecule node for ID {mol_id}, got: {mol_nodes}"
        
        mol_node = mol_nodes[0]
        assert has_type(mol_node, "ChemicalEntity") or has_type(mol_node, "CHEBI_23367")
        assert mol_node["cas"] in ("64-17-5", ["64-17-5"])
        assert mol_node["names"] == ["Ethanol", "Ethyl alcohol"]

        # Verify reaction node and its properties
        reaction_node = next((n for n in graph if n.get("@id").endswith(f"_{r.id}/")), None)
        assert reaction_node is not None
        
        assert reaction_node["rxno"] == "RXN-12345"
        assert reaction_node["conditions"] == "nitrogen atmosphere, RT"
        assert reaction_node["purification"] == ["Extraction", "Filtration"]
        assert reaction_node["tlc_solvents"] == "Hexane/EtOAc 4:1"
        assert reaction_node["rf_value"] == "0.35"
        assert reaction_node["volume"] == 10.5
        assert reaction_node["use_reaction_volume"] is True
        assert reaction_node["weight_percentage"] is True
        assert reaction_node["rinchi_string"] == "Long-RInChI-String"
        assert reaction_node["rinchi_web_key"] == "RInChI-Web-Key"
        assert reaction_node["variations"] == {"temp_steps": [25, 50]}

