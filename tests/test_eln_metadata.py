"""The descriptive metadata `export_eln` attaches, beyond the chemistry graph.

A crate can be perfectly valid and still be poor to read. These tests pin the properties that make
an exported archive useful to someone who did not create it: when things were made, what they are
called, what produced the crate, and whether its files are intact.

Everything here runs offline against the committed mini fixture, so it also documents what an
offline export can and cannot supply — notably timestamps, which the Chemotion export dump does
not record at all.
"""
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from chemotion_api import Author, AuthorAffiliation

FIXTURE = Path(__file__).parent / "fixtures" / "mini_export.json"


def _authors():
    return [Author(name="Test Author", orcid="0000-0002-1825-0097",
                   affiliations=[AuthorAffiliation(name="Example Org",
                                                   ror="https://ror.org/05gq02987")])]


@pytest.fixture(scope="module")
def crate(tmp_path_factory):
    """Export the mini fixture once and hand every test the parsed crate + the archive path."""
    from chemotion_api.offline import import_export_zip
    work = tmp_path_factory.mktemp("crate")
    export_dir = work / "export"
    export_dir.mkdir()
    shutil.copyfile(FIXTURE, export_dir / "export.json")
    out = work / "meta.eln"
    import_export_zip(export_dir).export_eln(str(out), authors=_authors(), ontology_lookup=False)
    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        data = json.loads(z.read(name))
    return {"path": out, "graph": {e["@id"]: e for e in data["@graph"]}, "raw": data}


def _by_type(graph, wanted):
    out = []
    for node in graph.values():
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if wanted in types:
            out.append(node)
    return out


# --------------------------------------------------------------------- provenance

def test_create_action_records_what_wrote_the_crate(crate):
    """The export itself is provenance: what made this archive, and when."""
    actions = _by_type(crate["graph"], "CreateAction")
    assert len(actions) == 1, "exactly one export action"
    action = actions[0]
    assert action["object"] == {"@id": "./"}
    # Parsed, not merely truthy: "yes" satisfied the old assertion.
    datetime.fromisoformat(action["endTime"])
    assert action["actionStatus"] == {"@id": "http://schema.org/CompletedActionStatus"}

    instrument = crate["graph"][action["instrument"]["@id"]]
    assert instrument["@type"] == "SoftwareApplication"
    assert instrument["name"] == "chemotion-api"
    version = instrument.get("version")
    assert version and version != "unknown", \
        "a crate must name the version that wrote it; 'unknown' is what you get outside an install"
    assert re.match(r"^\d+\.\d+", version), f"expected a real version, got {version!r}"


def test_sd_publisher_is_an_organization_not_the_software(crate):
    """sdPublisher names who published the crate; the software goes on the CreateAction."""
    publisher = crate["graph"]["ro-crate-metadata.json"]["sdPublisher"]
    node = crate["graph"][publisher["@id"]]
    assert node["@type"] == "Organization"
    assert node["@id"].startswith("https://ror.org/"), "a ROR-identified organization"


def test_producer_still_detected_after_moving_the_marker(crate):
    """import_eln must still recognise our own crates now the marker lives on the CreateAction."""
    from chemotion_api.offline.eln_reader import import_eln
    parsed = import_eln(crate["path"])
    assert parsed.is_chemotion_api, "own-crate detection must survive the sdPublisher change"


# --------------------------------------------------------------------- identity

def test_root_carries_the_collection_id_as_its_identifier(crate):
    """It must be the collection's own id, so a re-export is recognisably the same collection."""
    identifier = crate["graph"]["./"].get("identifier")
    assert identifier and identifier.strip(), "the root must carry an identifier"
    assert identifier.isdigit(), f"expected the collection id, got {identifier!r}"


def test_elements_carry_identifier_and_genre(crate):
    datasets = [n for n in _by_type(crate["graph"], "Dataset") if n["@id"] != "./"]
    assert datasets, "the fixture has at least one element"
    for node in datasets:
        assert node.get("identifier"), f"{node['@id']} has no identifier"
        assert node.get("genre"), f"{node['@id']} does not say what kind of record it is"


