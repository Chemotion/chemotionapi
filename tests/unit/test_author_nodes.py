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
    b = Author(name="B", orcid="https://orcid.org/0000-0001-0000-0009",
               affiliations=[AuthorAffiliation(name="X", ror="https://ror.org/01hhn8329")])
    assert b.orcid_url == "https://orcid.org/0000-0001-0000-0009"
    assert b.affiliations[0].ror_url == "https://ror.org/01hhn8329"


def test_validate_authors_helpful_errors():
    with pytest.raises(ValueError, match="requires at least one author"):
        validate_authors([])
    with pytest.raises(ValueError, match="missing an ORCID"):
        validate_authors([Author(name="No Orcid", orcid="",
                                 affiliations=[AuthorAffiliation(name="KIT", ror="04t3en479")])])
    with pytest.raises(ValueError, match="has no affiliation"):
        validate_authors([Author(name="No Aff", orcid="0000-0002-1825-0097", affiliations=[])])
    with pytest.raises(ValueError, match="missing a ROR id"):
        validate_authors([Author(name="Bad Aff", orcid="0000-0002-1825-0097",
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
    assert publisher == {"@id": "https://ror.org/04t3en479"}  # root dataset's ``publisher``


def test_build_author_nodes_multiple_authors_and_shared_org():
    shared = AuthorAffiliation(name="KIT", ror="https://ror.org/04t3en479")
    authors = [
        Author(name="A", orcid="0000-0000-0000-0001", affiliations=[shared]),
        Author(name="B", orcid="0000-0003-1613-5981",
               affiliations=[shared, AuthorAffiliation(name="MPI", ror="https://ror.org/01hhn8329")]),
    ]
    refs, publisher, graph_nodes = _build(authors)
    assert len(refs) == 2
    # the shared org appears only once in the graph (deduped by ROR @id)
    orgs = [n for n in graph_nodes.values() if n.get("@type") == "Organization"]
    assert sorted(o["@id"] for o in orgs) == [
        "https://ror.org/01hhn8329", "https://ror.org/04t3en479"]
    # author B carries both affiliations
    person_b = graph_nodes["https://orcid.org/0000-0003-1613-5981"]
    assert isinstance(person_b["affiliation"], list) and len(person_b["affiliation"]) == 2


# --- identifier validation (Slice 5) -------------------------------------

@pytest.mark.parametrize("orcid", [
    "0000-0002-1825-0098",              # right shape, wrong ISO 7064 check digit
    "banana",
    "http://evil.example/ada",          # used to become the crate's authorship @id verbatim
    "https://evil.example/orcid.org/0000-0002-1825-0097",  # name-drops a real iD in its path
    "0000-0002-1825-009",               # too short
])
def test_invalid_orcid_is_refused(orcid):
    with pytest.raises(ValueError, match="not a valid ORCID"):
        Author(name="X", orcid=orcid).orcid_url


@pytest.mark.parametrize("ror", [
    "not-a-ror", "abc", "https://evil.example/ror.org/04t3en479",
    "04t3en47i",                        # 'i' is excluded from crockford base32
    "04t3en478",                        # right shape, wrong MOD 97-10 check digits
])
def test_invalid_ror_is_refused(ror):
    with pytest.raises(ValueError, match="not a valid ROR"):
        AuthorAffiliation(name="X", ror=ror).ror_url


def test_validate_rejects_malformed_identifiers_not_just_missing_ones():
    """A well-formed-looking but wrong ORCID must fail at validation, not silently reach the crate."""
    bad = Author(name="Typo", orcid="0000-0002-1825-0098",
                 affiliations=[AuthorAffiliation(name="KIT", ror="04t3en479")])
    with pytest.raises(ValueError, match="not a valid ORCID"):
        validate_authors([bad])


def test_orcid_accepts_x_check_digit_and_bare_or_prefixed_forms():
    assert Author(name="X", orcid="0000-0002-1694-233X").orcid_url == \
        "https://orcid.org/0000-0002-1694-233X"
    for form in ("0000-0002-1825-0097", "https://orcid.org/0000-0002-1825-0097",
                 "http://orcid.org/0000-0002-1825-0097", "orcid.org/0000-0002-1825-0097"):
        assert Author(name="X", orcid=form).orcid_url == "https://orcid.org/0000-0002-1825-0097"
