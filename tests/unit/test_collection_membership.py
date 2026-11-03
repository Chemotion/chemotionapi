"""An element can belong to more than one collection, and the crate has to say so.

`build_element_index` derived an element's crate path from the collection it was reached
through and keyed one collection per element. An element in collections A *and* B was visited
twice under the same `(kind, id)` key, so the second traversal overwrote the first: the crate
asserted the element lived in whichever collection was walked last, and its membership in the
other was not merely unstated but *unrepresentable* — location was the only membership signal.

Collections are now contextual `Collection` entities and membership is a reference, so an
element is stored once at a collection-independent path and names every collection it is in.
"""
import json
import re
import zipfile

import pytest

from chemotion_api import Author, AuthorAffiliation
from chemotion_api.offline import import_eln

from tests.unit.test_offline_ingest import _bundle_data, _import


def _authors():
    return [Author(name="Fixture Author", orcid="0000-0002-1825-0097",
                   affiliations=[AuthorAffiliation(name="Example University",
                                                   ror="https://ror.org/05dxps055")])]


@pytest.fixture
def shared_crate(tmp_path):
    """A crate whose shared sample belongs to both "Child Col" and "Other Root".

    The sample is exported under its short_label ("MT-1"), not the dump's `name`."""
    root = _import(tmp_path, _bundle_data(second_root=True))
    out = str(tmp_path / "shared.eln")
    root.export_eln(out, ontology_lookup=False, authors=_authors())
    return out


def _graph(path):
    with zipfile.ZipFile(path) as z:
        meta = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        return json.loads(z.read(meta))["@graph"]


def _by_id(path):
    return {n["@id"]: n for n in _graph(path) if "@id" in n}


def _types(node):
    t = node.get("@type")
    return t if isinstance(t, list) else [t]


def test_an_element_in_two_collections_survives_a_round_trip(shared_crate):
    """The spine: export a shared element and read *both* memberships back out."""
    with import_eln(shared_crate) as crate:
        shared = next(e for e in crate.elements if e.kind == "sample")
        assert sorted(c.name for c in shared.collections) == ["Child Col", "Other Root"]


def test_the_shared_element_is_stored_exactly_once(shared_crate):
    """It was never duplicated — one membership was *lost*. Assert the count explicitly."""
    nodes = _by_id(shared_crate)
    samples = [i for i, n in nodes.items()
               if i.startswith("./samples/") and "Dataset" in _types(n)]
    assert len(samples) == 1
    root_parts = [r["@id"] for r in nodes["./"]["hasPart"]]
    assert root_parts.count(samples[0]) == 1


def test_haspart_and_ispartof_are_exact_inverses(shared_crate):
    """Two directions built from one index; a drift between them is a silent lie about data."""
    nodes = _by_id(shared_crate)
    forward = {(i, r["@id"]) for i, n in nodes.items() if "Collection" in _types(n)
               for r in n.get("hasPart", [])}
    backward = {(r["@id"], i) for i, n in nodes.items() if "Dataset" in _types(n)
                for r in (n["isPartOf"] if isinstance(n.get("isPartOf"), list)
                          else [n["isPartOf"]] if n.get("isPartOf") else [])
                if r["@id"] in nodes and "Collection" in _types(nodes[r["@id"]])}
    assert forward and forward == backward


def test_a_single_collection_element_gets_one_ispartof_not_a_list(shared_crate):
    nodes = _by_id(shared_crate)
    reaction = next(n for i, n in nodes.items() if i.startswith("./reactions/"))
    assert isinstance(reaction["isPartOf"], dict)


def test_element_paths_no_longer_carry_the_collection(shared_crate):
    """The path is the bug's root cause: it encoded a single location for a multi-membership fact."""
    nodes = _by_id(shared_crate)
    element_ids = [i for i, n in nodes.items()
                   if "Dataset" in _types(n) and i != "./"]
    assert element_ids
    for element_id in element_ids:
        assert element_id.split("/")[1] in ("samples", "reactions", "wellplates",
                                            "research_plans", "generics"), element_id