def test_title_is_not_duplicated_across_two_vocabularies(crate):
    """We mirror chem-dcat-ap's title into schema.org `name`; carrying both is just noise."""
    for node in _by_type(crate["graph"], "Dataset"):
        if node.get("name"):
            assert node.get("dct:title") != node["name"]
            assert node.get("title") != node["name"]


# --------------------------------------------------------------------- files

def test_every_described_file_is_present_and_matches_its_checksum(crate):
    """The invariant, asserted over whatever the crate does describe.

    Stated this way on purpose: a crate must never describe a file it does not have. The mini
    fixture carries no attachment *bytes* (only their metadata), so it legitimately produces no
    File nodes at all — an earlier version of this test asserted one was present, which passed
    only because the exporter was describing a file whose download had failed.
    """
    with zipfile.ZipFile(crate["path"]) as z:
        members = {n.split("/", 1)[1]: n for n in z.namelist() if "/" in n}
        for node in _by_type(crate["graph"], "File"):
            relative = node["@id"].lstrip("./")
            assert relative in members, f"{node['@id']} is described but not in the archive"
            assert node.get("sha256"), f"{node['@id']} is described without a checksum"
            assert node["sha256"] == hashlib.sha256(z.read(members[relative])).hexdigest(), \
                f"{node['@id']}'s checksum does not match its stored bytes"


def test_a_file_whose_bytes_are_unavailable_is_not_described(crate):
    """The mini fixture's attachment has metadata but no bytes, so nothing may claim it exists."""
    described = {n["@id"] for n in _by_type(crate["graph"], "File")}
    with zipfile.ZipFile(crate["path"]) as z:
        stored = {n.split("/", 1)[1] for n in z.namelist() if "/" in n}
    for file_id in described:
        assert file_id.lstrip("./") in stored
    assert not described, "this fixture has no attachment bytes, so it should describe no files"


def test_every_key_in_the_graph_is_defined_by_the_context(crate):
    """An absolute IRI used as a key that the context does not map is a REQUIRED violation.

    `ro-crate-1.2_3.1` rejects the whole crate for it, and this is exactly how our chem-dcat-ap
    predicates (`qudt:unit`, `sio:SIO_000008`, …) used to leave the exporter — the RO-Crate
    context does not define them, so they survived compaction as bare IRIs. The declared
    namespace prefixes are what make them compact IRIs instead.
    """
    offenders = {key for node in crate["raw"]["@graph"] for key in node
                 if key.startswith(("http://", "https://"))}
    assert not offenders, f"these keys are not mapped by the @context: {sorted(offenders)}"


def test_the_context_declares_the_chem_dcat_ap_namespaces(crate):
    """`sha256` is no longer defined locally — RO-Crate 1.2's own context carries it, where 1.1's
    did not. What we still have to declare are the vocabularies chem-dcat-ap uses as keys."""
    context = crate["raw"]["@context"]
    assert isinstance(context, list)
    assert context[0] == "https://w3id.org/ro/crate/1.2/context"
    declared = {k for entry in context if isinstance(entry, dict) for k in entry}
    assert {"qudt", "sio", "obo", "adms", "skos"} <= declared


def test_the_root_declares_both_profiles(crate):
    """`tests/checks/versions.py` upstream reads the ELN version from the root Dataset's
    `conformsTo` and nowhere else; a crate declaring it only on the descriptor reads as plain
    RO-Crate. Both profiles must also exist as entities in the graph."""
    conforms = crate["graph"]["./"]["conformsTo"]
    ids = [ref["@id"] for ref in conforms]
    assert ids == ["https://w3id.org/ro/crate/1.2",
                   "https://purl.archive.org/purl/elnconsortium/eln-spec/1.2+20260923"]
    for profile_id in ids:
        node = crate["graph"][profile_id]
        assert "Profile" in node["@type"] and node.get("name")


# --------------------------------------------------------------------- timestamps

