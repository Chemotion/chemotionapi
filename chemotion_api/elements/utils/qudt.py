"""Chemotion unit strings to QUDT unit IRIs, for the chem-dcat-ap mapping.

One table, shared by the sample and reaction mappings. It used to be a closure copied into
both, and the copies had already diverged — the sample one knew masses, volumes and times, the
reaction one only temperatures — so a unit fixed in one stayed broken in the other.

**An unknown unit yields ``None``, never a guess.** The previous fallback appended the raw
string to ``http://qudt.org/vocab/unit/``, which cannot produce a valid QUDT name except by
accident: QUDT spells these ``DEG_F``, ``BAR``, ``CentiM``, ``ANGSTROM``. Worse, a few raw
strings *do* resolve, to the wrong quantity — bare ``F`` is QUDT's **Faraday**, a unit of
electric charge, not Fahrenheit. A dead IRI is a broken link a reader can see; one that
resolves to the wrong concept is a silent error nothing downstream can detect. Callers drop
the ``unit`` field when this returns ``None``; the unit stays legible in the quantity's title.
"""
import logging

logger = logging.getLogger(__name__)

QUDT_UNIT = "http://qudt.org/vocab/unit/"

#: Chemotion's spellings -> QUDT local name. Every target is verified to resolve.
_UNITS: dict[tuple[str, ...], str] = {
    ('g', 'gram', 'grams'): "GM",
    ('mg', 'milligram', 'milligrams'): "MilliGM",
    ('ug', 'µg', 'microgram', 'micrograms'): "MicroGM",
    ('kg', 'kilogram', 'kilograms'): "KiloGM",

    ('mol', 'mole', 'moles'): "MOL",
    ('mmol', 'millimole', 'millimoles'): "MilliMOL",
    ('umol', 'µmol', 'micromole', 'micromoles'): "MicroMOL",

    ('l', 'liter', 'liters', 'litre', 'litres'): "L",
    ('ml', 'milliliter', 'milliliters', 'millilitre'): "MilliL",
    ('ul', 'µl', 'microliter', 'microliters', 'microlitre'): "MicroL",

    ('m', 'mol/l', 'mol-per-l', 'molar'): "MOL-PER-L",
    ('g/ml', 'g/cm3', 'gram-per-millilitre'): "GM-PER-MilliL",
    ('g/mol', 'gram-per-mole'): "GM-PER-MOL",

    # Fahrenheit was missing, and is a documented `valueUnit` (see Reaction.temperature).
    # Unmapped it produced `.../°F`, which is dead, while bare `F` would have resolved to
    # Faraday. Both spellings now map to QUDT's DEG_F.
    ('°c', 'c', 'deg_c', 'deg c', 'celsius'): "DEG_C",
    ('°f', 'f', 'deg_f', 'deg f', 'fahrenheit'): "DEG_F",
    ('k', 'kelvin'): "K",

    ('h', 'hr', 'hour', 'hours', 'hour(s)'): "HR",
    ('s', 'sec', 'second', 'seconds', 'second(s)'): "SEC",
    ('min', 'minute', 'minutes', 'minute(s)'): "MIN",

    ('%', 'percent', 'percentage'): "PERCENT",
}

#: Flattened once at import: spelling -> IRI.
_BY_SPELLING: dict[str, str] = {
    spelling: QUDT_UNIT + local
    for spellings, local in _UNITS.items()
    for spelling in spellings
}


def qudt_unit(unit_str: str | None) -> str | None:
    """The QUDT IRI for ``unit_str``, or ``None`` when no known unit matches.

    An empty or absent unit is ``UNITLESS`` — that is a statement, not a guess. Anything we do
    not recognise returns ``None`` and is logged once, so the quantity is exported without a
    ``unit`` rather than with an identifier that may be dead or point at the wrong quantity.

    :param unit_str: the unit exactly as Chemotion stores it, e.g. ``'mg'``, ``'°C'``.
    :return: a QUDT unit IRI, or ``None``.
    """
    if not unit_str or not str(unit_str).strip():
        return QUDT_UNIT + "UNITLESS"
    iri = _BY_SPELLING.get(str(unit_str).strip().lower())
    if iri is None:
        logger.info(
            "No QUDT unit is known for %r, so the quantity is exported without one rather than "
            "with a guessed IRI. Add it to chemotion_api.elements.utils.qudt if it should map.",
            unit_str)
    return iri
