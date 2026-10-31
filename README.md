# Chemotion API Python Client

A modernized Python client for the [Chemotion ELN](https://chemotion.net/) REST/Grape API,
targeting **ELN v4** and validating element properties with **Pydantic v2**.

The FAIR `.eln` (RO-Crate) export and the offline ingester are a separate pull request on this
line and are **not** in this release.

## Key features

- **Full REST client** — collections, samples, reactions, wellplates, research plans, LabIMotion
  generic elements/segments/datasets, attachments and analyses, search, users/groups/devices,
  inbox, converter profiles, and admin endpoints.
- **Pydantic v2 type safety** — element properties are validated and normalized on read and write.
- **Instance management CLI** — the `chemotion_api` command scaffolds and manages local
  dockerized Chemotion instances (start/stop, ports, backups).

## Requirements & installation

- Python **>= 3.14** (managed automatically by [uv](https://docs.astral.sh/uv/))
- **A Chemotion ELN v4 server.** ELN 3.x and older are *not* supported: v4 rewrote collections and
  sharing, renumbered share permission levels and removed the `/syncCollections` API, so there is
  no meaningful overlap. Connecting to an older instance raises `UnsupportedServerVersion` at
  `test_connection()`, before any credentials are sent.
  **For an ELN 3.1.x server, use the `312.x` release line instead.**
  The version scheme tracks the server: `400.x.y` ↔ ELN 4.0, `312.x.y` ↔ ELN 3.1.2.
- For development: [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/)
  (plus docker for the integration test stack).

Install from source (dependencies resolve from PyPI):

```bash
git clone <this repository> && cd chemotionapi

# for development (locked environment with all dependency groups)
uv sync --all-groups      # or: just sync

# as a plain library install
pip install .
```

## Development tasks

Everything is automated through [`just`](./justfile) — run `just` for the full list:

```bash
just sync               # create/refresh the locked virtualenv (uv)
just check              # lint + mypy + offline test suite (the local gate)
just test-integration   # integration suite against the self-contained docker ELN (also runs nightly in CI)
just cov                # offline-suite coverage report (gated at 54%)
just docs               # build the Sphinx documentation
just schemas            # dump the LabIMotion JSON schemas from a live ELN
just stack-up           # start / stop / reset / watch the dockerized test ELN
just build              # build sdist + wheel
```

## Quickstart

Connect and create a validated sample and reaction:

```python
from chemotion_api import Instance

with Instance("https://chemotion.dept.uni.de", username="USER", password="PASS") as instance:
    project = instance.get_or_create_collection("My Synthesis Project")

    sample = project.new_sample_smiles("CCO")
    sample.name = "Ethanol Stock"
    sample.properties.purity = 0.998        # validated by Pydantic
    sample.save()

    reaction = project.new_reaction()
    reaction.name = "Oxidation of ethanol"
    reaction.starting_materials.append(sample)
    reaction.save()
```

## Dumping the JSON validation schemas

The client validates LabIMotion generic structures (element/segment/dataset klasses, layers,
fields, select options) against JSON Schemas that ship as Python modules under
`chemotion_api/labImotion/items/validation/schemas/`. To export every registered schema as
plain JSON — e.g. for external tooling, documentation, or diffing against a server release —
use the generic manager:

```python
from chemotion_api import Instance

with Instance("https://...", username="USER", password="PASS") as instance:
    instance.generic_manager().write_all_validation_schemas()
```

Or, against the local test stack (credentials overridable via `ELN_URL`/`ELN_USER`/`ELN_PASS`):

```bash
just schemas
```

This writes one `<kind>/draft-01.json` per schema (element, segment, dataset, layer, field,
properties, select_option, …) into a `schemas/` directory under the **current working
directory**. The dump is a generated artifact — regenerate it on demand rather than committing
it (the repository gitignores `schemas/`). The copy under `tests/schemas/` is rewritten
automatically by the integration test suite.

## Command-line interface

The package installs a `chemotion_api` command for managing local dockerized Chemotion
instances (useful for development and testing):

```bash
chemotion_api --help    # scaffold, start/stop, configure ports, back up local instances
```

## Documentation

Sphinx documentation (API reference + guides) lives in [docs/](./docs) and builds in CI on
every push:

```bash
just docs    # → docs/_build/html/index.html
```

## Testing

The default test run is offline and memory-safe; integration tests run against a
**self-contained seeded docker environment** — see [tests/README.md](./tests/README.md) and
[tests/test_config/README.md](./tests/test_config/README.md):

```bash
# offline suite (no server; CI runs `just check` = mypy + this, on 3.14)
just test

# integration suite: boots + seeds the dockerized ELN automatically (docker required)
just test-integration
```

## Project layout

| Path | Contents |
| --- | --- |
| `chemotion_api/` | The client package (elements, collections, LabIMotion, CLI). |
| `tests/test_config/` | Self-contained dockerized Chemotion + seeded database for integration tests. |
| `docs/` | Sphinx documentation. |

## References

- [Chemotion ELN](https://chemotion.net/)

## License

GNU Affero General Public License v3 — see [LICENSE](./LICENSE).
