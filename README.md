# Chemotion API Python Client (Pydantic & Chem-DCAT-AP)

A modernized Python client for the [Chemotion ELN](https://chemotion.net/) REST/Grape API,
focused on making your lab data **FAIR**: it validates element properties with **Pydantic v2**,
maps chemistry entities onto the NFDI **[chem-dcat-ap](https://nfdi-de.github.io/chem-dcat-ap/)**
metadata schemas, and exports collections as **RO-Crate 1.1** conformant
[`.eln`](https://github.com/TheELNConsortium/TheELNFileFormat) archives — from a live server or
fully offline from a Chemotion export ZIP.

## Key features

- **Full REST client** — collections, samples, reactions, wellplates, research plans, LabIMotion
  generic elements/segments/datasets, attachments and analyses, search, users/groups/devices,
  inbox, converter profiles, and admin endpoints.
- **Pydantic v2 type safety** — element properties are validated and normalized on read and write.
- **chem-dcat-ap mapping** — `Sample.to_dcat_ap()` / `Reaction.to_dcat_ap()` produce typed
  `SubstanceSample` / `ChemicalReaction` metadata (QUDT units, CHEBI/CHMO/CHEMINF terms).
- **RO-Crate 1.1 `.eln` export** — `Collection.export_eln()` packages a collection tree, its
  metadata graph, and all attachments into a standards-compliant ZIP: crate-relative paths (no
  server URIs), a JSON-LD `ro-crate-metadata.json`, zip-slip-safe filenames, streamed attachment
  downloads, and a skipped-items manifest so nothing is lost silently.
- **Offline ingestion** — `Instance.import_export_zip()` rebuilds a collection tree (single
  collection or a bundle) from a Chemotion *export collection* ZIP and exports it to `.eln`
  with **no live server**. Import only — writing the native format stays with the ELN GUI.
- **`.eln` import** — `Instance.import_eln()` reads a `.eln` exported by this library back into
  navigable datasets, files (zip-slip-safe payload access), and ORCID/ROR authors; crates are
  identified by an embedded `chemotion-api` producer marker (foreign `.eln` import is deferred).
- **Ontology resolution** — analysis techniques are annotated with CHMO terms via embedded codes
  or a cached [EBI OLS4](https://www.ebi.ac.uk/ols4) lookup; `chemotion_api.ontology_patch` can
  upgrade existing `.eln` files in place.
- **Explicit authorship** — `.eln` export requires ORCID-identified authors with ROR-identified
  affiliations, so the resulting crates carry citable provenance.
- **Instance management CLI** — the `chemotion_api` command scaffolds and manages local
  dockerized Chemotion instances (start/stop, ports, backups).

## Requirements & installation

- Python **>= 3.14** (managed automatically by [uv](https://docs.astral.sh/uv/))
- A Chemotion ELN server — v3.1.2 is what the current test stack runs against (version
  scheme `312.x.y`); 2.1.1 was covered historically. Or none at all for the offline workflow.
- For development: [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/)
  (plus docker for the integration test stack).

Install from source (dependencies, including `chem_dcat_ap` and `dcat_ap_plus`, resolve from PyPI):

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
just cov                # offline-suite coverage report (gated at 55%)
just docs               # build the Sphinx documentation
just schemas            # dump the LabIMotion JSON schemas from a live ELN
just stack-up           # start the dockerized test ELN (see also stack-down / stack-reset / stack-logs)
just build              # build sdist + wheel
```

## Quickstart

Connect, create a validated sample, and export the collection as a citable `.eln`:

```python
from chemotion_api import Instance, Author, AuthorAffiliation

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

    # .eln export requires authors: ORCID iD + at least one ROR-identified affiliation
    project.set_authors([
        Author(name="Ada Lovelace", orcid="0000-0002-1825-0097",
               affiliations=[AuthorAffiliation(name="Example University",
                                               ror="https://ror.org/05dxps055")]),
    ])
    project.export_eln("my_project.eln")
```

### Export options

`export_eln(file_path, ...)` accepts:

| Option | Default | Effect |
| --- | --- | --- |
| `authors` | collection's `set_authors` | Author list for the crate (mandatory, validated). |
| `strict` | `False` | Fail hard if anything would be omitted; otherwise omissions are logged and recorded in the manifest. |
| `ontology_lookup` | `True` | Resolve analysis techniques via EBI OLS4 (network); `False` uses only embedded codes. |
| `ols_cache` | `None` | Path to a JSON OLS cache (read + updated) for deterministic/offline runs. |
| `interactive` | `False` | tqdm progress bars (element mapping, then attachment download). |
| `progress_callback` | `None` | `callback(i, total, name)` invoked across both phases. |

### Offline: Chemotion export ZIP → `.eln`

No server or credentials needed — convert an *export collection* ZIP (or its extracted
directory, or a bare `export.json`) directly:

```python
from chemotion_api import Author, AuthorAffiliation
from chemotion_api.offline import import_export_zip

col = import_export_zip("my_chemotion_export.zip")
col.export_eln("out.eln", authors=[Author(...)])
```

The ZIP may hold a single collection or a bundle: the original collection tree is rebuilt
(one collection per exported collection, elements scoped via the dump's membership join
tables; several top-level collections are grouped under a synthetic root). Import only —
*writing* Chemotion's native export format is the ELN GUI's domain, not this library's.

Samples and reactions (with molecules, analyses, and attachments) are reconstructed; element
kinds that are not yet reconstructed offline (wellplates, screens, research plans, generic
elements) are counted in the export manifest — with `strict=True` their presence fails the
export instead.

### Reading a `.eln` back in

`import_eln` opens a `.eln` RO-Crate archive (or an extracted crate directory) and exposes its
metadata graph and payload files as navigable objects. Supported input is what this library's
own `export_eln` writes; `.eln` files from other ELNs are a deferred feature (pass
`allow_foreign=True` for best-effort generic RO-Crate parsing):

```python
from chemotion_api.offline import import_eln   # or: Instance.import_eln(...)

with import_eln("out.eln") as crate:
    print(crate.root.name, crate.date_created)
    print([a.name for a in crate.authors])     # Author objects (ORCID + ROR round-trip)
    for ds in crate.elements:                  # datasets with a recognizable element kind
        print(ds.kind, ds.name)                # "sample" / "reaction" / ...
        for f in ds.files:
            f.extract("downloads/")            # or f.read() for the bytes
```

`crate.datasets` lists every dataset node (including collection folders); file access is
zip-slip safe, and File nodes whose payload is missing from the archive raise
`FileNotFoundError` on `read()` rather than failing silently.

Every crate this library exports carries a producer marker: a `SoftwareApplication` node named
`chemotion-api` (with the package version), referenced by the metadata descriptor's
`sdPublisher` — TheELNFileFormat's convention for "the software that wrote this crate". That
makes our crates trivially identifiable:

```bash
unzip -p out.eln '*/ro-crate-metadata.json' | grep '"name": "chemotion-api"'
```

Programmatically: `crate.producer` (the node) and `crate.is_chemotion_api` (bool).

### DCAT-AP metadata without an archive

```python
substance = sample.to_dcat_ap()      # chem-dcat-ap SubstanceSample (Pydantic)
reaction_md = reaction.to_dcat_ap()  # chem-dcat-ap ChemicalReaction
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
every push to main and on pull requests:

```bash
just docs    # → docs/_build/html/index.html
```

## Testing

The default test run is offline and memory-safe; integration tests run against a
**self-contained seeded docker environment** — see [tests/README.md](./tests/README.md) and
[tests/test_config/README.md](./tests/test_config/README.md):

```bash
# offline suite (no server; CI runs `just check` = lint + mypy + this, on 3.14)
just test

# integration suite: boots + seeds the dockerized ELN automatically (docker required)
just test-integration
```

## Project layout

| Path | Contents |
| --- | --- |
| `chemotion_api/` | The client package (elements, collections, offline, ontology, LabIMotion, CLI). |
| `tests/test_config/` | Self-contained dockerized Chemotion + seeded database for integration tests. |
| `docs/` | Sphinx documentation. |

## References

- [CHANGELOG.md](./CHANGELOG.md) — recent changes, the SHACL conformance baseline, known gaps.
- [Chemotion ELN](https://chemotion.net/) · [chem-dcat-ap](https://nfdi-de.github.io/chem-dcat-ap/) ·
  [The .eln file format](https://github.com/TheELNConsortium/TheELNFileFormat) ·
  [RO-Crate 1.1](https://www.researchobject.org/ro-crate/1.1/)

## License

MIT — see [LICENSE](./LICENSE).