def test_offline_export_omits_timestamps_and_says_so(tmp_path, caplog):
    """A Chemotion export dump carries no created_at/updated_at, so neither can the crate.

    The point of this test is the *notice*: silence would leave a reader unable to tell a source
    limitation from data that genuinely has no dates.
    """
    import logging

    from chemotion_api.offline import import_export_zip
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    shutil.copyfile(FIXTURE, export_dir / "export.json")
    out = tmp_path / "undated.eln"
    with caplog.at_level(logging.INFO):
        import_export_zip(export_dir).export_eln(str(out), authors=_authors(), ontology_lookup=False)

    assert "carry no timestamps" in caplog.text
    assert "export from a live server" in caplog.text.lower()

    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        graph = json.loads(z.read(name))["@graph"]
    elements = [n for n in graph if n.get("@id", "").startswith("./") and n["@id"] != "./"]
    for node in elements:
        assert "dateCreated" not in node, "no timestamp may be invented when the source has none"


def test_timestamps_are_emitted_when_the_source_has_them():
    """The parse -> emit path itself, without needing a live server."""
    from datetime import datetime

    from chemotion_api.elements.abstract_element import AbstractElement
    assert AbstractElement._parse_timestamp(None) is None
    assert AbstractElement._parse_timestamp("") is None
    assert AbstractElement._parse_timestamp("not a date") is None
    parsed = AbstractElement._parse_timestamp("2026-09-16T12:00:00+00:00")
    assert isinstance(parsed, datetime)
    assert parsed.year == 2026


def test_keywords_are_never_emitted_as_an_array(crate):
    """A list here is a hard failure in TheELNFileFormat's schema.json *and* its checks.py.

    Guarded across the whole graph rather than one node, because the failure is silent locally —
    it only shows up when the consortium suite runs.
    """
    for node in crate["graph"].values():
        keywords = node.get("keywords")
        assert not isinstance(keywords, list), (
            f"{node['@id']} emits keywords as a list; it must be a delimited string"
        )


def test_element_keywords_come_from_labels_and_tags():
    """user_labels and tag both feed keywords, de-duplicated, as one comma-separated string."""
    from unittest.mock import MagicMock

    from chemotion_api.collection import annotate_element_metadata
    from chemotion_api.user import UserLabel

    elem = MagicMock()
    elem.id = 7
    elem.element_type = "Sample"
    elem.short_label = "S-7"
    elem.created_at = None
    elem.last_update = None
    elem.properties = {"tag": "urgent", "location": "Shelf B"}
    elem.user_labels_resolved = [UserLabel(id=1, title="danger"),
                                 UserLabel(id=2, title="urgent")]  # duplicate of the tag

    node: dict = {}
    annotate_element_metadata(elem, node)

    assert node["keywords"] == "danger, urgent", "de-duplicated, comma-separated, a single string"
    assert node["identifier"] == "S-7"
    assert node["genre"] == "Sample"


def test_unmapped_eln_fields_are_carried_as_property_values():
    """Fields chem-dcat-ap has no home for must not be silently dropped."""
    from unittest.mock import MagicMock

    from chemotion_api.collection import annotate_element_metadata

    elem = MagicMock()
    elem.id = 3
    elem.element_type = "Sample"
    elem.short_label = "S-3"
    elem.created_at = None
    elem.last_update = None
    elem.user_labels_resolved = []
    elem.properties = {"location": "Shelf B", "melting_point": "58", "external_label": "",
                       "boiling_point": None}

    node: dict = {}
    annotate_element_metadata(elem, node)

    carried = {pv["propertyID"]: pv["value"] for pv in node["variableMeasured"]}
    assert carried == {"chemotion:location": "Shelf B", "chemotion:melting_point": "58"}, \
        "empty and absent fields are omitted, present ones are kept"
    for pv in node["variableMeasured"]:
        assert pv["@type"] == "PropertyValue"


def test_elements_without_timestamps_are_recorded_for_the_manifest():
    """The caller needs to know which elements had no dates, to report it once."""
    from unittest.mock import MagicMock

    from chemotion_api.collection import annotate_element_metadata

    elem = MagicMock()
    elem.id = 11
    elem.element_type = "Sample"
    elem.short_label = "S-11"
    elem.created_at = None
    elem.last_update = None
    elem.user_labels_resolved = []
    elem.properties = {}

    undated: list = []
    node: dict = {}
    annotate_element_metadata(elem, node, undated)

    assert undated == ["11"]
    assert "dateCreated" not in node and "dateModified" not in node