def test_collections_are_contextual_entities_reachable_from_the_root(shared_crate):
    """`@type: "Dataset"` would make each collection a Data Entity Directory, which RO-Crate 1.1
    requires to be path-shaped and reachable from `hasPart` — i.e. it would put the element back
    inside exactly one folder. `mentions` is how the root reaches a contextual entity."""
    nodes = _by_id(shared_crate)
    mentioned = {r["@id"] for r in nodes["./"].get("mentions", [])}
    collections = {i for i, n in nodes.items() if "Collection" in _types(n)}
    assert collections and collections <= mentioned
    assert all(i.startswith("#collection-") for i in collections)
    assert not any("Dataset" in _types(nodes[i]) for i in collections)


def test_sub_collections_keep_their_parent(shared_crate):
    with import_eln(shared_crate) as crate:
        child = next(c for c in crate.collections if c.name == "Child Col")
        assert child.parent is not None and child.parent.name == "Mini Test Collection"


def test_attachments_move_with_their_element(shared_crate):
    """ZIP entry paths come from the same index as the File `@id`s; if either moved alone, the
    crate would describe files the archive does not hold."""
    nodes = _by_id(shared_crate)
    file_ids = {i for i, n in nodes.items() if "File" in _types(n)}
    with zipfile.ZipFile(shared_crate) as z:
        members = {m.split("/", 1)[1] for m in z.namelist() if "/" in m}
    for file_id in file_ids:
        assert file_id.removeprefix("./") in members, file_id


def test_a_collection_without_elements_omits_haspart_rather_than_empty(tmp_path):
    """An empty array is not the same statement as "nothing recorded", and it reads as noise."""
    data = _bundle_data()
    data["Collection"]["col-empty"] = {"label": "Empty Col", "ancestry": ""}
    root = _import(tmp_path, data)
    out = str(tmp_path / "empty.eln")
    root.export_eln(out, ontology_lookup=False, authors=_authors())
    empty = next(n for n in _graph(out) if n.get("name") == "Empty Col")
    assert "hasPart" not in empty


def test_the_collection_fragment_is_stable_across_exports(tmp_path):
    """`col.id or id(col)` falls back to a Python object address; writing that into the crate
    would make two exports of identical data differ."""
    ids = []
    for run in range(2):
        workdir = tmp_path / str(run)
        workdir.mkdir()
        root = _import(workdir, _bundle_data(second_root=True))
        out = str(tmp_path / f"{run}.eln")
        root.export_eln(out, ontology_lookup=False, authors=_authors())
        ids.append(sorted(i for i, n in _by_id(out).items() if "Collection" in _types(n)))
    assert ids[0] == ids[1]


class _StubCollection:
    """A collection with no server id — the synthetic wrapper root an offline bundle gets."""

    def __init__(self, label, col_id=None):
        self.id = col_id
        self.label = label


def test_a_collection_without_an_id_still_gets_a_stable_fragment():
    """Every fixture collection has a truthy id, so this branch never runs in an export test —
    yet it is the one that puts a *label* into an `@id`, where a stray character would land in
    the crate."""
    from chemotion_api.collection import sanitize_filename
    from chemotion_api.export.indexing import _collection_node_id

    taken: dict = {}
    first = _collection_node_id(_StubCollection("My Project / 2026!"), sanitize_filename, taken)
    taken["a"] = first
    second = _collection_node_id(_StubCollection("My Project / 2026!"), sanitize_filename, taken)

    assert first == "#collection-My_Project___2026_-1"
    assert second != first                      # two unnamed collections must not merge
    for node_id in (first, second):
        # Fragment-safe: no spaces, no punctuation a URI parser would treat as structure.
        assert re.fullmatch(r"#collection-[A-Za-z0-9_-]+", node_id), node_id


def test_an_empty_label_and_no_id_still_yields_a_usable_fragment():
    from chemotion_api.collection import sanitize_filename
    from chemotion_api.export.indexing import _collection_node_id

    node_id = _collection_node_id(_StubCollection(""), sanitize_filename, {})
    assert re.fullmatch(r"#collection-[A-Za-z0-9_-]+", node_id), node_id
