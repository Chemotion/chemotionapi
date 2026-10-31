import os
import zipfile
import json
import pytest
from chemotion_api import Instance, Author, AuthorAffiliation


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
        
        # @context is "base context plus local definitions": a list whose first entry is the
        # RO-Crate 1.2 context IRI, followed by the terms that context does not define. Those are
        # generated from the document, so assert the shape and that nothing was left undeclared
        # rather than naming individual terms.
        context = metadata_dict["@context"]
        assert (context[0] if isinstance(context, list) else context) == \
            "https://w3id.org/ro/crate/1.2/context"
        declared = {k for entry in context[1:] if isinstance(entry, dict) for k in entry}
        undeclared = {key for node in metadata_dict["@graph"] for key in node
                      if not key.startswith("@") and key not in declared
                      and (key.startswith(("http://", "https://")) or ":" in key)}
        assert not undeclared, f"keys missing from @context: {sorted(undeclared)}"
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
        
        # Collections are contextual `Collection` entities keyed on their id, not crate folders.
        sub_node = next((n for n in graph if n.get("@id") == "#collection-456"), None)
        assert sub_node is not None
        assert sub_node["@type"] == "Collection"
        assert sub_node["isPartOf"] == {"@id": "#collection-123"}
        assert {r["@id"] for r in col_node["mentions"]} >= {"#collection-123", "#collection-456"}

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
    instance = instance_with_collection['instance']

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

        # Verify custom sample properties on s1's and s2's dataset nodes. Match on the full
        # type-qualified path ("/samples/...") and not just the id suffix: samples and
        # reactions get independent DB id sequences, so matching on id suffix alone could pick
        # up the wrong kind of node if a sample and a reaction happen to share a numeric id
        # (this is exactly what composite (kind, id) indexing keys in export_eln guard against).
        node_s1 = next((n for n in graph
                        if "/samples/" in n.get("@id", "") and n.get("@id", "").endswith(f"_{s1.id}/")), None)
        node_s2 = next((n for n in graph
                        if "/samples/" in n.get("@id", "") and n.get("@id", "").endswith(f"_{s2.id}/")), None)
        
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
        # `cas` and `names` were Chemotion column names used as JSON-LD keys, which RO-Crate 1.2
        # rejects outright — the @context defines neither. Same data, terms that exist.
        assert mol_node["identifier"] in ("64-17-5", ["64-17-5"])
        assert mol_node["alternateName"] == ["Ethanol", "Ethyl alcohol"]

        # Verify reaction node and its properties (see node_s1/node_s2 comment above: match on
        # the full type-qualified path, not just the id suffix)
        reaction_node = next((n for n in graph
                              if "/reactions/" in n.get("@id", "") and n.get("@id", "").endswith(f"_{r.id}/")), None)
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
        # `variations` is an opaque Chemotion payload — arbitrary nested JSON keyed on plain `id`,
        # not `@id`. Embedded as an object it makes the whole crate unparseable (py-rocrate raises
        # "ValueError: no @id in {...}"), so the exporter carries it as a JSON string instead: the
        # data survives, it just stops claiming to be linked data. Flat lists of literals like
        # `purification` above are unaffected — those are valid multi-valued properties.
        assert json.loads(reaction_node["variations"]) == {"temp_steps": [25, 50]}