# --------------------------------------------------------------- the source ELN

def test_crate_records_which_eln_it_came_from(crate):
    """A crate must say which notebook produced its data, not just which client wrote it."""
    based_on = crate["graph"]["./"].get("isBasedOn")
    assert based_on, "the root must point at the ELN the data came from"
    node = crate["graph"][based_on["@id"]]
    # Offline there is no /about, so no version can be stated — and RO-Crate 1.2 makes `version`
    # REQUIRED on a SoftwareApplication. Rather than invent one, the node stays a CreativeWork:
    # it still says where the data came from without claiming to identify a build.
    assert node["@type"] == "CreativeWork"
    assert "version" not in node
    assert node["name"] == "Chemotion ELN"
    assert node["url"] == node["@id"]


def test_offline_crate_names_the_sentinel_and_invents_no_version(crate):
    """There is no server offline, so the host is the reserved sentinel and the version is absent.

    `.invalid` is the RFC 2606 reserved TLD — it can never resolve, which is exactly the point:
    it states "no server" instead of pointing somewhere misleading.
    """
    from chemotion_api.eln_producer import OFFLINE_HOST

    node = crate["graph"][crate["graph"]["./"]["isBasedOn"]["@id"]]
    assert node["@id"] == OFFLINE_HOST
    assert "version" not in node, "a version must never be invented when there is no server to ask"


def test_reader_exposes_the_source_eln(crate):
    from chemotion_api.offline.eln_reader import import_eln

    with import_eln(crate["path"]) as parsed:
        assert parsed.source_eln is not None
        assert parsed.source_eln["name"] == "Chemotion ELN"


def test_metadata_model_versions_are_recorded_separately_from_the_client_version(crate):
    """chem-dcat-ap and dcat-ap-plus are pre-1.0 and moving; a reader needs to know which."""
    producer = crate["graph"]["#chemotion-api"]
    assert producer["version"], "the client's own version"
    requirements = producer.get("softwareRequirements", "")
    assert "chem_dcat_ap" in requirements
    assert requirements != producer["version"], "the two versions must not be conflated"


# --------------------------------------------------------- version string parsing

def test_full_version_string_survives_the_html_of_the_about_page():
    """`/about` is HTML. The build suffix is the only thing separating two rolling builds, and an
    unbounded capture swallows the closing tag into the recorded version."""
    from unittest.mock import MagicMock

    from chemotion_api.schema_manager import SchemaManager

    res = MagicMock(status_code=200)
    res.text = "<h4>Version: v4.0.0-rc-20260902</h4>\n<h4>Current revision: 28903b17fc2f</h4>"
    manager = SchemaManager(res)

    assert manager.version_string == "v4.0.0-rc-20260902", "no markup in the recorded version"
    assert manager.revision == "28903b17fc2f"
    assert manager.version == "4.0.0", "the dotted version stays clean for the guard"
    assert manager.model_type_version == "4.0", "element @types stay coarse across rc rebuilds"


def test_a_release_without_a_suffix_or_revision_still_parses():
    from unittest.mock import MagicMock

    from chemotion_api.schema_manager import SchemaManager

    res = MagicMock(status_code=200)
    res.text = "Version: v4.0.0"
    manager = SchemaManager(res)
    assert manager.version_string == "v4.0.0"
    assert manager.revision is None


