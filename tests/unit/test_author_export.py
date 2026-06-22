"""Offline tests: the logged-in user is exported as the crate's author (best-effort).

Chemotion elements do not expose a per-element creator, so ``export_eln`` records the
**exporting user** as the author (Person + Organization contextual entities).
"""
import pytest

from chemotion_api.collection import _build_author_nodes


class _FakeAffiliation:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class _FakeUser:
    def __init__(self, affiliations=()):
        self.id = 7
        self.email = "ada@example.org"
        self.name = "Ada Lovelace"
        self._affiliations = list(affiliations)

    def get_affiliations(self):
        return self._affiliations


def _patch_logged_in_user(monkeypatch, user):
    from chemotion_api import user as user_mod
    monkeypatch.setattr(user_mod.User, "load_me", classmethod(lambda cls, session: user))


def test_logged_in_user_becomes_person_node(monkeypatch):
    _patch_logged_in_user(monkeypatch, _FakeUser())
    meta, nodes = {"@graph": []}, {}
    refs, publisher = _build_author_nodes(meta, nodes, session=object())
    assert refs == [{"@id": "#author-7"}]
    person = nodes["#author-7"]
    assert person["@type"] == "Person"
    assert person["name"] == "Ada Lovelace"
    assert person["email"] == "ada@example.org"
    assert person["identifier"] == "ada@example.org"
    assert publisher is None  # no affiliations -> no sdPublisher


def test_affiliations_become_organizations(monkeypatch):
    _patch_logged_in_user(monkeypatch, _FakeUser(
        [_FakeAffiliation(1, "KIT, IBG, NFDI"), _FakeAffiliation(2, "MPI")]))
    meta, nodes = {"@graph": []}, {}
    refs, publisher = _build_author_nodes(meta, nodes, session=object())
    orgs = [n for n in meta["@graph"] if n.get("@type") == "Organization"]
    assert [o["name"] for o in orgs] == ["KIT, IBG, NFDI", "MPI"]
    person = nodes["#author-7"]
    assert person["affiliation"] == [{"@id": "#organization-1"}, {"@id": "#organization-2"}]
    # the first affiliation doubles as the descriptor's sdPublisher
    assert publisher == {"@id": "#organization-1"}


def test_nodes_are_not_duplicated(monkeypatch):
    _patch_logged_in_user(monkeypatch, _FakeUser([_FakeAffiliation(1, "KIT")]))
    meta, nodes = {"@graph": []}, {}
    refs1, _ = _build_author_nodes(meta, nodes, session=object())
    refs2, _ = _build_author_nodes(meta, nodes, session=object())
    assert refs1 == refs2
    assert len([n for n in meta["@graph"] if n.get("@type") == "Person"]) == 1
    assert len([n for n in meta["@graph"] if n.get("@type") == "Organization"]) == 1


def test_failure_is_graceful(monkeypatch):
    """Author metadata is best-effort: a failing user lookup must not break the export."""
    from chemotion_api import user as user_mod

    def _boom(cls, session):
        raise PermissionError("not logged in")

    monkeypatch.setattr(user_mod.User, "load_me", classmethod(_boom))
    meta, nodes = {"@graph": []}, {}
    refs, publisher = _build_author_nodes(meta, nodes, session=object())
    assert refs == [] and publisher is None
    assert meta["@graph"] == []  # graph untouched