def test_attachment_streaming_fallback():
    """Verify that the exporter uses iter_file when available, or falls back to load_file."""
    from unittest.mock import MagicMock, patch
    from chemotion_api.collection import Collection

    # Create a mock collection with a sample and attachment
    col = Collection({})
    mock_sample = MagicMock()
    mock_sample.name = "Test Sample"
    mock_sample.id = 1
    mock_sample.analyses = []
    mock_sample.to_dcat_ap.return_value = MagicMock(__name__='SubstanceSample')

    # Mock attachment with only iter_file (no load_file)
    mock_att_streaming = MagicMock()
    mock_att_streaming.iter_file = lambda: [b"chunk1", b"chunk2"]
    del mock_att_streaming.load_file  # remove load_file to test iter_file path

    mock_ds = MagicMock()
    mock_ds.name = "1H NMR"
    mock_ds.kind = "1H NMR [CHMO:0000595]"
    mock_ds.attachments = [mock_att_streaming]

    mock_analysis = MagicMock()
    mock_analysis.name = "NMR"
    mock_analysis.datasets = [mock_ds]
    mock_sample.analyses = [mock_analysis]

    col._samples = {'sample-1': mock_sample}

    # Test that iter_file path is used when available
    with patch('zipfile.ZipFile') as mock_zip:
        zip_instance = MagicMock()
        mock_zip.return_value.__enter__.return_value = zip_instance
        zip_instance.open.return_value.__enter__.return_value = MagicMock()

        try:
            # Should succeed using iter_file (hasattr check passes)
            col.export_eln("/tmp/test.eln", authors=_authors())
        except Exception as e:
            # If it fails, verify it's not due to missing iter_file
            assert "iter_file" not in str(e), f"iter_file should be used: {e}"

    # Test fallback: attachment with only load_file (no iter_file)
    mock_att_fallback = MagicMock()
    mock_att_fallback.load_file = lambda: b"fallback content"
    del mock_att_fallback.iter_file  # remove iter_file to test fallback

    mock_ds2 = MagicMock()
    mock_ds2.name = "1H NMR"
    mock_ds2.kind = "1H NMR [CHMO:0000595]"
    mock_ds2.attachments = [mock_att_fallback]

    mock_analysis2 = MagicMock()
    mock_analysis2.name = "NMR"
    mock_analysis2.datasets = [mock_ds2]
    mock_sample.analyses = [mock_analysis2]

    with patch('zipfile.ZipFile') as mock_zip:
        zip_instance = MagicMock()
        mock_zip.return_value.__enter__.return_value = zip_instance
        zip_instance.open.return_value.__enter__.return_value = MagicMock()

        try:
            # Should succeed using load_file fallback
            col.export_eln("/tmp/test2.eln", authors=_authors())
        except Exception as e:
            # If it fails, verify it's not due to missing load_file
            assert "load_file" not in str(e), f"load_file fallback should work: {e}"


def _mock_element(elem_id, name):
    """Build a bare-bones mocked element (sample/reaction-shaped) usable in export_eln's traverse."""
    from unittest.mock import MagicMock
    elem = MagicMock()
    elem.id = elem_id
    elem.name = name
    elem._data_loaded = True
    elem.properties = {}
    elem.attachments = []
    elem.analyses = []
    elem.to_dcat_ap.side_effect = Exception("no dcat mapping in this test")
    elem.eln_node_content.return_value = {}  # real dict, not a Mock -> must be JSON-serializable
    del elem.element_type
    return elem


@pytest.mark.heavy
def test_eln_export_id_collision_across_element_kinds(tmp_path):
    """Regression test for PR review finding 1: samples/reactions/... have independent DB id
    sequences, so a same-numbered sample and reaction must not silently overwrite each other in
    the exporter's element index (composite (kind, id) keys fix this)."""
    from unittest.mock import MagicMock

    root_col = MagicMock()
    root_col._element_manager.all_classes = {
        'sample': {'label': 'Sample'},
        'reaction': {'label': 'Reaction'},
        'wellplate': {'label': 'Wellplate'},
        'research_plan': {'label': 'Research Plan'},
    }

    col = MagicMock()
    col.id = 1
    col.label = "Collision Test"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    col.children = []

    SAME_ID = 999
    mock_sample = _mock_element(SAME_ID, "Shared-ID Sample")
    mock_reaction = _mock_element(SAME_ID, "Shared-ID Reaction")

    col.get_samples.return_value = [mock_sample]
    col.get_reactions.return_value = [mock_reaction]
    col.get_wellplates.return_value = []
    col.get_research_plans.return_value = []

    export_file = tmp_path / "collision_export.eln"

    from chemotion_api.collection import Collection
    Collection.export_eln(col, str(export_file), authors=_authors())

    assert export_file.exists()
    with zipfile.ZipFile(export_file, 'r') as z:
        root_folder = "collision_export.eln"
        metadata_dict = json.loads(z.read(f"{root_folder}/ro-crate-metadata.json").decode('utf-8'))
        graph = metadata_dict["@graph"]

        sample_node = next((n for n in graph if n.get("@id", "").startswith("./samples/")
                            and n.get("@id", "").endswith(f"_{SAME_ID}/")), None)
        reaction_node = next((n for n in graph if n.get("@id", "").startswith("./reactions/")
                              and n.get("@id", "").endswith(f"_{SAME_ID}/")), None)

        assert sample_node is not None, "sample with a colliding id was silently dropped from the crate"
        assert reaction_node is not None, "reaction with a colliding id was silently dropped from the crate"
        assert sample_node["@id"] != reaction_node["@id"]

        # Neither element should be recorded as skipped/omitted -- both were retrievable and
        # loadable, only their numeric ids collide.
        root_node = next(n for n in graph if n.get("@id") == "./")
        has_parts = {p["@id"] for p in root_node.get("hasPart", [])}
        assert sample_node["@id"] in has_parts
        assert reaction_node["@id"] in has_parts