def test_disclose_host_false_withholds_the_hostname_but_keeps_the_version(tmp_path, caplog):
    """An archive leaving the institution should say what produced it, not where it runs."""
    import logging

    from chemotion_api.eln_producer import OFFLINE_HOST
    from chemotion_api.offline import import_export_zip

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    shutil.copyfile(FIXTURE, export_dir / "export.json")
    collection = import_export_zip(export_dir)

    # Stand in for a live session: a real hostname and a server version to record.
    collection._session.host_url = "https://eln.internal.example.org"
    collection._session.schema_manager.version_string = "v4.0.0-rc-20260902"

    out = tmp_path / "withheld.eln"
    with caplog.at_level(logging.INFO):
        collection.export_eln(str(out), authors=_authors(), ontology_lookup=False,
                              disclose_host=False)

    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        graph = {e["@id"]: e for e in json.loads(z.read(name))["@graph"]}

    node = graph[graph["./"]["isBasedOn"]["@id"]]
    assert node["@id"] == OFFLINE_HOST, "the real hostname must not reach the crate"
    assert node["version"] == "v4.0.0-rc-20260902", "the version is still recorded"
    assert "eln.internal.example.org" not in json.dumps(graph), "no trace of the host anywhere"
    assert "withholding the ELN hostname" in caplog.text, "the omission is stated, not silent"


def test_a_missing_offline_attachment_explains_itself(tmp_path):
    """The error must name the problem, not the shim's missing attribute.

    `Attachment.load_file`/`iter_file` build their error from `res.text`. When the offline
    response had no `text`, a missing attachment surfaced as an AttributeError about
    `_OfflineResponse` — which tells a user nothing and, under strict=True, is what aborted the
    export.
    """
    from chemotion_api.offline import import_export_zip

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    shutil.copyfile(FIXTURE, export_dir / "export.json")

    with pytest.raises(RuntimeError) as excinfo:
        import_export_zip(export_dir).export_eln(
            str(tmp_path / "strict.eln"), authors=_authors(), ontology_lookup=False, strict=True)

    message = str(excinfo.value)
    assert "not in the export archive" in message, message
    assert "has no attribute" not in message, "the shim's internals must not leak into the error"


def test_mapping_values_never_reach_the_crate_as_repr_strings():
    """A container must be skipped, not stringified.

    Chemotion's PropertyDict is a MutableMapping but NOT a dict subclass, so an
    `isinstance(value, dict)` guard misses it and `str()` then writes
    `<PropertyDict object at 0x...>` — a live memory address — into the crate. This was reaching
    real exports via the sample `stereo` field.
    """
    from unittest.mock import MagicMock

    from chemotion_api.collection import annotate_element_metadata
    from chemotion_api.utils import PropertyDict

    elem = MagicMock()
    elem.id = 5
    elem.element_type = "Sample"
    elem.short_label = "S-5"
    elem.created_at = None
    elem.last_update = None
    elem.user_labels_resolved = []
    elem.properties = {
        "location": "Shelf B",                                   # a plain value: kept
        "solvent": PropertyDict(lambda *a: None, {"a": 1}),       # a mapping: skipped
        "purification": ["Extraction"],                           # a list: skipped
    }

    node: dict = {}
    annotate_element_metadata(elem, node)

    rendered = json.dumps(node)
    assert "object at 0x" not in rendered, "a repr with a memory address must never be emitted"
    carried = {pv["propertyID"] for pv in node.get("variableMeasured", [])}
    assert carried == {"chemotion:location"}


# ------------------------------------------------------- integrity of what the crate claims

def test_a_partly_downloaded_attachment_is_not_described_as_complete(tmp_path):
    """A stream that dies mid-file leaves a truncated member in the archive.

    Left alone, the crate would keep a File node advertising the server's contentSize with no
    checksum — a consumer would read silently corrupt bytes with nothing to detect it. The node
    (and any hasPart reference to it) must be withdrawn instead.
    """
    from chemotion_api.collection import _write_crate_zip_inner

    class DyingAttachment(dict):
        def iter_file(self):
            yield b"A" * 100
            raise OSError("connection dropped mid-stream")

        def __hash__(self):
            return id(self)

    metadata = {"@graph": [
        {"@id": "./", "@type": "Dataset", "hasPart": [{"@id": "./samples/S_1/big.dat"}]},
        {"@id": "./samples/S_1/big.dat", "@type": "File", "name": "big.dat",
         "contentSize": "5000"},
    ]}
    out = tmp_path / "partial.eln"
    skipped: list = []
    _write_crate_zip_inner(
        str(out), "partial", metadata,
        {("sample", 1): [(DyingAttachment(filename="big.dat"), "big.dat")]},
        {("sample", 1): "./samples/S_1/"}, skipped, None, str, False)

    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        graph = json.loads(z.read(name))["@graph"]

    assert not [n for n in graph if n.get("@type") == "File"], \
        "a file whose bytes did not arrive must not be described"
    root = next(n for n in graph if n["@id"] == "./")
    assert root["hasPart"] == [], "and nothing may still reference it"
    assert any(s["kind"] == "attachment" for s in skipped), "the failure is still recorded"


