# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-07-06 — feat: `GenericManager.check_schema_drift()` + schema version documented

- **`check_schema_drift()`** → fetches every element/segment/dataset klass the connected instance serves (REST API only — real deployments give no access to server internals) and validates each against the bundled JSON schemas; returns per-kind lists of non-conforming klasses with human-readable messages. Built-in klasses (`is_generic: false`) are skipped — they are not LabIMotion templates.
- **Schema version documented** → README and the validation package now state that the bundled schemas track **LabIMotion 2.1.1 as shipped with Chemotion ELN v3.1.2** (LabIMotion serves no schema documents over its API; the bundled schemas are a client-side reimplementation).
- **First drift finding, fixed** → running the new check against the live seeded 3.1.2 instance revealed that `properties_template.version` is `null` on a freshly created (never-released) klass; the properties schema now allows `null | string`.
- Tests: 3 offline unit tests (fixtures conform; corrupted klass reported; empty instance clean) + a live integration test asserting no drift on the seeded instance.

## 2026-07-06 — fix: filename typos and schema-dump docs correction

- **Filename typos renamed** (all references updated): `schema_generc_{dataset,element,layer,linked_element,segments}.py` → `schema_generic_*.py`; `tests/test_analyses_attachements.py` → `test_analyses_attachments.py`. Full pass over all tracked filenames found no other misspellings.
- **`just schemas` / README corrected**: the LabIMotion validation schemas ship with the package (registered into `SchemaRegistry` at import time) — they are *not* fetched from a live ELN. `write_all_validation_schemas` is now a `@staticmethod` and the recipe no longer logs in.

## 2026-07-06 — fix: crate-relative identifier policy (no fabricated PIDs) + CAS list repr

Outcome of an alignment review against the chem-dcat-ap canonical examples (incl. their
Chemotion-Repository-derived `SubstanceSampleCharacterizationDataset`):

- **No fabricated external PIDs** → `Sample.to_dcat_ap()` no longer emits `https://www.chemotion-repository.net/pid/<local-id>` (a plausible-looking but non-existent identifier built from the local ELN id). Policy, now documented in `docs/FairExport.rst`: IRIs naming our records are strictly crate-internal; real PIDs/DOIs come into existence at publication and can be injected post-hoc (same in-place patching approach as `ontology_patch`). External IRIs remain only for shared things: ontology terms, ORCID/ROR, CAS notations.
- **Sample short label** is emitted as an honest local identifier notation instead.
- **CAS fixed** → the ELN stores CAS as a list; each number is now emitted as its own identifier (was: the Python list repr `"['64-17-5']"`).

## 2026-07-05 — fix: license metadata matches the LICENSE file (AGPL-3.0)

- `pyproject.toml` (`AGPL-3.0-or-later`) and README now match the committed `LICENSE` file (GNU AGPL v3); both previously declared MIT, contradicting the license text shipped since the first commit.

## 2026-07-05 — docs: verify and correct claims across all markdown files

- Every claim in `README.md`, `CHANGELOG.md`, `branch_changelog.md`, `tests/README.md` and `tests/test_config/README.md` was verified against the code and git history by three independent review agents; inaccuracies fixed:
- **README.md** → coverage gate 48% → 55%; `just check` description includes lint; docs CI trigger scoped to "main + PRs"; `stack-up` description (start only); ELN compatibility wording (3.1.2 current, 2.1.1 historical).
- **tests/README.md / pytest.ini / justfile** → `tests/unit` description (110 tests incl. 7 heavy export tests, not "no RO-Crate serialization"); the broken `-p no:forked` advice replaced with a working `-o addopts=` override; `test-unit` comment no longer claims to be "what CI runs".
- **branch_changelog.md** → pre-07-05 entries rewritten against the actual commits: real commit dates restored (entries were dated up to 3 weeks off), and unverifiable claims removed (no `ChemOntologyManager`, no PyPI auto-release/`PYPI_TOKEN`, no `pytest --reset-eln`, no `models.v2`/strict mode, no `.travis.yml`/Makefile removal, no 85%/88% coverage thresholds, no `dcat:byteSize` mapping, no author-less exports — authors are mandatory).
- **CHANGELOG.md / pyproject.toml** → coverage figure corrected to the measured 55.29%.
- `Attachment.load_file` now delegates to `iter_file()` (single code path; whole-body-in-memory remains its documented contract).
- Flagged (pre-existing on main): `LICENSE` file is AGPL-3.0 while `pyproject.toml` and README declared MIT — resolved in the follow-up commit in favour of the LICENSE file.

