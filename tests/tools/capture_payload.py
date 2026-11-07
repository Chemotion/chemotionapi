"""Capture a server response as a JSON fixture for the offline unit tests (M0.2).

The klass and element schemas are strict (``additionalProperties: False``), so unit tests have to
validate against what a real server sends, not a hand-written guess. This logs into the test
stack, GETs one endpoint and writes its JSON into ``tests/unit/data/``.

Usage, from the repository root::

    uv run python tests/tools/capture_payload.py /api/v1/segments/list_segment_klass.json \\
        --select 'klass[0]' --scrub-timestamps -o segment_klass.json

Connection settings follow the integration tests: environment variable, then
``tests/config.json``, then the seeded stack's defaults (``ELN_URL``, ``ELN_USER``, ``ELN_PASS``).

Only capture from the seeded test stack: its data is fictional, so the fixture can be committed.
Check the file before committing anyway.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.dirname(HERE)
DEFAULT_OUT_DIR = os.path.join(TESTS_DIR, 'unit', 'data')

# The seeded stack's account, as in tests/conftest.py DEFAULT_CONFIG.
DEFAULTS = {
    'ELN_URL': 'http://127.0.0.1:3579',
    'ELN_USER': 'API',
    'ELN_PASS': '1234qewR!',
}

#: Stand-in for scrubbed timestamps, in the format the server renders them.
FIXED_TIMESTAMP = '2000-01-01T00:00:00+0000'
_TIMESTAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$')
_SELECT_STEP = re.compile(r'([^.\[\]]+)|\[(\d+)\]')


def load_settings() -> dict[str, str]:
    """Environment, then tests/config.json, then the seeded defaults."""
    file_values: dict[str, Any] = {}
    config_path = os.path.join(TESTS_DIR, 'config.json')
    if os.path.exists(config_path):
        with open(config_path) as f:
            file_values = json.load(f)
    return {key: str(os.getenv(key, file_values.get(key, default))) for key, default in DEFAULTS.items()}


def select(data: Any, path: str | None) -> Any:
    """Pick a sub-tree with a dotted path such as ``klass[0].properties_release``."""
    if not path:
        return data
    for key, index in _SELECT_STEP.findall(path):
        try:
            data = data[int(index)] if index else data[key]
        except (KeyError, IndexError, TypeError) as err:
            raise SystemExit(f'--select {path!r}: no {key or "[" + index + "]"} in the response') from err
    return data


def scrub(data: Any, timestamps: bool, drop: set[str]) -> Any:
    """Recursively drop keys named in ``drop`` and, optionally, pin ISO timestamps."""
    if isinstance(data, dict):
        return {k: scrub(v, timestamps, drop) for k, v in data.items() if k not in drop}
    if isinstance(data, list):
        return [scrub(v, timestamps, drop) for v in data]
    if timestamps and isinstance(data, str) and _TIMESTAMP.match(data):
        return FIXED_TIMESTAMP
    return data


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('path', help='endpoint path, e.g. /api/v1/samples/12')
    parser.add_argument('-p', '--param', action='append', default=[], metavar='KEY=VALUE',
                        help='query parameter (repeatable)')
    parser.add_argument('-s', '--select', help="sub-tree to keep, e.g. 'klass[0]' or 'sample'")
    parser.add_argument('--scrub-timestamps', action='store_true',
                        help=f'replace ISO timestamps with {FIXED_TIMESTAMP}')
    parser.add_argument('--drop', action='append', default=[], metavar='KEY',
                        help='remove this key wherever it occurs (repeatable)')
    parser.add_argument('-o', '--out',
                        help=f'output file; a bare name goes into {os.path.relpath(DEFAULT_OUT_DIR)}. '
                             'Omit to print to stdout.')
    parser.add_argument('--force', action='store_true', help='overwrite an existing output file')
    return parser.parse_args(argv)


def output_path(out: str) -> str:
    return out if os.path.dirname(out) else os.path.join(DEFAULT_OUT_DIR, out)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    params = {}
    for item in args.param:
        key, sep, value = item.partition('=')
        if not sep:
            raise SystemExit(f'--param {item!r}: expected KEY=VALUE')
        params[key] = value

    out = output_path(args.out) if args.out else None
    if out and os.path.exists(out) and not args.force:
        raise SystemExit(f'{out} exists; pass --force to overwrite it')

    sys.path.insert(0, os.path.dirname(TESTS_DIR))
    from chemotion_api import Instance

    settings = load_settings()
    instance = Instance(settings['ELN_URL']).login(settings['ELN_USER'], settings['ELN_PASS'])
    res = instance._con.get(args.path, params=params or None)
    if res.status_code != 200:
        body = res.text if 'json' in res.headers.get('Content-Type', '') else res.reason
        raise SystemExit(f'GET {args.path} -> HTTP {res.status_code}: {" ".join(str(body).split())[:200]}')

    data = scrub(select(res.json(), args.select), args.scrub_timestamps, set(args.drop))
    text = json.dumps(data, indent=1, ensure_ascii=False) + '\n'
    version = instance._con.schema_manager.version_string
    if out:
        with open(out, 'w') as f:
            f.write(text)
        # Provenance goes to stderr, not into the fixture: an extra key would fail strict schemas.
        print(f'wrote {out} ({len(text)} bytes) from {args.path} on ELN {version}', file=sys.stderr)
    else:
        sys.stdout.write(text)
        print(f'captured from {args.path} on ELN {version}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