def test_a_python_repr_never_reaches_the_crate(caplog):
    """Final guard against a bug this exporter has produced three times.

    A server value written out with str() without its shape being checked put
    `<PropertyDict object at 0x...>` — a live memory address — into a real export. No repr is ever
    valid crate content, so it is dropped and reported loudly rather than published.
    """
    import logging

    from chemotion_api.collection import flatten_crate_graph
    from chemotion_api.utils import PropertyDict

    metadata = {"@graph": [
        {"@id": "./", "@type": "Dataset", "name": "fine"},
        {"@id": "#pv", "@type": "PropertyValue", "propertyID": "chemotion:stereo",
         "value": str(PropertyDict(lambda *a: None, {"a": 1}))},
        {"@id": "#innocent", "@type": "PropertyValue", "value": "<a b c> angle brackets are fine"},
    ]}
    with caplog.at_level(logging.ERROR):
        flatten_crate_graph(metadata)
    nodes = {n["@id"]: n for n in metadata["@graph"]}

    assert "value" not in nodes["#pv"], "the repr must be dropped"
    assert nodes["#innocent"]["value"].startswith("<a b c>"), "ordinary angle brackets are kept"
    assert "not data" in caplog.text, "and it must be reported as the exporter bug it is"


# ------------------------------------------- the checksum path, with bytes actually present

#: The fixture declares `filesize: 1234` for this attachment. The real payload below is much
#: shorter on purpose: a crate must describe the bytes it stored, not the size a server recorded.
_ATTACHMENT_BYTES = b"##TITLE=probe\n##END=\n"


@pytest.fixture(scope="module")
def crate_with_payload(tmp_path_factory):
    """Like `crate`, but with the attachment's bytes actually present.

    The offline reader locates payloads at `attachments/<identifier>.<ext>` beside `export.json`,
    so writing that file is what makes the download succeed — and therefore what exercises the
    sha256 computation at all. Without it the digest code has no coverage anywhere in the suite.
    """
    from chemotion_api.offline import import_export_zip
    work = tmp_path_factory.mktemp("crate_payload")
    export_dir = work / "export"
    (export_dir / "attachments").mkdir(parents=True)
    shutil.copyfile(FIXTURE, export_dir / "export.json")
    (export_dir / "attachments" / "att-1-uuid.jdx").write_bytes(_ATTACHMENT_BYTES)

    out = work / "payload.eln"
    import_export_zip(export_dir).export_eln(str(out), authors=_authors(), ontology_lookup=False)
    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        data = json.loads(z.read(name))
    return {"path": out, "graph": {e["@id"]: e for e in data["@graph"]}}


def test_sha256_is_computed_from_the_bytes_that_were_stored(crate_with_payload):
    files = _by_type(crate_with_payload["graph"], "File")
    assert len(files) == 1, "the payload fixture describes exactly one file"
    node = files[0]
    assert node["sha256"] == hashlib.sha256(_ATTACHMENT_BYTES).hexdigest()

    with zipfile.ZipFile(crate_with_payload["path"]) as z:
        member = next(n for n in z.namelist() if n.endswith("att-1-uuid.jdx")
                      or n.endswith(node["@id"].lstrip("./")))
        assert z.read(member) == _ATTACHMENT_BYTES