## 2026-07-05 — release: version 312.0.0 (breaking changes documented)

- **Version bumped 211.0.1 → 312.0.0** (`pyproject.toml`, `docs/conf.py`). Scheme: `312.x.y` tracks compatibility with Chemotion ELN **v3.1.2**. The major bump signals the breaking changes accumulated on this branch:
  - `Connection` no longer subclasses `requests.Session` (composition; `.mount()`, `.headers`, post-construction `verify` etc. are gone — use constructor args; verb methods, `close()` and `with` support remain).
  - `RootCollection.move` → `move_collection` (signature clash with `AbstractCollection.move`).
  - `ElementManager.get_next_shot_label` → `get_next_short_label` (typo fix; old method was already broken — `@staticmethod` with a `self` param — so no working caller existed).
  - `Variations.remove` follows the `MutableSequence` contract (returns `None`, raises `ValueError` when absent).
  - `Variation` no longer subclasses `Reaction`.
- CLI docs now recommend the `PGPASSWORD` environment variable over the `--pgpassword` option (CLI options end up in shell history).

## 2026-07-05 — fix: robustness & resource-handling hardening (review follow-ups)

- **Duplicate uploads eliminated** → `Attachments.save`/`MutableAttachments.save` clear the upload queue after a successful request (`_mark_uploads_done`), so calling `save()` twice no longer re-uploads and duplicates files server-side.
- **File-handle leaks fixed** → multipart upload files are opened via `contextlib.ExitStack` (attachments) or a `with` block (inbox) and always closed; `empty_elements` uses a context manager.
- **Streaming instead of whole-body-in-memory** → `Attachment.save_file` streams via `iter_file()`; `Dataset.write_zip`/`write_data_set_xlsx` stream with `stream=True` + `iter_content`; `AnalysesManager.upload_file` reads one chunk at a time (was: whole file, then chunked from memory); `ontology_patch` streams zip members via `copyfileobj`.
- **Atomic crate export** → `.eln` export writes to `<name>.part` and renames on success, so a failure mid-export can no longer clobber a previous good export with a truncated zip.
- **Temp-file cleanup** → `ontology_patch` removes its temp file on failure.
- **HTTP timeouts** → the three bare `requests.get` calls in the CLI commands (Docker Hub tags, OLS lookup) now use `timeout=30`.
- **Header merging** → caller-supplied headers are merged over the defaults in `Connection._send_request` instead of replacing them, so custom headers no longer silently drop the `Authorization` bearer.
- **SchemaRegistry** → schema store is per-instance state (no longer a shared class attribute); the validator registry is invalidated on late registrations.

## 2026-07-05 — refactor: eliminate the last 13 `type: ignore[override]` comments

- **search builders** → base `add_search_condition(**kwargs)` renamed to protected `_add_search_conditions`; the typed `add_search_condition` methods on `SampleSearcher`/`ReactionSearcher` are no longer overrides. `new_field`/`field_details` accept `str` (allowed values documented; unsupported fields still raise `ValueError`).
- **`Variation`** → no longer subclasses `Reaction` (it never called the inherited behaviour and its material properties hold `SampleVariation` snapshots, not `MaterialList`s — not substitutable). `Variations.remove` now follows the `MutableSequence` contract (returns `None`, raises `ValueError` when absent).
- **collection.py** → `Collection.add_collection` accepts `str | list[str]` like the base; **`RootCollection.move` renamed to `move_collection`** (its `src, dest` signature clashed with `AbstractCollection.move(dest)`; `Collection.move(dest)` is unchanged).
- **attachments.py** → `Attachments.__getitem__` supports slices via overloads; `Attachments.save` return type widened to `Response | None` so `MutableAttachments.save` is a clean override.
- The CHANGELOG claim "eliminates all `type: ignore[override]` comments" is now actually true: zero remain.

