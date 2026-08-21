"""Reading a ``.eln`` RO-Crate back into Python objects (chemotion_api.offline.eln_reader).

Most tests use a small hand-built crate; the final test round-trips the mini export fixture
through the real exporter (marked ``heavy`` like the other full-export tests).
"""
import json
import os
import zipfile

import pytest

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "..", "fixtures")
MINI = os.path.join(FIXTURES, "mini_export.json")

ORCID = "https://orcid.org/0000-0002-1825-0097"
ROR = "https://ror.org/04t3en479"

METADATA = {
    "@context": "https://w3id.org/ro/crate/1.1/context",
    "@graph": [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "dateCreated": "2026-07-03T12:00:00",
            "sdPublisher": {"@id": "#chemotion-api"},
        },
        {"@id": "#chemotion-api", "@type": "SoftwareApplication",
         "name": "chemotion-api", "version": "211.0.1"},
        {
            "@id": "./",
            "@type": "Dataset",
            "name": "My Project",
            "author": {"@id": ORCID},
            "hasPart": [{"@id": "./samples/Water_42/"}, {"@id": "./reactions/R1_7/"}],
        },
        {
            # kind via the ontology placeholder written by export_eln
            "@id": "./samples/Water_42/",
            "@type": "Dataset",
            "name": "Water",
            "variableMeasured": [
                {"@type": "PropertyValue", "propertyID": "chemotion:elementType", "value": "sample"},
            ],
            "hasPart": [{"@id": "./samples/Water_42/spectrum.txt"}],
        },
        {
            # kind only inferable from the crate folder (reactions/)
            "@id": "./reactions/R1_7/",
            "@type": ["Dataset", "https://example.org/SomeOntologyClass"],
            "name": "R1",
        },
        {
            "@id": "./samples/Water_42/spectrum.txt",
            "@type": "File",
            "name": "spectrum.txt",
            "encodingFormat": "text/plain",
            "contentSize": "9",
        },
        {"@id": ORCID, "@type": "Person", "name": "Ada Lovelace",
         "identifier": ORCID, "email": "ada@example.org", "affiliation": {"@id": ROR}},
        {"@id": ROR, "@type": "Organization", "name": "KIT", "identifier": ROR},
    ],
}


def _crate_zip(tmp_path, metadata=METADATA, with_payload=True):
    """Write a minimal .eln ZIP (single root folder, as per TheELNFileFormat)."""
    path = tmp_path / "mini.eln"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mini.eln/ro-crate-metadata.json", json.dumps(metadata))
        if with_payload:
            z.writestr("mini.eln/samples/Water_42/spectrum.txt", b"1.0 2.0\n")
    return path


def test_reads_crate_structure_from_zip(tmp_path):
    from chemotion_api.offline import import_eln

    with import_eln(_crate_zip(tmp_path)) as crate:
        assert crate.root.name == "My Project"
        assert crate.date_created == "2026-07-03T12:00:00"
        assert {ds.id for ds in crate.datasets} == {"./samples/Water_42/", "./reactions/R1_7/"}
        # root's hasPart navigation resolves the same two datasets
        assert {ds.id for ds in crate.root.datasets} == {ds.id for ds in crate.datasets}


def test_kind_detection_placeholder_and_path(tmp_path):
    from chemotion_api.offline import import_eln

    with import_eln(_crate_zip(tmp_path)) as crate:
        by_id = {ds.id: ds for ds in crate.elements}
        assert by_id["./samples/Water_42/"].kind == "sample"      # from the placeholder
        assert by_id["./reactions/R1_7/"].kind == "reaction"      # from the folder name
        assert by_id["./samples/Water_42/"].source_id == 42
        assert by_id["./reactions/R1_7/"].source_id == 7
        assert "https://example.org/SomeOntologyClass" in by_id["./reactions/R1_7/"].types


def test_files_and_payload_access(tmp_path):
    from chemotion_api.offline import import_eln

    with import_eln(_crate_zip(tmp_path)) as crate:
        sample = crate.get_dataset("./samples/Water_42/")
        (f,) = sample.files
        assert (f.name, f.encoding_format, f.content_size) == ("spectrum.txt", "text/plain", 9)
        assert f.read() == b"1.0 2.0\n"
        out = f.extract(tmp_path / "out")
        assert out.read_bytes() == b"1.0 2.0\n"
        assert crate.has_file(f.id)
        assert [x.id for x in crate.files] == [f.id]


def test_metadata_only_file_is_reported_missing(tmp_path):
    """File nodes may outlive their payload (export skips failed downloads but keeps metadata)."""
    from chemotion_api.offline import import_eln

    with import_eln(_crate_zip(tmp_path, with_payload=False)) as crate:
        (f,) = crate.files
        assert not crate.has_file(f.id)
        with pytest.raises(FileNotFoundError):
            f.read()


