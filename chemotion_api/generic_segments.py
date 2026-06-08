"""Loader/registry for the LabIMotion generic *segment* classes attached to elements."""
import uuid
from chemotion_api.connection import Connection

class GenericSegments:
    """Loader and registry for the LabIMotion generic *segment* classes attached to elements.

    Segment classes are fetched lazily from the server and cached on first access.
    """

    def __init__(self, session: Connection):
        self._session = session

    @property
    def all_classes(self):
        """All generic segment classes available on the instance, fetched once and cached.

        The result is cached on the shared :class:`~chemotion_api.connection.Connection` (not on
        this instance), so the many short-lived ``GenericSegments`` created per page load / element
        fetch reuse a single ``/api/v1/segments/klasses.json`` request per connection.

        :return: list of segment-class definitions (``klass`` payloads) as returned by the server.
        :raises ConnectionError: if the segment classes cannot be fetched.
        """
        cached = getattr(self._session, "_generic_segment_classes", None)
        if cached is None:
            get_url = "/api/v1/segments/klasses.json"
            res = self._session.get(get_url)
            if res.status_code != 200:
                raise ConnectionError(f'{res.status_code} -> {res.text}')
            cached = res.json().get('klass', [])
            try:
                self._session._generic_segment_classes = cached
            except Exception:
                pass  # session without a writable cache slot: still return the fetched value

        return cached

    @classmethod
    def new_session(cls, base_segment: dict) -> dict:
        """Create a fresh, unsaved segment instance from a segment-class definition.

        :param base_segment: a segment-class definition (as returned by :attr:`all_classes`);
            its ``id`` and ``properties_release`` are used to seed the new instance.
        :return: a new segment ``dict`` with a generated UUID, marked as new, ready to attach.
        """
        a = {
            'segment_klass_id': base_segment['id'],
            'klassType': 'Segment',
            'is_new': True,
            'id': uuid.uuid4().__str__()
        }
        a['properties'] = base_segment.get('properties_release', {}).copy()
        a['properties_release'] = base_segment.get('properties_release', {}).copy()

        return a