def test_content_size_describes_the_stored_bytes_not_the_recorded_filesize(crate_with_payload):
    """The fixture claims filesize 1234; the real payload is 20 bytes.

    A size copied from stale server metadata sitting next to a correct checksum is worse than no
    size at all — it is a contradiction a consumer cannot resolve.
    """
    node = _by_type(crate_with_payload["graph"], "File")[0]
    assert node["contentSize"] == str(len(_ATTACHMENT_BYTES))
    assert node["contentSize"] != "1234", "must not echo the server's recorded filesize"


# ------------------------------------------------ values that arrive in awkward server shapes

def test_narrative_fields_survive_being_quill_deltas():
    """Chemotion stores descriptions and observations as Quill deltas, not strings.

    An `isinstance(str)` guard therefore skipped exactly the elements whose narrative matters —
    a reaction's observation is never a plain string.
    """
    from unittest.mock import MagicMock

    from chemotion_api.collection import annotate_element_metadata

    elem = MagicMock(id=1, element_type="Reaction", short_label="R-1",
                     created_at=None, last_update=None, user_labels_resolved=[])
    elem.properties = {"observation": {"ops": [{"insert": "Turned deep red after 10 min."}]}}

    node: dict = {}
    annotate_element_metadata(elem, node)
    assert node["text"] == "Turned deep red after 10 min."


def test_the_unset_melting_point_every_sample_carries_is_not_emitted():
    """The ELN sets both points to an infinite range on create, serialised as "(,)".

    Emitting it would put two meaningless PropertyValues on every sample in every crate.
    """
    from unittest.mock import MagicMock

    from chemotion_api.collection import annotate_element_metadata

    elem = MagicMock(id=2, element_type="Sample", short_label="S-2",
                     created_at=None, last_update=None, user_labels_resolved=[])
    elem.properties = {"melting_point": "(,)", "boiling_point": "-114...-114"}

    node: dict = {}
    annotate_element_metadata(elem, node)
    carried = {pv["propertyID"]: pv["value"] for pv in node.get("variableMeasured", [])}

    assert "chemotion:melting_point" not in carried, '"(,)" means unset and must be dropped'
    assert carried["chemotion:boiling_point"] == "-114", \
        "a degenerate range is one value written twice, not a range"


@pytest.mark.parametrize(("raw", "expected"), [
    ("(,)", None), ("", None), ("...", None),
    ("-114...-114", "-114"), ("10...20", "10-20"), ("58", "58"),
])
def test_range_normalisation(raw, expected):
    from chemotion_api.utils import normalise_range_value
    assert normalise_range_value(raw) == expected


def test_fields_that_arrive_as_containers_are_not_listed_as_if_they_worked():
    """solvent/purification (lists) and vessel_size (mapping) can never pass the container guard.

    Listing them would be dead code masquerading as a curated choice.
    """
    from chemotion_api.collection import _ELN_EXTRA_FIELDS
    for dead in ("solvent", "purification", "vessel_size", "stereo", "xref"):
        assert dead not in _ELN_EXTRA_FIELDS, f"{dead} can never fire; listing it is misleading"


# ----------------------------------------------------- declaring what the export left out

def test_a_partial_crate_says_so(crate):
    """A crate that omitted things must not read exactly like a complete one.

    The mini fixture's attachment has no bytes and its elements have no timestamps, so this
    export is genuinely partial — and must say which kinds of thing were left out.
    """
    manifest = crate["graph"].get("#export-manifest")
    assert manifest is not None, "a partial crate must declare its omissions"
    assert manifest["@type"] == "CreativeWork"
    assert "incomplete" in manifest["description"].lower()
    assert "attachment" in manifest["description"]

    root = crate["graph"]["./"]
    assert {"@id": "#export-manifest"} in root["mentions"], \
        "the root must point at it, or a reader has no way to find it"


def test_each_omission_is_machine_readable(crate):
    """Prose for a human; a PropertyValue per kind so a consumer can act on it."""
    measured = crate["graph"]["#export-manifest"]["variableMeasured"]
    assert measured, "the manifest must carry structured entries, not only prose"
    for ref in measured:
        node = crate["graph"][ref["@id"]]
        assert node["@type"] == "PropertyValue"
        assert node["propertyID"].startswith("chemotion:omitted/")
        assert node["value"].isdigit(), "a count, so a consumer can tell how much is missing"
        assert node["description"], "and why"