def test_authors_reconstructed(tmp_path):
    from chemotion_api.offline import import_eln

    with import_eln(_crate_zip(tmp_path)) as crate:
        (author,) = crate.authors
        assert author.name == "Ada Lovelace"
        assert author.orcid_url == ORCID
        assert author.email == "ada@example.org"
        assert [(a.name, a.ror_url) for a in author.affiliations] == [("KIT", ROR)]


def test_reads_extracted_directory(tmp_path):
    from chemotion_api.offline import import_eln

    d = tmp_path / "crate" / "mini.eln"
    (d / "samples" / "Water_42").mkdir(parents=True)
    (d / "ro-crate-metadata.json").write_text(json.dumps(METADATA), encoding="utf-8")
    (d / "samples" / "Water_42" / "spectrum.txt").write_bytes(b"1.0 2.0\n")
    with import_eln(tmp_path / "crate") as crate:
        assert crate.root.name == "My Project"
        assert crate.get_dataset("./samples/Water_42/").files[0].read() == b"1.0 2.0\n"


def test_zip_slip_ids_are_rejected(tmp_path):
    from chemotion_api.offline import import_eln

    with import_eln(_crate_zip(tmp_path)) as crate:
        for evil in ("../outside.txt", "samples/../../outside.txt", "/etc/passwd"):
            assert not crate.has_file(evil)
            with pytest.raises(ValueError, match="unsafe crate path"):
                crate.read_file(evil)


def test_producer_marker_identifies_our_crates(tmp_path):
    from chemotion_api.offline import import_eln

    with import_eln(_crate_zip(tmp_path)) as crate:
        assert crate.is_chemotion_api
        assert crate.producer["name"] == "chemotion-api"
        assert crate.producer["version"]


def test_foreign_crates_are_rejected_by_default(tmp_path):
    """.eln files from other ELNs are a deferred feature: refuse unless allow_foreign=True."""
    import copy
    from chemotion_api.offline import import_eln

    foreign = copy.deepcopy(METADATA)
    for node in foreign["@graph"]:
        if node["@id"] == "#chemotion-api":
            node["name"] = "eLabFTW"
    path = _crate_zip(tmp_path, metadata=foreign)
    with pytest.raises(ValueError, match="eLabFTW.*not supported yet"):
        import_eln(path)
    # escape hatch: best-effort generic parsing
    with import_eln(path, allow_foreign=True) as crate:
        assert not crate.is_chemotion_api
        assert crate.root.name == "My Project"

    # no producer declared at all -> also rejected
    unmarked = copy.deepcopy(METADATA)
    unmarked["@graph"][0].pop("sdPublisher")
    with pytest.raises(ValueError, match="unknown producer"):
        import_eln(_crate_zip(tmp_path, metadata=unmarked))


def test_rejects_non_crates(tmp_path):
    from chemotion_api.offline import import_eln

    not_zip = tmp_path / "plain.eln"
    not_zip.write_text("not a zip")
    with pytest.raises(ValueError, match="neither"):
        import_eln(not_zip)

    no_meta = tmp_path / "empty.eln"
    with zipfile.ZipFile(no_meta, "w") as z:
        z.writestr("empty.eln/readme.txt", "hi")
    with pytest.raises(ValueError, match="ro-crate-metadata.json"):
        import_eln(no_meta)


@pytest.mark.heavy
def test_roundtrip_export_then_import(tmp_path):
    """export_eln → import_eln: structure, kinds, and authors survive the round trip."""
    from chemotion_api import Author, AuthorAffiliation, Instance

    d = tmp_path / "export"
    d.mkdir()
    (d / "export.json").write_text(open(MINI).read(), encoding="utf-8")
    out = str(tmp_path / "roundtrip.eln")
    authors = [Author(name="Test Author", orcid=ORCID,
                      affiliations=[AuthorAffiliation(name="KIT", ror=ROR)])]
    Instance.import_export_zip(d).export_eln(out, ontology_lookup=False, authors=authors)

    with Instance.import_eln(out) as crate:
        assert crate.is_chemotion_api             # producer marker written by export_eln
        assert crate.producer["@type"] == "SoftwareApplication"
        assert crate.root.node.get("publisher") == {"@id": ROR}
        assert crate.root.name  # the collection label from the export dump
        kinds = [ds.kind for ds in crate.elements]
        assert kinds.count("reaction") == 1
        (author,) = crate.authors
        assert (author.name, author.orcid_url) == ("Test Author", ORCID)
        assert author.affiliations[0].ror_url == ROR
        # every File node is reachable from some element's hasPart
        listed = {f.id for ds in crate.elements for f in ds.files}
        assert {f.id for f in crate.files} == listed