## 2026-07-05 — security: path-traversal and SQL-injection fixes

- **`Attachment.save_file`** → server-provided filenames are reduced to a safe basename via new `utils.safe_download_filename()`; `../../x` or absolute names can no longer escape the target directory.
- **`Dataset.write_zip` / `write_data_set_xlsx`** → filename now parsed robustly from `Content-Disposition` (handles missing header and unquoted `filename=`) and sanitized; previously a crafted header could traverse directories and a missing/unquoted header crashed with `KeyError`/`AttributeError`.
- **`ElnFile.extract`** → the crate-metadata `name` (attacker-controlled in a foreign `.eln`) is sanitized to a basename before writing; `"name": "../../x"` in `ro-crate-metadata.json` can no longer write outside `dest_dir`.
- **`insert_dataset` CLI command** → OLS-fetched `label`/`definition` are passed to psql as `-v` variables with `:'var'` quoting (SQL fed via stdin) instead of f-string interpolation; apostrophes in CHMO definitions no longer break the insert and a malicious response can no longer inject SQL.

## 2026-07-05 — fix: minor review findings (wellplate size 0, shared search dicts, affiliations)

- **wellplate.py** → `size == 0` now correctly sends an empty well list instead of all wells (truthiness test conflated "size missing" with "size zero").
- **search/utils.py `get_field_details`** → returns a copy of the field metadata; callers mutating a built search condition can no longer corrupt the shared `FIELD_DEFINITIONS` for later searches.
- **user.py `affiliations` setter** → normalizes raw dicts from a user payload into `Affiliation` objects, so `get_affiliations()` never returns plain dicts.

## 2026-07-05 — fix: Connection.close() and generic-klass cache invalidation

- **`Connection.close()` / context-manager support** → the composition refactor dropped the inherited `Session.close()`; `with Instance(...)` silently leaked the pooled sockets (the `hasattr` guard in `Instance.__exit__` was dead code). `Connection` now delegates `close()` and supports `with`.
- **Generic-klass cache invalidation** → `Connection.reset_generic_segment_cache()` and `ElementManager.reset_cache()` added; `GenericManager` (create/upload of elements and segments) and `save_template`/`save_generale_properties` invalidate the caches, so elements loaded after creating a segment class no longer silently drop that segment, and `all_version_of_generic_class` no longer serves stale revision sets. `Instance.generic_manager()` wires its `ElementManager` in.

## 2026-07-05 — fix: stop leaking `attachments: []` and `name: ''` into save payloads

- **`AbstractElement.attachments`** → returns `None` again when the element carries no attachment data (e.g. fetched from a listing, never fully loaded), restoring pre-branch semantics. Previously every save payload included `attachments: []` and unconditionally POSTed `update_attachments_attachable` with an empty list — a server treating that as authoritative could detach existing attachments.
- **`ResearchPlan.add_image`** → creates the attachment container on demand; `_parse_image` returns `None` when no attachment data is present.
- **`AbstractElement.name`** → returns `None` again when unset (was `''`), so saves no longer overwrite a server-side null name with an empty string.

## 2026-07-05 — fix: exception-handling regressions found by review

