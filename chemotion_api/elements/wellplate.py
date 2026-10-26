"""Wellplate element: a grid of wells, each optionally holding a :class:`~chemotion_api.elements.sample.Sample`."""
import logging
from chemotion_api.elements.abstract_element import AbstractElement

from chemotion_api.elements.sample import Sample
from collections.abc import MutableMapping
from typing import cast

logger = logging.getLogger(__name__)

#: Largest width/height the server accepts (``wellplate_api.rb``: ``values: 1..100``). The web
#: client caps its own input one lower (``Wellplate.MAX_DIMENSION == 99``), so a 100-row plate
#: is reachable through the API but not through the UI.
MAX_DIMENSION = 100

#: Default plate, and the ``wellplates.width``/``.height`` column defaults in the v4 schema.
DEFAULT_WIDTH = 12
DEFAULT_HEIGHT = 8


def row_label(index: int) -> str:
    """Return the row label for a 0-based row index: ``A``-``Z``, then ``AA``-``AZ``, ``BA``-…

    A hand-mirror of ``Wellplate.rowLabel`` in the ELN's ``app/javascript/src/models/Wellplate.js``,
    which spells the same sequence out literally up to ``CZ``. Labels must agree with the web
    client's, or the same well is named differently in each.
    """
    if index < 26:
        return chr(ord('A') + index)
    return chr(ord('A') + (index - 26) // 26) + chr(ord('A') + (index - 26) % 26)


class WellplateCol(MutableMapping):
    """
    One column of a well plate: a mapping from row label to a
    :class:`~chemotion_api.elements.sample.Sample` (or None for an empty well).

    Keys are case-insensitive. The available labels depend on the plate's height — ``A``-``H`` for
    the default 8-row plate, up to ``CV`` for a 100-row one — and any other key raises ``IndexError``.
    """

    def __init__(self, *args, height: int = DEFAULT_HEIGHT, **kwargs):
        self._keys = [row_label(i) for i in range(height)]
        self.store = dict.fromkeys(self._keys, None)
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key: str):
        return self.store[self._keytransform(key)]

    def __setitem__(self, key: str, value: Sample | None):
        """Assign a sample to this well, as a *split* of it — the ELN's own semantics.

        Putting an existing sample into a well creates a subsample, which is why assignment goes
        through :meth:`~chemotion_api.elements.sample.Sample.split`. Note that ``split()`` saves
        the source sample, so this performs a request.
        """
        self.store[self._keytransform(key)] = value.split() if value is not None else None

    def place_loaded(self, key: str, value: Sample | None) -> None:
        """Put a sample that already belongs to this well into it, as-is.

        Parsing the server's own payload must not go through ``__setitem__``: that splits, and
        ``split()`` PUTs the source sample and returns a *new, unsaved* subsample labelled
        ``…-NaN``. Merely reading a wellplate therefore wrote to the server once per occupied
        well and then held samples that were not the ones on the plate — so a subsequent save
        replaced every well's contents.
        """
        self.store[self._keytransform(key)] = value

    def __delitem__(self, key):
        del self.store[self._keytransform(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def _keytransform(self, key):
        key = key.upper()
        if key not in self._keys:
            raise IndexError(
                f"This wellplate has {len(self._keys)} rows, so its row keys are "
                f"{self._keys[0]}-{self._keys[-1]}; got {key!r}")
        return key


class Wellplate(AbstractElement):
    """
    Wellplates represent the localization of materials (chemicals)
    for biological experiments and are therefore some kind of link between chemical and biological operations.
    It extends the :class:`chemotion_api.elements.abstract_element.AbstractElement`

    - Plate size: :attr:`width` x :attr:`height`, 12 x 8 by default, up to 100 x 100
    - Vertical indexing: ``0`` to ``width - 1``
    - Horizontal indexing: ``'A'`` upwards (``'A'``-``'H'`` on a default plate)

    The plate's dimensions are fixed once it exists: the v4 update endpoint does not accept
    ``width``/``height`` (only creation does), so an existing wellplate cannot be resized through
    the API.

    Usage::

    >>> from chemotion_api import Instance
    >>> from chemotion_api.collection import Collection
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> # Get the wellplate with ID 1
    >>> wp = instance.get_wellplate(1)
    >>> # Add samples to wellplate
    >>> wp.wells[0]['A'] = instance.get_sample(1)
    >>> wp.wells[0]['B'] = instance.get_sample(1)
    >>> wp.wells[0]['C'] = instance.get_sample(1)
    >>> wp.wells[1]['A'] = instance.get_sample(2)
    >>> wp.wells[1]['B'] = instance.get_sample(2)
    >>> wp.wells[1]['C'] = instance.get_sample(2)
    >>> wp.save()

    """

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)
        # Cleared rather than parsed: `wells` is gated behind `unless: :displayed_in_list` in
        # v4's WellplateEntity, so a list payload carries an empty array. Parsing eagerly would
        # build an empty grid, and a later save would then write every well back as empty —
        # the same destructive asymmetry Slice 2 fixed for `properties`, which is why `wells`
        # is lazy for exactly the same reason.
        self._wells: list[WellplateCol] | None = None

    @staticmethod
    def _dimension(json_data: dict, key: str, default: int) -> int:
        value = json_data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_DIMENSION:
            if value is not None:
                logger.warning("Wellplate %s of %r is not an integer in 1-%d; using %d",
                               key, value, MAX_DIMENSION, default)
            return default
        return value

    @property
    def width(self) -> int:
        """Number of columns, as the server reports it (12 by default)."""
        return self._dimension(cast(dict, self.json_data), 'width', DEFAULT_WIDTH)

    @property
    def height(self) -> int:
        """Number of rows, as the server reports it (8 by default)."""
        return self._dimension(cast(dict, self.json_data), 'height', DEFAULT_HEIGHT)

    @property
    def size(self) -> int:
        """Total number of wells (``width * height``), matching the server's ``Wellplate#size``."""
        return self.width * self.height

    def resize(self, width: int, height: int) -> Wellplate:
        """Change the plate's grid (``PUT /api/v1/wellplates/resize/:id``).

        **This is the only way to resize a plate on ELN v4.** The ordinary wellplate ``PUT`` does
        not declare ``width``/``height`` at all, so assigning them and calling :meth:`save` is
        silently a no-op — the server drops undeclared params. Upstream did that deliberately, so
        a stale tab cannot revert somebody else's resize.

        Growing is always allowed. **Shrinking is refused when a well that would fall outside the
        new grid still holds data**; the server answers 422 and names the blocking positions. Clear
        those wells first — this client will not clear them for you, because deleting someone's
        samples to satisfy a resize is not a decision a wrapper should take.

        :param width: new column count, 0..100.
        :param height: new row count, 0..100.
        :return: self, refreshed from the server's response.
        :raises ValueError: if a dimension is out of range, or the server refuses the shrink (422).
        :raises PermissionError: if you may not update this wellplate (401).
        """
        for name, value in (('width', width), ('height', height)):
            if not isinstance(value, int) or isinstance(value, bool) \
                    or not 0 <= value <= MAX_DIMENSION:
                raise ValueError(
                    f"{name} must be an integer from 0 to {MAX_DIMENSION}; got {value!r}")

        res = self._session.put(f'/api/v1/wellplates/resize/{self.id}',
                                data={'id': self.id, 'width': width, 'height': height})
        if res.status_code == 401:
            raise PermissionError(f'You may not update wellplate {self.id}.')
        if res.status_code == 404:
            raise ValueError(f'Wellplate {self.id} does not exist.')
        if res.status_code == 422:
            # The message names the wells that block the shrink, which is the actionable part.
            raise ValueError(f'The server refused the resize: {res.text}')
        if res.status_code not in (200, 201):
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        payload = res.json()
        if isinstance(payload, dict) and 'wellplate' in payload:
            self._set_json_data(payload['wellplate'])
            self._wells = None          # the grid changed; drop the parsed columns
        return self

    @property
    def wells(self) -> list[WellplateCol]:
        """The plate's columns, each a :class:`WellplateCol` mapping row label to sample or None.

        Fetches the full record on first access, because the list payload omits ``wells``.
        """
        self._ensure_loaded()
        if self._wells is None:
            self._wells = self._parse_wells()
        return self._wells

    def _parse_wells(self) -> list[WellplateCol]:
        width, height = self.width, self.height
        wells = [WellplateCol(height=height) for _ in range(width)]
        for element in cast(dict, self.json_data).get('wells') or []:
            if not isinstance(element, dict) or element.get('sample') is None:
                continue
            position = element.get('position') or {}
            try:
                x = int(position['x']) - 1
                y = int(position['y']) - 1
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipping wellplate well with an unreadable position: %r", position)
                continue
            if not (0 <= x < width and 0 <= y < height):
                # Previously an IndexError that aborted loading the whole element.
                logger.warning("Skipping well at position (%d, %d): outside this %dx%d plate",
                               x + 1, y + 1, width, height)
                continue
            wells[x].place_loaded(
                row_label(y), Sample(self._generic_segments, self._session, element['sample']))
        return wells

    def _parse_properties(self) -> dict:

        return {
            'name': cast(dict, self.json_data).get('name'),
            'description': cast(dict, self.json_data).get('description')
        }

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        # The former `wells[:json_data.get('size')]` was always `[:None]`, i.e. a no-op copy:
        # `size` is a *method* on the Rails model (width * height), not a column, and
        # WellplateEntity never exposes it.
        # Serialising must not mutate the element. This wrote the cleaned payloads straight into
        # `self.json_data['wells'][i]['sample']` and returned `json_data` itself, so after a failed
        # PUT (save() only reloads on success) the in-memory wellplate held serialised payloads
        # where the server's raw records had been, and anything that re-read or re-serialised it
        # saw the mutated shape. A shallow copy per well is enough: only these keys are replaced.
        wells, width, height = self.wells, self.width, self.height
        out_wells = []
        for element in cast(dict, self.json_data).get('wells') or []:
            element = dict(element)
            out_wells.append(element)
            position = element.get('position') or {}
            try:
                x = int(position['x']) - 1
                y = int(position['y']) - 1
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= x < width and 0 <= y < height):
                continue
            element['is_new'] = element.get('is_new', False)
            sample = wells[x][row_label(y)]
            element['sample'] = None if sample is None else sample.clean_data()

        return cast(dict, self.json_data) | {
            'wells': out_wells,
            'name': self.properties.get('name'),
            'description': self.properties.get('description'),
        }


    def save(self):
        """
        Save the well plate to the server and reload it to refresh the well/sample data.
        """
        super().save()
        self.load()
