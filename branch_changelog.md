# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-07-05 — Fix: correctness, safety, and maintainability

- **Null-safety**: Guard `wellplate.get('wells')`, segment class lookups, `klass_obj` access, and port lists against None/empty.
- **Exception handling**: Specify exception types in `collection.get_or_create` and `utils` merge functions (avoid bare `except:` catching SystemExit/KeyboardInterrupt).
- **Naming**: `filed_type` → `field_type` (typo across search modules); `get_next_shot_label` → `get_next_short_label` (spelling + removed contradictory `@staticmethod`).
- **Testing**: Add `test_attachment_streaming_fallback` to verify both `iter_file()` and `load_file()` code paths are exercised.
- All 110 unit tests pass; no behavioral changes, only robustness.

## 2026-07-03 — Lint: ruff widened to pyflakes (F) and bugbear (B)

- `select = ["UP", "F", "B"]`; `tests/**` ignores `B011`/`B017` (the try/except + `assert False` idiom is deliberate; pytest never runs under `python -O`).
- ~70 unused imports/variables removed; exception chaining (`from e`/`from None`) added at every raise-inside-except; unused loop variables `_`-prefixed.
- `schemas/imports.py` generator now emits per-line `# noqa: F401` (side-effect imports).
- Code note: `Author`/`AuthorAffiliation` are re-exported via the PEP 484 redundant-alias idiom.

## 2026-07-03 — Docs: `.eln` reading + collection-tree import

- `docs/OfflineIngestion.rst` covers both directions (export ZIP → `.eln`, and reading a `.eln` back) with autodoc for `ElnCrate`/`ElnDataset`/`ElnFile`.

## 2026-07-02 — Collection trees for native-ZIP import + producer marker

- `import_export_zip` now rebuilds the exported **collection tree** (bundles supported): one `OfflineCollection` per collection, elements scoped via the `CollectionsSample`/`CollectionsReaction` join tables; several top-level collections group under a synthetic root. Import only — writing the native format stays with the ELN GUI.
- Every exported crate embeds a producer marker: a `SoftwareApplication` node named `chemotion-api` (with version) referenced by the descriptor's `sdPublisher`. Grep: `"name": "chemotion-api"` in `ro-crate-metadata.json`.
- `import_eln` accepts only our own crates by default (foreign `.eln` import is deferred); `allow_foreign=True` opens them best-effort. `ElnCrate.producer` / `.is_chemotion_api` expose the marker.
- Fix: `_OfflineResponse` lacked `close()`, so archived attachment payloads were skipped during offline export.

## 2026-07-02 — `.eln` importer

- `Instance.import_eln(path)` / `chemotion_api.offline.import_eln` opens a `.eln` (ZIP or extracted crate dir) and exposes it as navigable objects: `ElnCrate` (root, datasets, files, authors, `read_file`) / `ElnDataset` (kind, files, sub-datasets) / `ElnFile` (`read()`/`extract()`).
- Zip-slip-safe payload access; metadata-only File nodes raise `FileNotFoundError` on `read()` instead of failing silently.
- ORCID/ROR authors round-trip back into `Author`/`AuthorAffiliation` objects.
- Round-trip tested against our own exporter output.

## 2026-07-01 — Gated coverage reporting and offline-suite expansion

- Coverage gate via `fail_under` in `pyproject.toml` (54% then; since raised to 55%); CI posts the coverage summary and uploads `coverage.xml` as an artifact.
- New unit tests: `tests/unit/test_pure_helpers.py` and `tests/unit/test_research_plan_body.py`.

## 2026-07-01 — GitHub Actions — offline gate and nightly integration

- New `.github/workflows/ci.yml`: ruff lint, mypy, offline test suite and docs build on pushes to main and PRs.
- New `.github/workflows/integration.yml`: nightly integration run against the seeded docker stack.

## 2026-06-30 — Docs: Sphinx site, user-facing README and CHANGELOG

- `docs/` site: Sphinx build with cross-references and autodoc for main entry points (theme: `sphinx_rtd_theme`).
- User-facing `README.md` and `CHANGELOG.md` (newest-first, dates, summaries).

## 2026-06-30 — Self-contained seeded integration environment

