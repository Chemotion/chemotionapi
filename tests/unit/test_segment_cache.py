"""Offline test: generic segment classes are fetched once per connection, not per call.

Regression guard for the redundant-schema-loading fix — the shared cache lives on the
Connection, so the many short-lived GenericSegments instances reuse a single
/api/v1/segments/klasses.json request.
"""
import types


def _fake_session():
    """A minimal stand-in for Connection: counts klasses.json GETs, has the cache slot."""
    calls = {"n": 0}

    def _get(url, *a, **k):
        calls["n"] += 1
        return types.SimpleNamespace(status_code=200, json=lambda: {"klass": [{"id": 1}]})

    session = types.SimpleNamespace(get=_get, _generic_segment_classes=None)
    return session, calls


def test_segment_classes_fetched_once_across_instances():
    from chemotion_api.generic_segments import GenericSegments

    session, calls = _fake_session()

    # Simulate several page loads / element fetches, each creating its own GenericSegments.
    first = GenericSegments(session).all_classes
    second = GenericSegments(session).all_classes
    third = GenericSegments(session).all_classes

    assert first == second == third == [{"id": 1}]
    # The endpoint is hit exactly once — the cache is shared via the session.
    assert calls["n"] == 1
    assert session._generic_segment_classes == [{"id": 1}]
