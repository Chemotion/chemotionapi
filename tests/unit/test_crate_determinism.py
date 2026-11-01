"""The archive describes everything it contains, and regenerating it does not churn ids."""
import json
import re
import zipfile

import pytest

pytestmark = pytest.mark.heavy

BLANK_ID = re.compile(r"^#[a-z0-9_]+-\d+$")


def _export(tmp_path, name="c.eln"):
    """Export the committed fixture dump offline — no server, no network."""
    import shutil
    from chemotion_api import Author, AuthorAffiliation
    from chemotion_api.offline import import_export_zip

    fixture = __import__("pathlib").Path(__file__).resolve().parents[1] / "fixtures" / "mini_export.json"
    export_dir = tmp_path / f"dump-{name}"
    export_dir.mkdir()
    shutil.copyfile(fixture, export_dir / "export.json")
    out = tmp_path / name
    import_export_zip(export_dir).export_eln(
        str(out),
        authors=[Author(name="T", orcid="0000-0002-1825-0097",
                        affiliations=[AuthorAffiliation(
                            name="O", ror="https://ror.org/04t3en479")])],
        ontology_lookup=False,
    )
    return out


def _graph(path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        return json.loads(z.read(name))["@graph"]


def test_every_archive_member_is_described(tmp_path):
    """Regression: a failed download left its partial bytes in the ZIP with no File node.

    The fixture's attachment has no bytes in the dump, so this exercises exactly that path —
    the archive used to ship a 0-byte `.jdx` that nothing in the metadata described.
    """
    out = _export(tmp_path)
    graph = _graph(out)
    described = {n["@id"].lstrip("./") for n in graph if isinstance(n.get("@id"), str)}
    with zipfile.ZipFile(out) as z:
        members = [i.filename for i in z.infolist()
                   if not i.filename.endswith("/") and not i.filename.endswith(".json")]
    root = members[0].split("/", 1)[0] if members else ""
    for m in members:
        rel = m.split("/", 1)[1] if "/" in m else m
        assert rel in described, f"{m} is in the archive but nothing describes it"
    assert root or not members


def test_element_directories_survive_a_withdrawn_file(tmp_path):
    """Removing the only file in an element's folder must not remove the folder.

    RO-Crate requires every Dataset data entity to be present in the payload, so the directory
    entry has to stay even once its contents are withdrawn.
    """
    out = _export(tmp_path)
    graph = _graph(out)
    dataset_paths = {n["@id"] for n in graph
                     if n.get("@id", "").startswith("./") and n["@id"].endswith("/")
                     and "Dataset" in (n["@type"] if isinstance(n.get("@type"), list)
                                       else [n.get("@type")])}
    with zipfile.ZipFile(out) as z:
        entries = {i.filename for i in z.infolist()}
    for path in dataset_paths - {"./"}:
        rel = path.lstrip("./")
        assert any(e.endswith(rel) or f"/{rel}" in e for e in entries), \
            f"{path} is a Dataset data entity but has no payload directory"


def test_blank_node_ids_are_stable_across_exports(tmp_path):
    """Two exports of the same input must produce the same crate ids.

    The ids used to be numbered in rdflib's graph order, which is not deterministic, so a
    regenerated crate always diffed even when nothing had changed.
    """
    first = {n["@id"]: n for n in _graph(_export(tmp_path, "a.eln"))
             if isinstance(n.get("@id"), str) and BLANK_ID.match(n["@id"])}
    second = {n["@id"]: n for n in _graph(_export(tmp_path, "b.eln"))
              if isinstance(n.get("@id"), str) and BLANK_ID.match(n["@id"])}
    assert first, "the fixture produces blank nodes, so there is something to stabilise"
    assert set(first) == set(second), "the same input produced different crate ids"
    for key in first:
        assert first[key] == second[key], f"{key} describes something different on re-export"


def test_every_node_is_identical_across_exports(tmp_path):
    """Each entity describes the same thing on re-export, under the same id.

    This is the guarantee, and it is narrower than byte-identity on purpose: multi-valued
    *reference* arrays still come out of rdflib in arbitrary order, so two crates can differ in
    the order of a node's references while every node means the same thing. Ordering those is
    valid JSON-LD but reorders `conformsTo` and `author`, where sequence is read by people.
    """
    first = {n["@id"]: n for n in _graph(_export(tmp_path, "x.eln")) if "@id" in n}
    second = {n["@id"]: n for n in _graph(_export(tmp_path, "y.eln")) if "@id" in n}
    assert set(first) == set(second), "the same input produced a different set of entities"

    # The export's own clock is the one thing that *must* differ: the provenance CreateAction
    # records when it ran.
    TIMES = {"startTime", "endTime", "datePublished", "dateCreated", "dateModified"}

    def canon(node):
        return json.dumps({k: (sorted(v, key=str) if isinstance(v, list) else v)
                           for k, v in node.items() if k not in TIMES},
                          sort_keys=True, default=str)

    for key in first:
        assert canon(first[key]) == canon(second[key]), f"{key} differs between exports"


def test_type_arrays_are_ordered(tmp_path):
    for node in _graph(_export(tmp_path, "z.eln")):
        types = node.get("@type")
        if isinstance(types, list):
            assert types == sorted(types, key=str), f"{node.get('@id')} has unordered @type"