- `tests/test_config/compose.yml` (Chemotion 3.1.2 + Postgres, Push2Deploy embed scripts) boots a live ELN on port 3579.
- Pre-seeded DB (`tests/data/test.sql`): API/ADM/MM users plus sample data.
- `conftest.py` runs `tests/data/setup_chemotion_db.sh` when `NO_SETUP=0`: boots the stack, resets the DB from the seed, waits for the `**SUCCESS**` marker.

## 2026-06-29 — chem-dcat-ap mapping, SHACL conformance and ontology-annotation suites

- Test suites for the chem-dcat-ap mapping, SHACL shape conformance of exported crates, and ontology annotation of analyses.

## 2026-06-29 — Offline ingestion of Chemotion export ZIPs

- `chemotion_api.offline.import_export_zip` navigates and indexes exported collections without a server. Returns `OfflineCollection` tree; RO-Crate support (`.eln` files) came later (2026-07-02 importer).

## 2026-06-26 — Analysis ontology annotation, streamed attachments, two-phase progress

- Analyses are annotated with CHMO ontology IRIs during export, resolved by `chemotion_api/ontology/ols_lookup.py` from the CHMO code embedded in `extended_metadata.kind` (with a typed fallback mapping and cached OLS lookups).
- Attachments stream into the `.eln`; `progress_callback(processed_count, total_count, current_item_name)` reports per item; a missing file is skipped (recorded in the skip manifest) instead of aborting the export.

## 2026-06-25 — Explicit ORCID + ROR authorship replaces the logged-in-user default

- `Author` and `AuthorAffiliation` capture full identity (ORCID, name) and org identity (ROR, name) respectively.
- Export no longer defaults to the logged-in user; `export_eln` raises `ValueError` unless authors with ORCID + ROR affiliations are supplied (`validate_authors`).

## 2026-06-22 — RO-Crate 1.1 .eln exporter (logged-in user as author)

- `Collection.export_eln(...)` bundles a collection + its elements as a ZIP containing RO-Crate 1.1 metadata (crate descriptor, datasets per element type, file payloads).
- Offline-capable: the RO-Crate JSON-LD context is vendored (`chemotion_api/data/ro-crate-context.jsonld`), so serialization needs no network access.

## 2026-06-18 — Typed element layer with chem-dcat-ap mapping

- `Sample.to_dcat_ap()` / `Reaction.to_dcat_ap()` map element JSON to chem-dcat-ap objects.
- Reaction: starting materials/reactants/products/solvents with roles and quantities; conditions (temperature, duration) as typed properties.
- Sample: molecule identifiers (SMILES/InChI) and quantities (mass, volume, amount, density, molarity) as QUDT-typed values.

## 2026-06-15 — CHMO term resolution via embedded codes and cached OLS lookup

- `chemotion_api/ontology/ols_lookup.py` + `OntologyRegistry` resolve CHMO terms from the code embedded in an analysis' `extended_metadata.kind`, hitting the OLS API on first use with caching; an embedded fallback mapping covers offline use.

## 2026-06-11 — Pydantic v2 data models for samples, reactions and molecules

- `chemotion_api/models.py` with Pydantic v2 models (`ConfigDict(extra='allow')` so unknown server fields pass through) for chem-dcat-ap aware fields (SMILES, InChI, density, stoichiometry).
- Replaces inline dict-based schema handling; proper IDE autocomplete.

## 2026-06-09 — Typed fields and a schema validation registry

- `chemotion_api.labImotion.items.{layer, fields, …}` typed; `.value` properties on field types.
- `SchemaRegistry` (jsonschema validator store, singleton) enables runtime property validation before model construction.

## 2026-06-08 — Modernize the core plumbing

- `Instance`, `ElementManager`, `User` strongly typed.
- `Connection` configurable with `verify_ssl`, auto-retrying transient failures (HTTP 502/503/504, idempotent methods only).
- `SchemaManager` decouples version/schema metadata from request logic.

## 2026-06-02 — Migrate to uv + just, target Python 3.14

- `pyproject.toml`: uv-managed deps, Python ≥ 3.14.
- `justfile`: reproducible dev tasks (build, test, lint, coverage).
- Removed the `requirements.txt` files.

## 2026-06-01 — Remove build artifacts, generated dumps and stale configs

- Housekeeping: deleted `.gitlab-ci.yml`, `.readthedocs.yaml`, `.tool-versions`, `chemotionapi.iml`, `config.json.sample` and the `dist/` wheels.