def test_the_manifest_never_carries_raw_error_text():
    """Exception text is unstable across runs and embeds the server hostname on a failed download.

    Declaring omissions must not become a channel that defeats disclose_host=False.
    """
    from chemotion_api.collection import build_skipped_manifest

    nodes = build_skipped_manifest([
        {"kind": "attachment", "stage": "download", "filename": "x.jdx",
         "error": "HTTPSConnectionPool(host='eln.internal.example.org', port=443): Max retries"},
    ])
    rendered = json.dumps(nodes)
    assert "eln.internal.example.org" not in rendered, "a hostname must never reach the crate here"
    assert "HTTPSConnectionPool" not in rendered, "nor raw exception text"
    assert "could not be retrieved" in rendered, "but the reason must still be stated"


def test_declare_skipped_false_leaves_the_crate_bare(tmp_path):
    from chemotion_api.offline import import_export_zip

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    shutil.copyfile(FIXTURE, export_dir / "export.json")
    out = tmp_path / "bare.eln"
    import_export_zip(export_dir).export_eln(str(out), authors=_authors(), ontology_lookup=False,
                                             declare_skipped=False)
    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        graph = {e["@id"]: e for e in json.loads(z.read(name))["@graph"]}
    assert "#export-manifest" not in graph
    # `mentions` still carries the crate's collection entities; what must be gone is the
    # manifest reference the root would otherwise point at.
    assert "#export-manifest" not in [r["@id"] for r in graph["./"].get("mentions", [])]


def test_a_complete_export_declares_nothing():
    """No manifest when nothing was omitted — an empty one would be noise."""
    from chemotion_api.collection import build_skipped_manifest
    assert build_skipped_manifest([]) == []


def test_real_sample_melting_point_reaches_the_crate():
    """`_parse_properties` splits the Ruby range into *_lowerbound/*_upperbound, so
    `props.get("melting_point")` was always None on a real element — the melting and boiling
    points were silently absent from every crate, and `normalise_range_value` was dead code."""
    from chemotion_api.collection import annotate_element_metadata
    from chemotion_api.offline import import_export_zip

    col = import_export_zip(str(FIXTURE))
    sample = col.get_reactions()[0].properties["starting_materials"][0]
    assert "melting_point" not in sample.properties        # the premise
    assert sample.properties["melting_point_lowerbound"] == -114

    node: dict = {}
    annotate_element_metadata(sample, node)
    carried = {pv["propertyID"]: pv["value"] for pv in node.get("variableMeasured", [])}
    assert carried["chemotion:melting_point"] == "-114"
    assert carried["chemotion:boiling_point"] == "78"


def test_sample_role_in_reaction_reaches_the_crate():
    """`role` is an attribute, not a property key, so `props.get("role")` was always None."""
    from chemotion_api.collection import annotate_element_metadata
    from chemotion_api.offline import import_export_zip

    col = import_export_zip(str(FIXTURE))
    sample = col.get_reactions()[0].properties["starting_materials"][0]
    assert "role" not in sample.properties                 # the premise

    node: dict = {}
    annotate_element_metadata(sample, node)
    carried = {pv["propertyID"]: pv["value"] for pv in node.get("variableMeasured", [])}
    assert carried["chemotion:role"] == "starting_materials"


def test_a_bound_pair_that_is_a_real_range_is_rendered_as_one():
    from unittest.mock import MagicMock

    from chemotion_api.collection import annotate_element_metadata

    elem = MagicMock(id=9, element_type="Sample", short_label="S-9",
                     created_at=None, last_update=None, user_labels_resolved=[])
    elem.json_data = {}
    elem.properties = {"melting_point_lowerbound": 10, "melting_point_upperbound": 20}
    node: dict = {}
    annotate_element_metadata(elem, node)
    carried = {pv["propertyID"]: pv["value"] for pv in node.get("variableMeasured", [])}
    assert carried["chemotion:melting_point"] == "10-20"
