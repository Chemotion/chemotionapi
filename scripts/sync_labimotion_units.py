#!/usr/bin/env python
"""Regenerate the LabIMotion unit table in ``chemotion_api/labImotion/items/options.py``.

``options.py`` hand-mirrors ``lib/labimotion/utils/units.rb`` from the labimotion gem. When the
ELN bumps LabIMotion, units are added, and a klass using one the client has not learned raises on
load (now: warns — see ``SystemDefined``). Neither the JSON-Schema drift check nor the integration
suite catches that, so re-sync deliberately:

    python scripts/sync_labimotion_units.py 2.3.0 --check    # CI / verification
    python scripts/sync_labimotion_units.py 2.3.0            # rewrite options.py

A ``.gem`` is a plain tar containing ``data.tar.gz``; no ruby toolchain is needed. Versions are
listed at https://rubygems.org/gems/labimotion/versions.
"""
import argparse
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

GEM_URL = 'https://rubygems.org/downloads/labimotion-{version}.gem'
UNITS_RB = 'lib/labimotion/utils/units.rb'
FIELD_TYPE_RB = 'lib/labimotion/utils/field_type.rb'

#: Field types the **server emits** that the gem's field_type.rb does not declare. Regenerating
#: the enum from the gem alone would silently drop these again, so they are carried explicitly.
#: `select-multi` is intentional upstream — labimotion/libs/element_variation_column_set.rb says
#: "select-multi deliberately has no Labimotion::FieldType constant" — yet klasses use it.
#: DO NOT remove without checking a live instance first.
EXTRA_FIELD_TYPES = ('select-multi',)
OPTIONS_PY = Path(__file__).resolve().parent.parent / 'chemotion_api/labImotion/items/options.py'


def fetch_units(version: str) -> list[dict]:
    """Return the parsed unit table from the published gem."""
    with urllib.request.urlopen(GEM_URL.format(version=version), timeout=60) as response:
        gem = tarfile.open(fileobj=io.BytesIO(response.read()))
    data = tarfile.open(fileobj=io.BytesIO(gem.extractfile('data.tar.gz').read()), mode='r:gz')
    source = data.extractfile(UNITS_RB).read().decode('utf-8')
    # units.rb is a Ruby file wrapping one JSON array literal.
    return json.loads(re.search(r'\[\s*\{.*\}\s*\]', source, re.S).group(0))


def fetch_field_types(version: str) -> list[str]:
    """Return the field-type values the gem declares, plus the ones only the server emits."""
    with urllib.request.urlopen(GEM_URL.format(version=version), timeout=60) as response:
        gem = tarfile.open(fileobj=io.BytesIO(response.read()))
    data = tarfile.open(fileobj=io.BytesIO(gem.extractfile('data.tar.gz').read()), mode='r:gz')
    source = data.extractfile(FIELD_TYPE_RB).read().decode('utf-8')
    declared = re.findall(r"^\s*[A-Z_0-9]+\s*=\s*'([^']+)'\.freeze", source, re.M)
    return sorted(set(declared) | set(EXTRA_FIELD_TYPES))


def render(entries: list[dict], existing_names: dict[str, str]) -> str:
    """Render the FieldUnit enum and UNITS dict, keeping current member names stable."""
    seen, rows = set(), []
    for entry in entries:
        field = entry['field']
        if field in seen:
            continue
        seen.add(field)
        rows.append((existing_names.get(field, field.upper()), field,
                     [unit['key'] for unit in entry.get('units', [])]))

    out = ['class FieldUnit(ListableEnum):']
    out += [f'    {name} = "{value}"' for name, value, _ in rows]
    out += ['', '', 'UNITS: dict[FieldUnit, list[str]] = {']
    for name, _, keys in rows:
        line = f'    FieldUnit.{name}: [' + ', '.join(f'"{k}"' for k in keys) + '],'
        if len(line) <= 118:
            out.append(line)
            continue
        out.append(f'    FieldUnit.{name}: [')
        current = '       '
        for key in keys:
            piece = f' "{key}",'
            if len(current) + len(piece) > 114:
                out.append(current)
                current = '       '
            current += piece
        if current.strip():
            out.append(current)
        out.append('    ],')
    out.append('}')
    return '\n'.join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', help='labimotion gem version, e.g. 2.3.0')
    parser.add_argument('--check', action='store_true',
                        help='report drift and exit non-zero instead of rewriting options.py')
    args = parser.parse_args()

    sys.path.insert(0, str(OPTIONS_PY.parents[3]))
    from chemotion_api.labImotion.items.options import UNITS, FieldUnit

    entries = fetch_units(args.version)
    gem = {e['field']: [u['key'] for u in e.get('units', [])] for e in entries}
    ours = {unit.value: keys for unit, keys in UNITS.items()}

    missing_types = sorted(set(gem) - set(ours))
    stale_types = sorted(set(ours) - set(gem))
    key_drift = {
        unit_type: sorted(set(gem[unit_type]) - set(ours[unit_type]))
        for unit_type in sorted(set(gem) & set(ours))
        if set(gem[unit_type]) - set(ours[unit_type])
    }

    # Field types gate JSON-Schema validation of every klass (schema_field.py renders
    # FieldType.list() into an `enum`), so drift there makes klasses unreadable, not just odd.
    from chemotion_api.labImotion.items.options import FieldType
    ours_ft = {m.value for m in FieldType}
    gem_ft = set(fetch_field_types(args.version))
    missing_ft = sorted(gem_ft - ours_ft)
    if missing_ft:
        print(f'labimotion {args.version}: field types missing from the client: '
              f'{", ".join(missing_ft)}', file=sys.stderr)

    if not (missing_types or stale_types or key_drift or missing_ft):
        print(f'labimotion {args.version}: unit table is in sync ({len(gem)} unit types); '
              f'field types in sync ({len(gem_ft)}).')
        return 0

    print(f'labimotion {args.version}: unit table is OUT OF SYNC', file=sys.stderr)
    if missing_types:
        print(f'  unit types missing from the client ({len(missing_types)}): '
              f'{", ".join(missing_types)}', file=sys.stderr)
    if stale_types:
        print(f'  unit types the gem no longer defines ({len(stale_types)}): '
              f'{", ".join(stale_types)}', file=sys.stderr)
    for unit_type, keys in key_drift.items():
        print(f'  {unit_type}: missing {", ".join(keys)}', file=sys.stderr)

    if args.check:
        return 1

    names = {member.value: member.name for member in FieldUnit}
    source = OPTIONS_PY.read_text(encoding='utf-8')
    start = source.index('class FieldUnit(ListableEnum):')
    layer_color = source.index('class LayerColor(ListableEnum):')
    units_start = source.index('UNITS', layer_color)
    units_end = source.index('\n}\n', units_start) + 3
    block = render(entries, names)
    enum_block, units_block = block.split('\n\n\nUNITS')
    rewritten = (source[:start] + enum_block + '\n\n\n'
                 + source[layer_color:units_start] + 'UNITS' + units_block + source[units_end:])
    OPTIONS_PY.write_text(rewritten, encoding='utf-8')
    print(f'rewrote {OPTIONS_PY.relative_to(Path.cwd())} from labimotion {args.version}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