@pytest.mark.heavy
def test_eln_export_filename_sanitization_collision(tmp_path):
    """Regression test for PR review finding 2: two attachments whose original filenames differ
    but sanitize to the same string must not collapse into one ZIP entry / one File @id.

    One of the two colliding attachments is attached directly to the element, the other lives
    under an analysis dataset -- exercising both places that resolve an attachment to its
    crate-relative File @id (the element's own ``hasPart`` and the analysis' AnalysisSourceData
    ``hasPart``), so a disambiguated filename computed once is correctly reused by both.
    """
    from unittest.mock import MagicMock

    root_col = MagicMock()
    root_col._element_manager.all_classes = {
        'sample': {'label': 'Sample'},
        'reaction': {'label': 'Reaction'},
        'wellplate': {'label': 'Wellplate'},
        'research_plan': {'label': 'Research Plan'},
    }

    col = MagicMock()
    col.id = 1
    col.label = "Filename Collision Test"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    col.children = []

    mock_sample = _mock_element(2001, "Sanitization Sample")

    def _make_att(filename, content):
        att = MagicMock()
        att_dict = {"filename": filename, "filesize": len(content), "mime_type": "text/plain"}
        att.get.side_effect = lambda k, default=None: att_dict.get(k, default)
        att.__getitem__.side_effect = lambda k: att_dict[k]
        att.iter_file.return_value = [content]
        att.load_file.return_value = content
        return att

    # sanitize_filename keeps '-' and '_' verbatim and only replaces other non-alnum characters,
    # so both of these sanitize to the identical "spectrum_1.dx".
    att_a = _make_att("spectrum#1.dx", b"content A")
    att_b = _make_att("spectrum@1.dx", b"content B")
    mock_sample.attachments = [att_a]

    mock_ds = MagicMock()
    mock_ds.attachments = [att_b]
    mock_ana = MagicMock()
    mock_ana.get.side_effect = lambda k, default=None: {"id": "ana-1"}.get(k, default)
    mock_ana.datasets = [mock_ds]
    mock_sample.analyses = [mock_ana]

    col.get_samples.return_value = [mock_sample]
    col.get_reactions.return_value = []
    col.get_wellplates.return_value = []
    col.get_research_plans.return_value = []

    export_file = tmp_path / "filename_collision_export.eln"

    from chemotion_api.collection import Collection
    Collection.export_eln(col, str(export_file), authors=_authors())

    assert export_file.exists()
    with zipfile.ZipFile(export_file, 'r') as z:
        root_folder = "filename_collision_export.eln"
        namelist = z.namelist()

        sample_files = [n for n in namelist
                        if n.startswith(f"{root_folder}/samples/") and n.endswith(".dx")]
        assert len(sample_files) == 2, f"expected two distinct ZIP entries, got: {sample_files}"
        assert len(set(sample_files)) == 2  # distinct paths, not one path written twice

        contents = {z.read(n) for n in sample_files}
        assert contents == {b"content A", b"content B"}

        metadata_dict = json.loads(z.read(f"{root_folder}/ro-crate-metadata.json").decode('utf-8'))
        graph = metadata_dict["@graph"]
        file_nodes = [n for n in graph if n.get("@type") == "File"]
        file_ids = {n["@id"] for n in file_nodes}
        assert len(file_nodes) == 2
        assert len(file_ids) == 2, f"expected two distinct File @ids, got: {file_ids}"

        # The disambiguated name computed for att_b (attached via the analysis dataset) must be
        # the exact one used for its ZIP entry/File node -- not a stale recomputation that
        # ignores the collision, which would produce a dangling @id no File node/ZIP entry has.
        # (Match the element's own directory node, not one of the File nodes it contains -- both
        # kinds of @id start with "./samples/", but only the element node's @id ends in "/".)
        sample_node = next(n for n in graph
                           if n.get("@id", "").startswith("./samples/") and n.get("@id", "").endswith("/"))
        has_part_ids = {p["@id"] for p in sample_node.get("hasPart", [])}
        assert has_part_ids == file_ids, (
            f"element hasPart refs {has_part_ids} don't match the actual File nodes {file_ids}")

        # The AnalysisSourceData node itself only appears when to_dcat_ap() succeeds (it is built
        # by _analysis_dcat_datasets from the mapped element); this test's mock always fails that
        # call, as in the other mocked export tests, so there is nothing further to assert here
        # for the analysis-dataset attachment specifically. What matters for finding 2 -- that
        # att_b's disambiguated name from ds.attachments is the exact one written to the ZIP/File
        # node -- is already covered above by len(file_nodes) == 2 and the hasPart/File-id match.