- **collection.py `get_or_create_collection`** → now also catches `ModuleNotFoundError`, which `get_collection` raises for missing collections; the create branch was dead code and first-time callers crashed on a fresh DB.
- **sample.py `to_dcat_ap`** → mass/volume/amount guards widened to `(KeyError, ValueError, TypeError, ZeroDivisionError, AttributeError)` (matching the existing guard at `_set_amount`); decoupled samples and samples with missing amount/molarity keys raised `KeyError` instead of omitting the quantity.
- **`Instance.get_collection_of_element`** → outer handler widened to `(KeyError, IndexError, TypeError)` so empty `collection_labels` or a `None` tag still produce the friendly `KeyError` message.
- **collection.py `_index`** → added missing `continue` after recording a failed element load; the fall-through crashed the whole crate export on `it.properties` of the unloaded element.
- **abstract_element.py `load()`** → `_data_loaded` is now set only after the server fetch succeeds, so a failed load no longer leaves the element claiming to be loaded with `None` properties.

## 2026-07-05 — Fix: consolidate duplicate search builders and improve API error handling

- **Refactored duplicate field builders** → Extracted 60+ lines of identical `field_details()` code into shared `FIELD_DEFINITIONS` dict + `get_field_details()` helper in `search/utils.py`. sample.py and reaction.py now call shared logic.
- **API response validation** → Added safe `.get()` patterns and type checks for JSON responses in element_manager.py and user.py. Prevents silent failures on malformed server responses (missing keys, wrong types).
- **@property caching audit** → Reviewed all @property methods; generic_segments.py and element_manager.py already have appropriate caching. No additional N+1 opportunities found at API boundaries.
- Tests: 110/110 passing. Code maintainability and robustness improved, ~70 lines removed through consolidation.

## 2026-07-05 — Fix: typos, magic numbers, type validation, and null checks

- **Typos fixed** (5 locations): "Counld"→"Could", "genetic"→"generic", "Wallplate"→"Wellplate", "Horiconcal"→"Horizontal", "starting_aterials"→"starting_materials", "perpetration"→"preparation".
- **Magic numbers** → Replaced hardcoded 8 & 12 with `WELLPLATE_ROWS` and `WELLPLATE_COLUMNS` constants in ElementManager.
- **Type validation** (wellplate.py) → Removed unsafe `cast()` calls; added proper `isinstance()` checks for json_data, wells, size with clear error messages.
- **Null safety** → Added guard check for `sample.molecule` before calling `.get()`; improved exception specificity from `Exception` to `(AttributeError, TypeError)`.
- Tests: 110/110 passing. Code clarity and type safety improved.

## 2026-07-05 — fix: specify exception types in remaining bare except clauses

- Changed 10 bare except: clauses to specify exact exception types:
- `elements/__init__.py`: (ValueError, TypeError) for int() conversions
- elements/sample.py (6x): (ValueError, TypeError) for float() conversions
- elements/workflow_manager.py: (StopIteration, KeyError) for next() lookups
- elements/abstract_element.py (2x): (ValueError, TypeError, AttributeError) for date parsing
- Tests: 110/110 passing. Behavior unchanged; improves debuggability by not hiding unexpected exceptions.

## 2026-07-05 — fix(arch): refactor Connection from inheritance to composition (LSP)

- Refactored `Connection` from inheriting `requests.Session` to composing it.
- Previously, the class inherited from Session but changed method signatures (url_path instead of url), requiring `# type: ignore[override]` comments—a Liskov Substitution Principle violation.
- Now Connection owns a `_http_session` and delegates to it. No type ignores needed.
- Behavioral changes: none. Tests: 110/110 passing.

## 2026-07-05 — Perf: cache generic class revisions (avoid N+1 API calls)

- `ElementManager.all_version_of_generic_class` now uses `@functools.cached_property` instead of `@property`.
- Previously, any access to `all_types` (which consults `all_version_of_generic_class`) would loop through every generic class and re-fetch its revisions from the server (one GET per class to `/api/v1/generic_elements/klass_revisions.json`).
- Now the fetch is cached for the lifetime of the ElementManager instance, eliminating N+1 queries on paginated or bulk-element operations.

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
