"""The value of a field the server withheld from the current user.

When a collection is shared below the full detail level (10), ELN v4 still sends the element but
replaces each withheld field with the string ``'***'`` — numbers and booleans included — and sets
``is_restricted: true``. Parsing ``'***'`` as a number fails, and reading it as ``None`` would make
"withheld" indistinguishable from "empty". So the client substitutes :data:`WITHHELD`, a sentinel
that is neither ``None`` nor a number — and is a ``str`` reading ``'***'``, so a payload still
serialises as the server sent it.

Using it as a number raises :class:`WithheldValueError` (a ``PermissionError``) with a message
that says why. Other fields the server withholds arrive as ``null``, ``[]`` or ``{}``; those cannot
be told apart from genuinely empty values, so they are left as they are.
"""
from typing import Any

#: The marker ELN v4 puts in place of a withheld field.
SERVER_MASK = '***'


class WithheldValueError(PermissionError):
    """A withheld value was used as a number."""


class Withheld(str):
    """Singleton sentinel for a withheld field; compare with ``is WITHHELD``.

    It is a ``str`` whose text is the server's own mask, ``'***'`` (owner, 2026-11-13): raw
    ``json_data`` still serialises — ``json.dumps``, ``str()`` and f-strings give exactly what the
    server sent — so code that passes payloads on (a downstream app encoding results as JSON) keeps
    working. Being a sentinel, it still refuses to act as a number.
    """

    _instance: Withheld | None = None

    def __new__(cls) -> Withheld:
        if cls._instance is None:
            cls._instance = super().__new__(cls, SERVER_MASK)
        return cls._instance

    def __repr__(self) -> str:
        return 'WITHHELD'

    def __reduce__(self):
        return (Withheld, ())

    def _refuse(self, *args, **kwargs):
        raise WithheldValueError(
            'This value was withheld by the server: the element is shared with you below the full '
            'detail level, so it is not available to you.')

    # Numeric use — and the str operations that would otherwise quietly succeed in its place
    # (`WITHHELD * 2` repeating the text, `WITHHELD + 'x'` concatenating) — raise instead.
    __float__ = __int__ = __index__ = __round__ = _refuse
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _refuse
    __truediv__ = __rtruediv__ = __lt__ = __le__ = __gt__ = __ge__ = _refuse


#: The one :class:`Withheld` instance.
WITHHELD = Withheld()


def mark_withheld(data: Any) -> Any:
    """Replace every :data:`SERVER_MASK` string in ``data`` with :data:`WITHHELD`, in place.

    Call it only on a payload the server flagged ``is_restricted`` — elsewhere ``'***'`` may be a
    value a user actually typed.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if value == SERVER_MASK:
                data[key] = WITHHELD
            else:
                mark_withheld(value)
    elif isinstance(data, list):
        for i, value in enumerate(data):
            if value == SERVER_MASK:
                data[i] = WITHHELD
            else:
                mark_withheld(value)
    return data
