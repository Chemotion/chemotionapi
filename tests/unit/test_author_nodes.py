"""Offline tests for manual author/affiliation export metadata + the Grape Affiliation model."""
import pytest

from chemotion_api.user import Affiliation
from chemotion_api.authors import Author, AuthorAffiliation, validate_authors
from chemotion_api.collection import _build_author_nodes


def test_affiliation_from_json_and_name():
    aff = Affiliation.from_json({"id": 5, "organization": "KIT", "department": "IBG",
                                 "group": "NFDI", "country": "DE", "from": "2020", "to": None})
    assert aff.id == 5 and aff.organization == "KIT" and aff.country == "DE"
    assert aff.name == "KIT, IBG, NFDI"
    assert aff.to_dict()["from"] == "2020"


# --- manual Author model -------------------------------------------------

def test_orcid_and_ror_normalization():
    a = Author(name="Ada", orcid="0000-0002-1825-0097",
               affiliations=[AuthorAffiliation(name="KIT", ror="04t3en479")])
    assert a.orcid_url == "https://orcid.org/0000-0002-1825-0097"
    assert a.affiliations[0].ror_url == "https://ror.org/04t3en479"
    # already-full URLs pass through unchanged
    b = Author(name="B", orcid="https://orcid.org/0000-0001-0000-0000",
               affiliations=[AuthorAffiliation(name="X", ror="https://ror.org/abc")])
    assert b.orcid_url == "https://orcid.org/0000-0001-0000-0000"
    assert b.affiliations[0].ror_url == "https://ror.org/abc"


def test_validate_authors_helpful_errors():
    with pytest.raises(ValueError, match="requires at least one author"):
        validate_authors([])
    with pytest.raises(ValueError, match="missing an ORCID"):
        validate_authors([Author(name="No Orcid", orcid="",
                                 affiliations=[AuthorAffiliation(name="KIT", ror="r")])])
    with pytest.raises(ValueError, match="has no affiliation"):
        validate_authors([Author(name="No Aff", orcid="0000", affiliations=[])])
    with pytest.raises(ValueError, match="missing a ROR id"):
        validate_authors([Author(name="Bad Aff", orcid="0000",
                                 affiliations=[AuthorAffiliation(name="KIT", ror="")])])


def _build(authors):
    meta = {"@graph": []}
    graph_nodes = {}
    refs, publisher = _build_author_nodes(meta, graph_nodes, authors)
    return refs, publisher, graph_nodes


def test_build_author_nodes_person_and_org():
    authors = [Author(name="Ada Lovelace", orcid="0000-0002-1825-0097", email="ada@kit.edu",
                      affiliations=[AuthorAffiliation(name="KIT", ror="https://ror.org/04t3en479")])]
    refs, publisher, graph_nodes = _build(authors)
    assert refs == [{"@id": "https://orcid.org/0000-0002-1825-0097"}]
    person = graph_nodes["https://orcid.org/0000-0002-1825-0097"]
    assert person["@type"] == "Person" and person["name"] == "Ada Lovelace"
    assert person["identifier"] == "https://orcid.org/0000-0002-1825-0097"
    assert person["email"] == "ada@kit.edu"
    assert person["affiliation"] == {"@id": "https://ror.org/04t3en479"}
    org = graph_nodes["https://ror.org/04t3en479"]
    assert org["@type"] == "Organization" and org["name"] == "KIT"
    assert org["identifier"] == "https://ror.org/04t3en479"
    assert publisher == {"@id": "https://ror.org/04t3en479"}  # descriptor sdPublisher


def test_build_author_nodes_multiple_authors_and_shared_org():
    shared = AuthorAffiliation(name="KIT", ror="https://ror.org/04t3en479")
    authors = [
        Author(name="A", orcid="0000-0000-0000-0001", affiliations=[shared]),
        Author(name="B", orcid="0000-0000-0000-0002",
               affiliations=[shared, AuthorAffiliation(name="MPI", ror="https://ror.org/0287p9c41")]),
    ]
    refs, publisher, graph_nodes = _build(authors)
    assert len(refs) == 2
    # the shared org appears only once in the graph (deduped by ROR @id)
    orgs = [n for n in graph_nodes.values() if n.get("@type") == "Organization"]
    assert sorted(o["@id"] for o in orgs) == [
        "https://ror.org/0287p9c41", "https://ror.org/04t3en479"]
    # author B carries both affiliations
    person_b = graph_nodes["https://orcid.org/0000-0000-0000-0002"]
    assert isinstance(person_b["affiliation"], list) and len(person_b["affiliation"]) == 2
